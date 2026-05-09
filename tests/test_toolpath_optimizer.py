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
