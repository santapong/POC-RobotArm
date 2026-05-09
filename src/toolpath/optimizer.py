"""Redundancy-resolution optimizer — fan candidates and DP a smooth path.

Given a sequence of Cartesian waypoints (:class:`PoseTarget`), this
module fans out a set of candidate joint configurations per waypoint by
spinning the tool around its own Z axis ("tool roll" — the redundant
axis for most milling, deburring, and inspection processes). It then
runs a dynamic-programming search across the resulting trellis to pick
the per-waypoint configuration that minimises a cost combining

* joint-space travel: ``||q_k - q_{k-1}||_W`` (Euclidean, identity weights),
* manipulability penalty: ``lambda / max(eps, manipulability(q_k))``.

The result is a smooth, kinematically-clean joint trajectory — exactly
what Robotmaster-class CAM software produces with their per-waypoint
"axis 7" optimisation. The IK solver is :func:`rtb.Robot.ik_LM`; the
import is lazy so callers without ``roboticstoolbox`` can still use the
rest of the toolpath package.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from src.motion.ir import PoseTarget

if TYPE_CHECKING:  # pragma: no cover - typing only
    import roboticstoolbox as _rtb  # noqa: F401


_EPS = 1.0e-9


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


def _quat_wxyz_to_rotmat(q: Sequence[float]) -> np.ndarray:
    """Convert a unit-norm wxyz quaternion to a 3x3 rotation matrix."""
    w, x, y, z = (float(c) for c in q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def _SE3_from_pose(target: PoseTarget) -> Any:
    """Build a spatialmath SE3 from a PoseTarget (lazy import)."""
    from spatialmath import SE3
    R = _quat_wxyz_to_rotmat(target.quat_wxyz)
    return SE3.Rt(R, np.asarray(target.xyz_m, dtype=float))


def _spin_about_local_z(target: PoseTarget, phi: float) -> Any:
    """Return ``SE3(target) * Rz(phi)`` — rotate the tool about its local Z."""
    from spatialmath import SE3
    base = _SE3_from_pose(target)
    return base * SE3.Rz(phi)


def _q_within_limits(q: np.ndarray, qlim: np.ndarray) -> bool:
    """Check that joint vector ``q`` lies inside ``qlim`` (shape ``(2, n)``)."""
    if qlim is None or qlim.size == 0:
        return True
    lo = qlim[0]
    hi = qlim[1]
    return bool(np.all(q >= lo - 1e-9) and np.all(q <= hi + 1e-9))


def _manipulability(robot: Any, q: np.ndarray) -> float:
    """Yoshikawa manipulability index. Returns 0.0 if the call fails."""
    try:
        return float(robot.manipulability(q))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


def _ik_candidates(
    robot: Any,
    target: PoseTarget,
    phis: np.ndarray,
    manipulability_min: float,
    q_seed: np.ndarray | None,
) -> list[tuple[np.ndarray, float]]:
    """Return a list of ``(q, manipulability)`` for one waypoint.

    For each phi, run ``ik_LM`` with the spun tool pose and discard the
    solution if it fails, falls outside joint limits, or has
    manipulability below ``manipulability_min``.
    """
    cands: list[tuple[np.ndarray, float]] = []
    qlim = np.asarray(getattr(robot, "qlim", np.empty((2, 0))), dtype=float)
    seed = np.zeros(robot.n) if q_seed is None else np.asarray(q_seed, dtype=float)
    for phi in phis:
        T = _spin_about_local_z(target, float(phi))
        try:
            q, success, _iters, _searches, _residual = robot.ik_LM(T, q0=seed)
        except Exception:
            continue
        if not success:
            continue
        q = np.asarray(q, dtype=float)
        if not _q_within_limits(q, qlim):
            continue
        m = _manipulability(robot, q)
        if m < manipulability_min:
            continue
        cands.append((q, m))
    return cands


# ---------------------------------------------------------------------------
# Public optimizer
# ---------------------------------------------------------------------------


def optimize_joints(
    robot: Any,
    waypoints: Sequence[PoseTarget],
    free_axis: str = "z",
    phi_step_deg: float = 5.0,
    manipulability_min: float = 0.01,
    travel_weight: float = 1.0,
    manip_weight: float = 1.0,
) -> list[tuple[float, ...]]:
    """Run the DP trellis to pick joint configurations along ``waypoints``.

    Args:
        robot: A :class:`roboticstoolbox.Robot` (rtb is imported lazily by
            the caller; this function expects a ready-to-use object).
        waypoints: Cartesian targets to follow, in order.
        free_axis: Which tool axis to spin about for the redundancy fan.
            Currently only ``"z"`` is supported (and is the convention
            for almost every CAM redundancy resolution).
        phi_step_deg: Sampling resolution for the spin angle (degrees).
        manipulability_min: Drop candidates whose Yoshikawa
            manipulability is below this threshold.
        travel_weight: Scale on the ``||Δq||`` cost between adjacent
            waypoints.
        manip_weight: Scale on the per-waypoint ``1 / manipulability``
            penalty.

    Returns:
        A list of joint-configuration tuples, one per input waypoint.

    Raises:
        ValueError: if ``waypoints`` is empty, ``free_axis`` is unknown,
            or any waypoint has zero feasible candidates.
    """
    if not waypoints:
        raise ValueError("optimize_joints: waypoints is empty")
    if free_axis.lower() != "z":
        raise ValueError(
            f"optimize_joints: free_axis={free_axis!r} not supported (use 'z')"
        )
    if phi_step_deg <= 0.0:
        raise ValueError(f"optimize_joints: phi_step_deg must be > 0, got {phi_step_deg}")

    # Sample phi over [0, 2*pi).
    n_phi = max(1, int(round(360.0 / phi_step_deg)))
    phis = np.linspace(0.0, 2.0 * math.pi, n_phi, endpoint=False)

    # Build trellis: per-waypoint list of (q, manipulability).
    trellis: list[list[tuple[np.ndarray, float]]] = []
    seed = np.zeros(robot.n)
    for i, wp in enumerate(waypoints):
        cands = _ik_candidates(
            robot,
            wp,
            phis,
            manipulability_min=manipulability_min,
            q_seed=seed,
        )
        if not cands:
            raise ValueError(
                f"optimize_joints: waypoint {i} has zero feasible candidates"
            )
        trellis.append(cands)
        # Seed next waypoint's IK from the smoothest (highest-manip) cand.
        seed = max(cands, key=lambda c: c[1])[0]

    # DP forward pass: cost[i][k] = best total cost reaching waypoint i, cand k.
    n = len(trellis)
    cost: list[list[float]] = [[math.inf] * len(trellis[i]) for i in range(n)]
    parent: list[list[int]] = [[-1] * len(trellis[i]) for i in range(n)]
    # Initialize first column: only manipulability term (no predecessor).
    for k, (_, m) in enumerate(trellis[0]):
        cost[0][k] = manip_weight / max(m, _EPS)
    for i in range(1, n):
        for k, (qk, mk) in enumerate(trellis[i]):
            best = math.inf
            best_p = -1
            for j, (qj, _) in enumerate(trellis[i - 1]):
                step = travel_weight * float(np.linalg.norm(qk - qj))
                total = cost[i - 1][j] + step
                if total < best:
                    best = total
                    best_p = j
            cost[i][k] = best + manip_weight / max(mk, _EPS)
            parent[i][k] = best_p

    # Backtrack from the cheapest terminal.
    final_costs = cost[-1]
    end_k = int(np.argmin(final_costs))
    if not math.isfinite(final_costs[end_k]):
        raise ValueError("optimize_joints: no feasible joint trajectory found")

    indices_rev: list[int] = [end_k]
    for i in range(n - 1, 0, -1):
        end_k = parent[i][end_k]
        indices_rev.append(end_k)
    indices = list(reversed(indices_rev))

    return [tuple(float(v) for v in trellis[i][k][0]) for i, k in enumerate(indices)]


__all__ = ["optimize_joints"]
