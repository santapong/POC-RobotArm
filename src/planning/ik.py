"""Inverse kinematics with quantised LRU seed cache.

Wraps PyBullet's damped-least-squares IK (via :class:`RobotArmSim`) and
caches the (xyz, quat) → q solution under a key quantised to 1 mm /
0.01 wxyz (gap-report §I item: warm-start cache for repeated goal-pose
planning). The cache uses :class:`collections.OrderedDict` so we can
expose hits / misses for tests; :func:`functools.lru_cache` is avoided
because it does not.

Notes
-----
* Module top imports stdlib only; PyBullet is imported inside
  :meth:`IKSolver.__init__` so :mod:`src.planning.ik` stays importable on
  Windows.
* The cache is keyed by ``(scene.fingerprint, xyz_quantised, quat_quantised)``
  so two scenes with the same robot but different obstacles do not
  cross-contaminate.
* ``residual_tol_m`` defaults to 5 mm; callers requiring tighter accuracy
  pass their own.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Sequence

from src.planning.scene import SceneSnapshot
from src.planning.types import PlanningUnavailable

# Quantisation grid for seed-cache hits. 1 mm + 0.01 wxyz matches the
# specification in §A: "LRU keyed by (robot_id, target_xyz_quantised_to_1mm)".
_XYZ_GRID_M = 1e-3
_QUAT_GRID = 1e-2


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
    """PyBullet-backed IK with a quantised LRU seed cache."""

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
        self._lock = threading.Lock()

        # Build a private PyBullet client owned by this solver. RobotArmSim
        # is imported here (lazy) so the module top stays cheap for the
        # Windows guard.
        from src.simulation.engine import RobotArmSim

        self._sim = RobotArmSim(
            robot_name=scene.robot_catalog_name, use_gui=False
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
        """
        key = (
            self._scene.fingerprint,
            _quantise_xyz(target_xyz_m),
            _quantise_quat(target_quat_wxyz),
        )

        seed_used: list[float] | None = None
        seed_was_cache_hit = False
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._hits += 1
                seed_used = list(cached)
                seed_was_cache_hit = True
            else:
                self._misses += 1
                if q_seed is not None:
                    seed_used = [float(v) for v in q_seed]

        # PyBullet expects (x, y, z, w); the IR carries (w, x, y, z).
        quat_xyzw = (
            float(target_quat_wxyz[1]),
            float(target_quat_wxyz[2]),
            float(target_quat_wxyz[3]),
            float(target_quat_wxyz[0]),
        )

        # Seed the simulator's joint state so PyBullet's IK starts there.
        if seed_used is not None:
            pad = max(0, self._sim.num_joints - len(seed_used))
            self._sim.reset_joint_angles(seed_used + [0.0] * pad)

        q = self._sim.solve_ik(
            target_position=list(target_xyz_m),
            target_orientation=list(quat_xyzw),
        )

        # Drive the sim to q and measure residual against the achieved EE pose.
        pad = max(0, self._sim.num_joints - len(q))
        self._sim.reset_joint_angles(list(q) + [0.0] * pad)
        ee_pos, _ee_quat_xyzw = self._sim.get_end_effector_pose()
        residual_m = math.sqrt(
            sum((float(a) - float(b)) ** 2 for a, b in zip(ee_pos, target_xyz_m))
        )

        if residual_m > self._residual_tol_m:
            raise PlanningIKUnreachable(
                f"IK residual {residual_m:.6f} m exceeds tolerance "
                f"{self._residual_tol_m:.6f} m for target {target_xyz_m}"
            )

        q_tuple = tuple(float(v) for v in q)
        with self._lock:
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
        with self._lock:
            return self._hits, self._misses

    def close(self) -> None:
        """Disconnect the private PyBullet client."""
        try:
            self._sim.disconnect()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["IKSolver", "IKResult", "PlanningIKUnreachable"]
