"""Inverse kinematics with quantised LRU seed cache.

Wraps PyBullet's damped-least-squares IK (via :class:`RobotArmSim`) and
caches the (xyz, quat) -> q solution under a key quantised to 1 mm /
0.01 wxyz (gap-report §I item: warm-start cache for repeated goal-pose
planning). The cache uses :class:`collections.OrderedDict` so we can
expose hits / misses for tests; :func:`functools.lru_cache` is avoided
because it does not.

Notes
-----
* Module top imports stdlib only; PyBullet is imported inside the worker
  thread (lazy) so :mod:`src.planning.ik` stays importable on Windows.
* The cache is keyed by ``(scene.fingerprint, xyz_quantised, quat_quantised)``
  so two scenes with the same robot but different obstacles do not
  cross-contaminate.
* ``residual_tol_m`` defaults to 5 mm; callers requiring tighter accuracy
  pass their own.
* PyBullet's ``BulletClient`` has thread affinity (risk #7): the client
  is constructed on, and only ever touched from, a dedicated worker
  thread owned by this :class:`IKSolver`. Public calls (:meth:`solve`)
  post a request envelope to a :class:`queue.Queue` and block on a
  :class:`~concurrent.futures.Future`. Cache reads/writes stay on the
  calling thread under a separate lock.
"""

from __future__ import annotations

import math
import queue
import threading
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Sequence

from src.planning.scene import SceneSnapshot
from src.planning.types import PlanningUnavailable

# Quantisation grid for seed-cache hits. 1 mm + 0.01 wxyz matches the
# specification in §A: "LRU keyed by (robot_id, target_xyz_quantised_to_1mm)".
_XYZ_GRID_M = 1e-3
_QUAT_GRID = 1e-2

# Sentinel telling the worker loop to shut down cleanly.
_SHUTDOWN = object()


# Internal request envelope. Each entry is either the sentinel or a tuple
# of (target_xyz, target_quat_xyzw, seed_or_None, Future).
_QueryEnvelope = (
    tuple[
        tuple[float, float, float],
        tuple[float, float, float, float],
        tuple[float, ...] | None,
        Future,
    ]
    | object
)


class PlanningIKUnreachable(RuntimeError):
    """Raised when IK cannot achieve the target within tolerance."""


@dataclass(frozen=True)
class IKResult:
    """One IK solution + cache diagnostics."""

    q_rad: tuple[float, ...]
    residual_m: float
    seed_was_cache_hit: bool


def _quantise_xyz(
    xyz: tuple[float, float, float],
) -> tuple[int, int, int]:
    """Quantise a metric position to the 1 mm grid."""
    return tuple(round(v / _XYZ_GRID_M) for v in xyz)  # type: ignore[return-value]


def _quantise_quat(
    quat: tuple[float, float, float, float],
) -> tuple[int, int, int, int]:
    """Quantise a (w, x, y, z) quaternion to the 0.01 grid."""
    return tuple(round(v / _QUAT_GRID) for v in quat)  # type: ignore[return-value]


