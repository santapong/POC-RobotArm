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
from typing import TYPE_CHECKING, Any, Callable, Sequence

import numpy as np

from src.motion.frames import SE3_from_pose as _SE3_from_pose  # noqa: F401
from src.motion.ir import PoseTarget

if TYPE_CHECKING:  # pragma: no cover - typing only
    import roboticstoolbox as _rtb  # noqa: F401


_EPS = 1.0e-9


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
    prev_row: list[tuple[np.ndarray, float] | None] | None = None,
    is_valid: Callable[[np.ndarray], bool] | None = None,
) -> list[tuple[np.ndarray, float] | None]:
    """Return ``(q, manipulability)`` per phi for one waypoint, index-aligned.

    The returned list has one entry per phi, with ``None`` where no acceptable
    solution was found, so entry ``k`` means "the phi-``k`` configuration" at
    every waypoint. That alignment is the point: the DP trellis compares
    candidate ``k`` at waypoint ``i`` against candidate ``j`` at ``i-1``, and
    those comparisons are only meaningful if a given index tracks one IK
    branch along the path.

    Seeding is therefore chained twice over:

    * across phi, each solve is seeded from the previous phi's solution, so the
      fan itself is continuous rather than a scatter of unrelated branches;
    * across waypoints, phi ``k`` is seeded from phi ``k`` of ``prev_row``.

    Seeding every phi from one shared configuration (the previous behaviour)
    let ``ik_LM`` land in a different branch per phi and per waypoint. On a
    UR5, consecutive waypoints 20 mm apart produced same-index candidates a
    mean of 1.5 rad and as much as 8.3 rad apart, which makes every trellis
    edge weight fiction.

    ``is_valid`` is an optional predicate applied to each accepted solution.
    Without it this function screens only on joint limits and manipulability,
    which says nothing about the world the arm is standing in: on a real cell
    the resulting path drove the forearm through the benchtop for 20% of its
    waypoints. A caller with a planning scene passes a checker here so
    colliding configurations never enter the trellis at all, rather than being
    discovered after the DP has already committed to them.
    """
    qlim = np.asarray(getattr(robot, "qlim", np.empty((2, 0))), dtype=float)
    fallback = np.zeros(robot.n) if q_seed is None else np.asarray(q_seed, dtype=float)

    out: list[tuple[np.ndarray, float] | None] = []
    walking = fallback  # seed chained along phi
    for k, phi in enumerate(phis):
        if prev_row is not None and k < len(prev_row) and prev_row[k] is not None:
            seed = prev_row[k][0]
        else:
            seed = walking

        T = _spin_about_local_z(target, float(phi))
        try:
            q, success, _iters, _searches, _residual = robot.ik_LM(T, q0=seed)
        except Exception:
            out.append(None)
            continue
        if not success:
            out.append(None)
            continue
        q = np.asarray(q, dtype=float)
        if not _q_within_limits(q, qlim):
            out.append(None)
            continue
        m = _manipulability(robot, q)
        if m < manipulability_min:
            out.append(None)
            continue
        if is_valid is not None and not is_valid(q):
            out.append(None)
            continue

        out.append((q, float(m)))
        walking = q
    return out


