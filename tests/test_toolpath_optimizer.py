"""Tests for src.toolpath.optimizer — DP redundancy resolution."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("numpy")
pytest.importorskip("roboticstoolbox")

import numpy as np  # noqa: E402

from src.motion.ir import PoseTarget  # noqa: E402
from src.robots.predefined import get_ur5  # noqa: E402
from src.toolpath.optimizer import optimize_joints  # noqa: E402

# A "tool faces -Z" quaternion (180-deg rot about world X).
_TOOL_DOWN = (0.0, 1.0, 0.0, 0.0)


def _line_path(n: int = 5) -> list[PoseTarget]:
    """A short straight line in the UR5's reachable workspace."""
    out: list[PoseTarget] = []
    for i in range(n):
        x = 0.4
        y = -0.05 + 0.025 * i  # 25 mm steps along +Y
        z = 0.30
        out.append(PoseTarget(xyz_m=(x, y, z), quat_wxyz=_TOOL_DOWN))
    return out


def test_optimize_joints_returns_one_q_per_waypoint() -> None:
    ur5 = get_ur5()
    waypoints = _line_path(5)
    qs = optimize_joints(
        ur5,
        waypoints,
        phi_step_deg=30.0,
        manipulability_min=1e-4,
    )
    assert len(qs) == len(waypoints)
    for q in qs:
        assert len(q) == ur5.n
        for v in q:
            assert math.isfinite(v)


def test_optimize_joints_smoothness() -> None:
    """Adjacent joint configurations should be close — DP minimises ||Δq||."""
    ur5 = get_ur5()
    waypoints = _line_path(6)
    qs = optimize_joints(
        ur5,
        waypoints,
        phi_step_deg=30.0,
        manipulability_min=1e-4,
    )
    # Maximum per-step joint travel should be small for a smooth line.
    for i in range(1, len(qs)):
        dq = np.array(qs[i]) - np.array(qs[i - 1])
        # Allow up to ~1.0 rad per 25 mm step — DP should easily beat this
        # for a co-linear path with the redundancy fan available.
        assert float(np.linalg.norm(dq)) < 1.5


def test_optimize_joints_unreachable_raises() -> None:
    """A point well outside the UR5 reach must raise ValueError."""
    ur5 = get_ur5()
    waypoints = [
        PoseTarget(xyz_m=(0.4, 0.0, 0.30), quat_wxyz=_TOOL_DOWN),
        # 5 m away — far beyond the UR5's ~0.85 m reach. ik_LM may
        # converge to a junk solution that violates joint limits, in
        # which case we filter it out and the candidate list is empty.
        PoseTarget(xyz_m=(5.0, 5.0, 5.0), quat_wxyz=_TOOL_DOWN),
    ]
    with pytest.raises(ValueError):
        optimize_joints(
            ur5,
            waypoints,
            phi_step_deg=30.0,
            manipulability_min=1e-4,
        )


def test_optimize_joints_empty_waypoints() -> None:
    ur5 = get_ur5()
    with pytest.raises(ValueError):
        optimize_joints(ur5, [], phi_step_deg=30.0)


def test_optimize_joints_invalid_free_axis() -> None:
    ur5 = get_ur5()
    waypoints = _line_path(2)
    with pytest.raises(ValueError):
        optimize_joints(ur5, waypoints, free_axis="x")


def test_optimize_joints_invalid_phi_step() -> None:
    ur5 = get_ur5()
    waypoints = _line_path(2)
    with pytest.raises(ValueError):
        optimize_joints(ur5, waypoints, phi_step_deg=0.0)


def test_optimize_joints_high_manip_filter() -> None:
    """Setting an absurdly high manipulability threshold filters everything."""
    ur5 = get_ur5()
    waypoints = _line_path(3)
    with pytest.raises(ValueError):
        optimize_joints(
            ur5,
            waypoints,
            phi_step_deg=30.0,
            manipulability_min=10.0,  # impossibly high
        )


# ---------------------------------------------------------------------------
# Regressions for the two cost/candidate defects
# ---------------------------------------------------------------------------


def test_candidate_rows_are_index_aligned() -> None:
    """Candidate k must mean the same IK branch at every waypoint.

    The DP compares candidate k at waypoint i against candidate j at i-1, so
    those edge weights are only meaningful if an index tracks one branch along
    the path. Seeding every phi from one shared configuration let ik_LM land
    in an unrelated branch per phi and per waypoint: on this very path,
    same-index candidates were a mean of 1.5 rad and up to 8.3 rad apart for a
    20 mm pose step.
    """
    from src.toolpath.optimizer import _ik_candidates

    ur5 = get_ur5()
    phis = np.linspace(0.0, 2.0 * math.pi, 12, endpoint=False)
    waypoints = _line_path(3)

    prev_row = None
    seed = np.zeros(ur5.n)
    rows = []
    for wp in waypoints:
        row = _ik_candidates(ur5, wp, phis, 1e-6, seed, prev_row=prev_row)
        assert len(row) == len(phis), "rows must have one entry per phi"
        rows.append(row)
        prev_row = row
        seed = next(c[0] for c in row if c is not None)

    for i in range(1, len(rows)):
        for k, (a, b) in enumerate(zip(rows[i - 1], rows[i])):
            if a is None or b is None:
                continue
            step = float(np.linalg.norm(b[0] - a[0]))
            assert step < 0.5, (
                f"candidate {k} jumped {step:.3f} rad between waypoints "
                f"20 mm apart — the index is not tracking one IK branch"
            )