class IKSolver:
    """PyBullet-backed IK with a quantised LRU seed cache.

    The underlying ``RobotArmSim`` (and its PyBullet client) is constructed
    on, and only ever touched from, a dedicated worker thread owned by this
    solver. The constructor remains synchronous: it blocks until the worker
    reports the client is ready (or raises the initialisation error). The
    cache (OrderedDict) lives on the caller-side under a separate lock and
    never crosses the queue boundary.
    """

    def __init__(
        self,
        scene: SceneSnapshot,
        residual_tol_m: float = 0.005,
        cache_size: int = 256,
    ) -> None:
        import sys

        if sys.platform == "win32":
            raise PlanningUnavailable(
                "src.planning.ik is not supported on Windows. Use WSL."
            )
        if residual_tol_m <= 0.0:
            raise ValueError(
                f"residual_tol_m must be > 0, got {residual_tol_m}"
            )
        if cache_size < 1:
            raise ValueError(f"cache_size must be >= 1, got {cache_size}")

        self._scene = scene
        self._residual_tol_m = float(residual_tol_m)
        self._cache_size = int(cache_size)
        self._cache: "OrderedDict[tuple, tuple[float, ...]]" = OrderedDict()
        self._hits = 0
        self._misses = 0
        # _cache_lock guards _cache, _hits, _misses — caller-side state only.
        self._cache_lock = threading.Lock()
        # _lifecycle_lock guards _closed for idempotent shutdown.
        self._lifecycle_lock = threading.Lock()

        self._queue: queue.Queue[_QueryEnvelope] = queue.Queue()
        self._ready = threading.Event()
        self._init_error: BaseException | None = None
        self._closed = False

        self._thread = threading.Thread(
            target=self._worker,
            name=f"ik_{scene.robot_id}",
            daemon=True,
        )
        self._thread.start()

        # Wait for the worker to construct the PyBullet client (or report
        # an init error) so __init__ surfaces a meaningful exception
        # synchronously rather than failing on the first solve().
        if not self._ready.wait(timeout=10.0):
            raise RuntimeError(
                "IKSolver worker thread failed to initialise within 10s"
            )
        if self._init_error is not None:
            raise self._init_error

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        """Worker thread entry: own the PyBullet client, drain the queue."""
        # RobotArmSim is imported here (lazy) so the module top stays cheap
        # for the Windows guard and so the PyBullet ``connect()`` happens on
        # this worker thread (PyBullet client thread-affinity, risk #7).
        from src.simulation.engine import RobotArmSim

        try:
            sim = RobotArmSim(
                robot_name=self._scene.robot_catalog_name,
                use_gui=False,
                load_plane=False,
            )
        except BaseException as exc:  # noqa: BLE001
            self._init_error = exc
            self._ready.set()
            return

        self._ready.set()

        try:
            while True:
                envelope = self._queue.get()
                if envelope is _SHUTDOWN:
                    break
                # mypy doesn't narrow the union after the sentinel check;
                # we know this is the tuple form at this point.
                assert isinstance(envelope, tuple)
                target_xyz, quat_xyzw, seed, fut = envelope
                if fut.cancelled():
                    continue
                try:
                    if seed is not None:
                        pad = max(0, sim.num_joints - len(seed))
                        sim.reset_joint_angles(list(seed) + [0.0] * pad)
                    q = sim.solve_ik(
                        target_position=list(target_xyz),
                        target_orientation=list(quat_xyzw),
                    )
                    pad = max(0, sim.num_joints - len(q))
                    sim.reset_joint_angles(list(q) + [0.0] * pad)
                    ee_pos, _ee_quat_xyzw = sim.get_end_effector_pose()
                    residual_m = math.sqrt(
                        sum(
                            (float(a) - float(b)) ** 2
                            for a, b in zip(ee_pos, target_xyz)
                        )
                    )
                    q_tuple = tuple(float(v) for v in q)
                    fut.set_result((q_tuple, residual_m))
                except BaseException as exc:  # noqa: BLE001
                    fut.set_exception(exc)
        finally:
            try:
                sim.disconnect()
            except Exception:  # noqa: BLE001
                pass
            # Drain any pending envelopes so callers don't block forever
            # waiting on a Future the worker will never set.
            while True:
                try:
                    leftover = self._queue.get_nowait()
                except queue.Empty:
                    break
                if leftover is _SHUTDOWN:
                    continue
                assert isinstance(leftover, tuple)
                _, _, _, fut = leftover
                if not fut.done():
                    fut.set_exception(
                        RuntimeError("IKSolver worker exited unexpectedly")
                    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve(
        self,
        target_xyz_m: tuple[float, float, float],
        target_quat_wxyz: tuple[float, float, float, float],
        q_seed: Sequence[float] | None = None,
    ) -> IKResult:
        """Solve IK; return q + residual + cache-hit diagnostic.

        The PyBullet IK uses (xyz, wxyz) ordering on input but PyBullet
        natively expects (xyzw). The conversion is done at the boundary.
        Cache lookup happens before solving and warm-starts the solver
        with the previously-found q for that quantised target.

        Raises
        ------
        PlanningIKUnreachable
            If the residual exceeds ``residual_tol_m`` for the final
            converged q.
        RuntimeError
            If the solver has been closed or the worker thread is dead.
        """
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("IKSolver is closed")
            if not self._thread.is_alive():
                raise RuntimeError("IKSolver worker thread is not alive")

        key = (
            self._scene.fingerprint,
            _quantise_xyz(target_xyz_m),
            _quantise_quat(target_quat_wxyz),
        )

        seed_used: tuple[float, ...] | None = None
        seed_was_cache_hit = False
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._hits += 1
                seed_used = cached
                seed_was_cache_hit = True
            else:
                self._misses += 1
                if q_seed is not None:
                    seed_used = tuple(float(v) for v in q_seed)

        # PyBullet expects (x, y, z, w); the IR carries (w, x, y, z).
        quat_xyzw = (
            float(target_quat_wxyz[1]),
            float(target_quat_wxyz[2]),
            float(target_quat_wxyz[3]),
            float(target_quat_wxyz[0]),
        )

        fut: Future = Future()
        self._queue.put(
            (
                (float(target_xyz_m[0]), float(target_xyz_m[1]), float(target_xyz_m[2])),
                quat_xyzw,
                seed_used,
                fut,
            )
        )
        # 5s is generous; one IK solve against a 6-DOF arm is normally
        # << 50 ms even with cold caches.
        q_tuple, residual_m = fut.result(timeout=5.0)

        if residual_m > self._residual_tol_m:
            raise PlanningIKUnreachable(
                f"IK residual {residual_m:.6f} m exceeds tolerance "
                f"{self._residual_tol_m:.6f} m for target {target_xyz_m}"
            )

        with self._cache_lock:
            self._cache[key] = q_tuple
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                # FIFO eviction (oldest entry first) — popitem(last=False).
                self._cache.popitem(last=False)

        return IKResult(
            q_rad=q_tuple,
            residual_m=residual_m,
            seed_was_cache_hit=seed_was_cache_hit,
        )

    def cache_stats(self) -> tuple[int, int]:
        """Return ``(hits, misses)`` since construction."""
        with self._cache_lock:
            return self._hits, self._misses

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Shut the worker thread down and release the PyBullet client.

        Idempotent. Safe to call from any thread.
        """
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(_SHUTDOWN)
        self._thread.join(timeout=5.0)

    def __enter__(self) -> "IKSolver":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - GC fallback
        try:
            self.close()
        except Exception:
            pass


__all__ = ["IKSolver", "IKResult", "PlanningIKUnreachable"]