def _manip_penalty(m: float, m_ref: float, weight: float, cap: float) -> float:
    """Bounded, scale-free penalty for a low-manipulability configuration.

    The previous cost added ``weight / m`` directly to ``||dq||``. Those two
    terms have no common scale: manipulability is not dimensionless and its
    magnitude depends entirely on the robot and the region of its workspace.
    On a UR5 at a comfortable pose ``1/m`` is about 13 while a typical step is
    about 0.13 rad, so the DP was optimising manipulability alone and ignoring
    smoothness — the exact opposite of what a redundancy resolver is for. On a
    small arm with ``m ~ 0.006`` the ratio reaches four orders of magnitude.

    Referencing each candidate against the median manipulability of the whole
    trellis makes the penalty dimensionless: a median-or-better configuration
    scores 0, and a worse one is charged in units comparable to radians of
    joint travel. ``cap`` stops a near-singular candidate from dominating the
    path the way an unbounded reciprocal does.
    """
    if weight <= 0.0 or m_ref <= _EPS:
        return 0.0
    ratio = m_ref / max(m, _EPS)
    return weight * float(min(max(ratio - 1.0, 0.0), cap))


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
    manip_penalty_cap: float = 10.0,
    is_valid: Callable[[np.ndarray], bool] | None = None,
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
        manip_weight: Scale on the per-waypoint manipulability penalty. The
            penalty is referenced to the median manipulability of the whole
            trellis, so it is dimensionless and comparable to radians of joint
            travel on any robot. Pass 0 for pure smoothness.
        manip_penalty_cap: Ceiling on that penalty, in the same units. Stops a
            single near-singular candidate from dominating the whole path.
        is_valid: Optional predicate ``q -> bool`` applied to every candidate.
            This optimizer otherwise knows nothing about the world around the
            arm — it screens on joint limits and manipulability only — so a
            caller holding a planning scene should pass a collision check here.
            Candidates that fail never enter the trellis. Note it is called
            once per (waypoint, phi), so a slow check is felt: a 365-waypoint
            path with a 30-degree fan is roughly 4400 calls.

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

    # Build the trellis. Rows are index-aligned across waypoints (None where a
    # phi has no acceptable solution) so that candidate k means the same branch
    # at every waypoint; see _ik_candidates.
    rows: list[list[tuple[np.ndarray, float] | None]] = []
    seed = np.zeros(robot.n)
    prev_row: list[tuple[np.ndarray, float] | None] | None = None
    for i, wp in enumerate(waypoints):
        row = _ik_candidates(
            robot,
            wp,
            phis,
            manipulability_min=manipulability_min,
            q_seed=seed,
            prev_row=prev_row,
            is_valid=is_valid,
        )
        if not any(c is not None for c in row):
            hint = " (is_valid rejected every candidate?)" if is_valid else ""
            raise ValueError(
                f"optimize_joints: waypoint {i} has zero feasible candidates{hint}"
            )
        rows.append(row)
        prev_row = row
        # Carry a fallback seed forward for any phi the next row cannot chain.
        seed = next(c[0] for c in row if c is not None)

    # Reference manipulability for the penalty: the median over every accepted
    # candidate. Using the path's own scale keeps the penalty comparable to
    # ||dq|| on any robot, rather than depending on the absolute magnitude of
    # a quantity that varies by orders of magnitude between arms.
    all_m = [c[1] for row in rows for c in row if c is not None]
    m_ref = float(np.median(all_m)) if all_m else 0.0

    n = len(rows)
    cost: list[list[float]] = [[math.inf] * len(rows[i]) for i in range(n)]
    parent: list[list[int]] = [[-1] * len(rows[i]) for i in range(n)]

    for k, c in enumerate(rows[0]):
        if c is not None:
            cost[0][k] = _manip_penalty(c[1], m_ref, manip_weight, manip_penalty_cap)

    for i in range(1, n):
        for k, ck in enumerate(rows[i]):
            if ck is None:
                continue
            qk = ck[0]
            best, best_p = math.inf, -1
            for j, cj in enumerate(rows[i - 1]):
                if cj is None or not math.isfinite(cost[i - 1][j]):
                    continue
                total = cost[i - 1][j] + travel_weight * float(
                    np.linalg.norm(qk - cj[0])
                )
                if total < best:
                    best, best_p = total, j
            if best_p < 0:
                continue
            cost[i][k] = best + _manip_penalty(
                ck[1], m_ref, manip_weight, manip_penalty_cap
            )
            parent[i][k] = best_p

    finite = [k for k, c in enumerate(cost[-1]) if math.isfinite(c)]
    if not finite:
        raise ValueError("optimize_joints: no feasible joint trajectory found")
    end_k = min(finite, key=lambda k: cost[-1][k])

    indices_rev: list[int] = [end_k]
    for i in range(n - 1, 0, -1):
        end_k = parent[i][end_k]
        indices_rev.append(end_k)
    indices = list(reversed(indices_rev))

    return [tuple(float(v) for v in rows[i][k][0]) for i, k in enumerate(indices)]


__all__ = ["optimize_joints"]
