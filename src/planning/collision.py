"""Thread-affined wrapper around :class:`src.collision.checker.CollisionChecker`.

PyBullet's ``BulletClient`` has thread affinity: constructing the client on
one thread and querying from another corrupts state (risk #7 / PyBullet
threading model in the perf-research stream). This wrapper resolves that by
owning a dedicated daemon thread and a ``queue.Queue`` for query traffic.
Pool workers call :meth:`is_collision` which posts a ``Future``-backed
request to the worker thread and blocks for the result.

OMPL state-validity-checker callbacks bind to this wrapper via
:meth:`make_validity_fn` — the OMPL C++ side never directly touches
PyBullet because the lambda forwards through the thread-safe queue.

Notes
-----
* Module top imports only stdlib + the planning types. Pybullet imports
  happen inside the worker thread (lazy).
* :class:`CollisionChecker` is reusable as a context manager; :meth:`close`
  is idempotent.
* On Windows, :meth:`__init__` raises :class:`PlanningUnavailable` (mirrors
  the Drake / OMPL story even though pybullet itself supports Windows —
  the rest of the planning stack does not, so the runtime is gated as a
  unit).
"""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Callable, Sequence

from src.planning.scene import SceneSnapshot
from src.planning.types import PlanningUnavailable

_LOG = logging.getLogger(__name__)

# Sentinel telling the worker loop to shut down cleanly.
_SHUTDOWN = object()


# Internal request envelope. Each entry is either the sentinel or a tuple
# of (q_tuple, clearance, future).
_QueryEnvelope = (
    tuple[tuple[float, ...], float, Future]
    | object
)


class CollisionChecker:
    """Thread-affined wrapper around ``src.collision.checker.CollisionChecker``.

    Construct it once per :class:`PlanningRuntime`. The underlying
    PyBullet client is built inside the worker thread the first time the
    thread runs and never returned to other threads. Pool callers use
    :meth:`is_collision` which posts a query, blocks on a
    :class:`~concurrent.futures.Future`, and never touches PyBullet
    directly.
    """

    def __init__(self, scene: SceneSnapshot) -> None:
        # Gate concrete-class instantiation per planning's Windows contract.
        # The underlying pybullet wheel exists on Windows but the rest of
        # the planning stack (OMPL, Drake, toppra) does not, so we keep the
        # behaviour consistent at the wrapper layer.
        import sys

        if sys.platform == "win32":
            raise PlanningUnavailable(
                "src.planning.collision is not supported on Windows. Use WSL."
            )

        self._scene = scene
        self._queue: queue.Queue[_QueryEnvelope] = queue.Queue()
        self._ready = threading.Event()
        self._init_error: BaseException | None = None
        self._closed = False
        self._lock = threading.Lock()

        self._thread = threading.Thread(
            target=self._worker,
            name=f"collision_{scene.robot_id}",
            daemon=True,
        )
        self._thread.start()

        # Wait for the worker to either construct the inner checker
        # successfully or report the error back so __init__ surfaces a
        # meaningful exception rather than failing on the first query.
        if not self._ready.wait(timeout=10.0):
            raise RuntimeError(
                "CollisionChecker worker thread failed to initialise within 10s"
            )
        if self._init_error is not None:
            # Worker thread already exited; re-raise on the caller's thread.
            raise self._init_error

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        """Worker thread entry: own the PyBullet client, drain the queue."""
        from src.collision.checker import CollisionChecker as InnerChecker

        try:
            inner = InnerChecker(
                robot_urdf_path=self._scene.robot_urdf_path,
                scene_meshes=tuple(self._scene.fixture_mesh_paths),
            )
            for half_extents, position in self._scene.fixture_boxes:
                inner.add_static_box(half_extents=half_extents, position=position)
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
                q_tuple, clearance, fut = envelope
                if fut.cancelled():
                    continue
                try:
                    result = inner.is_in_collision(q_tuple, distance_m=clearance)
                    fut.set_result(bool(result))
                except BaseException as exc:  # noqa: BLE001
                    fut.set_exception(exc)
        finally:
            try:
                inner.close()
            except Exception:  # noqa: BLE001
                pass
            # Drain any pending envelopes so callers don't block forever
            # waiting on a Future the worker will never set (worker crash
            # or unexpected exit).
            while True:
                try:
                    leftover = self._queue.get_nowait()
                except queue.Empty:
                    break
                if leftover is _SHUTDOWN:
                    continue
                assert isinstance(leftover, tuple)
                _, _, fut = leftover
                if not fut.done():
                    fut.set_exception(
                        RuntimeError("CollisionChecker worker exited unexpectedly")
                    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_collision(self, q: Sequence[float], clearance_m: float = 0.0) -> bool:
        """Return ``True`` if joint configuration ``q`` is in collision.

        Posts the query to the dedicated worker thread and blocks on the
        result. Safe to call from any thread, including the OMPL state-
        validity callback executed by ``Planner::solve``.

        Raises
        ------
        RuntimeError
            If the wrapper has been closed or the worker thread died.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("CollisionChecker is closed")
            if not self._thread.is_alive():
                raise RuntimeError("CollisionChecker worker thread is not alive")

        fut: Future = Future()
        q_tuple = tuple(float(v) for v in q)
        self._queue.put((q_tuple, float(clearance_m), fut))
        # 5s is generous; one query against a 6-DOF arm is normally << 5 ms.
        # If the worker is hung we treat the query as a collision so OMPL
        # aborts the candidate rather than busy-looping on more queries.
        try:
            return bool(fut.result(timeout=5.0))
        except FuturesTimeoutError:
            _LOG.warning(
                "CollisionChecker.is_collision timed out after 5s for robot=%s; "
                "treating as collision",
                self._scene.robot_id,
            )
            return True

    def make_validity_fn(self) -> Callable[[Sequence[float]], bool]:
        """Return a callable suitable for OMPL ``StateValidityCheckerFn``.

        The returned function returns ``True`` for *valid* states (i.e. not
        in collision) — matching OMPL's convention. The clearance is fixed
        to ``0.0``; the sampler passes its own clearance through the
        underlying call when it constructs the actual validity check (see
        :mod:`src.planning.samplers`).
        """

        def _validity(state: Sequence[float]) -> bool:
            return not self.is_collision(state, clearance_m=0.0)

        return _validity

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Shut the worker thread down. Idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(_SHUTDOWN)
        self._thread.join(timeout=5.0)

    def __enter__(self) -> "CollisionChecker":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - GC fallback
        try:
            self.close()
        except Exception:
            pass


__all__ = ["CollisionChecker"]