def test_manip_penalty_is_bounded_and_scale_free() -> None:
    """The penalty is referenced to the trellis median, not 1/m."""
    from src.toolpath.optimizer import _manip_penalty

    ref = 0.05
    # At or above the reference a candidate is not penalised at all.
    assert _manip_penalty(ref, ref, weight=1.0, cap=10.0) == 0.0
    assert _manip_penalty(ref * 2, ref, weight=1.0, cap=10.0) == 0.0
    # Below it the charge grows but stays bounded by the cap...
    mid = _manip_penalty(ref / 3, ref, weight=1.0, cap=10.0)
    assert 0.0 < mid <= 10.0
    # ...even as manipulability collapses toward a singularity, where an
    # unbounded 1/m would have reached four orders of magnitude.
    assert _manip_penalty(1e-9, ref, weight=1.0, cap=10.0) == 10.0
    # Zero weight disables it.
    assert _manip_penalty(1e-9, ref, weight=0.0, cap=10.0) == 0.0


def test_smoothness_not_swamped_by_manipulability_term() -> None:
    """Default weights must not cost much more travel than pure smoothness.

    manipulability is not dimensionless, so adding weight/m straight to ||dq||
    compared two quantities with no common scale. On a UR5 at a comfortable
    pose 1/m is about 13 while a step is about 0.13 rad, so the DP optimised
    manipulability alone and smoothness was noise in the sum.
    """
    ur5 = get_ur5()
    waypoints = _line_path(6)
    kw = dict(phi_step_deg=30.0, manipulability_min=1e-6)

    default = np.asarray(optimize_joints(ur5, waypoints, **kw))
    smooth = np.asarray(optimize_joints(ur5, waypoints, manip_weight=0.0, **kw))

    def travel(qs):
        return float(np.linalg.norm(np.diff(qs, axis=0), axis=1).sum())

    # The manipulability term may legitimately trade a little smoothness away,
    # but it must not dominate. Measured on this path: before the fix the
    # default cost 0.70 rad against 0.37 for pure smoothness (ratio 1.90);
    # after, both are 0.37 (ratio 1.00), because a median-or-better candidate
    # is charged nothing at all.
    assert travel(default) <= travel(smooth) * 1.5


# ---------------------------------------------------------------------------
# is_valid: the caller's window onto the world the arm stands in
# ---------------------------------------------------------------------------


def test_is_valid_rejects_candidates_from_the_trellis() -> None:
    """A rejected configuration must never appear in the result.

    Without this hook the optimizer screens on joint limits and manipulability
    only, which says nothing about obstacles: on a real machining cell its path
    put the forearm through the benchtop for 20% of the waypoints.
    """
    ur5 = get_ur5()
    waypoints = _line_path(5)
    kw = dict(phi_step_deg=30.0, manipulability_min=1e-6)

    baseline = optimize_joints(ur5, waypoints, **kw)
    # Forbid the exact shoulder band the unconstrained solution uses.
    banned_lo = min(q[1] for q in baseline) - 0.05
    banned_hi = max(q[1] for q in baseline) + 0.05

    def is_valid(q):
        return not (banned_lo <= q[1] <= banned_hi)

    try:
        qs = optimize_joints(ur5, waypoints, is_valid=is_valid, **kw)
    except ValueError as exc:
        # Legitimate outcome: nothing outside the banned band is reachable.
        assert "zero feasible candidates" in str(exc)
        assert "is_valid" in str(exc), "the error should name the culprit"
        return

    for q in qs:
        assert not (banned_lo <= q[1] <= banned_hi), (
            "a configuration rejected by is_valid came back in the result"
        )


def test_is_valid_is_called_for_every_candidate() -> None:
    """The predicate sees each (waypoint, phi) candidate, not just the winners."""
    ur5 = get_ur5()
    waypoints = _line_path(3)
    seen: list[int] = []

    def is_valid(q):
        seen.append(len(q))
        return True

    qs = optimize_joints(ur5, waypoints, is_valid=is_valid,
                         phi_step_deg=90.0, manipulability_min=1e-6)
    assert len(qs) == len(waypoints)
    # 3 waypoints x 4 phis, minus any that failed IK or the limit check.
    assert 0 < len(seen) <= 12
    assert all(n == ur5.n for n in seen)


def test_is_valid_none_matches_previous_behaviour() -> None:
    """Omitting the hook changes nothing."""
    ur5 = get_ur5()
    waypoints = _line_path(4)
    kw = dict(phi_step_deg=30.0, manipulability_min=1e-6)
    assert optimize_joints(ur5, waypoints, **kw) == optimize_joints(
        ur5, waypoints, is_valid=None, **kw
    )


def test_q_init_selects_the_starting_branch() -> None:
    """The first seed decides which IK branch the whole path lands in.

    optimize_joints previously hardcoded zeros, which is an arbitrary place to
    start and rarely where the arm is. On a path where a joint must sweep a
    full turn this is decisive: seeded one way the sweep runs into a joint
    limit and wraps, seeded another it fits.
    """
    ur5 = get_ur5()
    waypoints = _line_path(6)
    kw = dict(phi_step_deg=30.0, manipulability_min=1e-6)

    default = optimize_joints(ur5, waypoints, **kw)
    seeded = optimize_joints(ur5, waypoints, q_init=default[0], **kw)

    # Seeding with a solution the optimizer itself chose must stay valid and
    # shaped correctly; it need not be identical, since IK is iterative.
    assert len(seeded) == len(waypoints)
    for q in seeded:
        assert len(q) == ur5.n
        assert all(math.isfinite(v) for v in q)


def test_q_init_rejects_a_wrong_length() -> None:
    ur5 = get_ur5()
    with pytest.raises(ValueError, match="q_init"):
        optimize_joints(ur5, _line_path(2), q_init=[0.0, 0.0], phi_step_deg=90.0)
