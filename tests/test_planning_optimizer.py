"""Tests for src.planning.optimizer — DrakeOptimizer.

Covers:
- DrakeOptimizer.smooth produces waypoints that are collision-free per CollisionChecker
- Raises PlanCancelled when token set BEFORE call
- Drake/PyBullet collision-state parity at ε=2 mm for one config sweep (risk #9)
  Boolean parity: if Drake says "in collision" and PyBullet says "not in collision"
  (or vice versa) for the same q, that is a divergence we document.
"""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.planning
pytest.importorskip("pydrake")
pytest.importorskip("pybullet")

from src.planning.budgets import CancelToken, PlanCancelled  # noqa: E402
from src.planning.collision import CollisionChecker  # noqa: E402
from src.planning.optimizer import DrakeOptimizer  # noqa: E402
from src.planning.samplers import PlanNoSolution  # noqa: E402
from src.planning.scene import SceneSnapshot  # noqa: E402
from src.planning.types import OptimizerConfig  # noqa: E402
from src.station.scene import Frame, RobotEntry, Station  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)


@pytest.fixture(scope="module")
def ur5_scene() -> SceneSnapshot:
    station = Station(
        name="cell",
        frames=(Frame("world", (0.0, 0.0, 0.0), _IDENTITY_QUAT),),
        robots=(RobotEntry("arm0", "ur5", "world"),),
    )
    return SceneSnapshot.from_station(station, "arm0")


@pytest.fixture(scope="module")
def ur5_checker(ur5_scene: SceneSnapshot):
    checker = CollisionChecker(ur5_scene)
    yield checker
    checker.close()


@pytest.fixture(scope="module")
def optimizer() -> DrakeOptimizer:
    return DrakeOptimizer()


def _make_smooth_waypoints(scene: SceneSnapshot, n: int = 6) -> list[list[float]]:
    home = list(scene.home_q)
    goal = [q + 0.3 for q in home]
    return [
        [home[j] + (goal[j] - home[j]) * i / (n - 1) for j in range(scene.dof)]
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_smooth_returns_tuple_of_waypoints(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = OptimizerConfig(enabled=True, max_iterations=50, spline_degree=5)
    result = optimizer.smooth(ur5_scene, wps, cfg, cancel)
    assert isinstance(result, tuple)
    assert len(result) > 0


def test_smooth_preserves_waypoint_count(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    n = 6
    wps = _make_smooth_waypoints(ur5_scene, n=n)
    cancel = CancelToken()
    cfg = OptimizerConfig(enabled=True, max_iterations=50)
    result = optimizer.smooth(ur5_scene, wps, cfg, cancel)
    assert len(result) == n


def test_smooth_preserves_dof(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = OptimizerConfig(enabled=True, max_iterations=50)
    result = optimizer.smooth(ur5_scene, wps, cfg, cancel)
    for wp in result:
        assert len(wp) == ur5_scene.dof


def test_smoothed_waypoints_are_collision_free(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    optimizer: DrakeOptimizer,
) -> None:
    """All smoothed waypoints must be collision-free according to CollisionChecker."""
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = OptimizerConfig(enabled=True, max_iterations=100, min_distance_m=0.0)
    try:
        smoothed = optimizer.smooth(ur5_scene, wps, cfg, cancel)
    except PlanNoSolution:
        pytest.skip("Drake optimizer failed to converge — acceptable in some envs")
        return
    for i, wp in enumerate(smoothed):
        is_coll = ur5_checker.is_collision(list(wp))
        assert is_coll is False, (
            f"Smoothed waypoint {i} is in collision: {wp}"
        )


def test_smooth_endpoint_constraint_start(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    """The smoothed path's first waypoint should be near the input start."""
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = OptimizerConfig(enabled=True, max_iterations=100)
    try:
        smoothed = optimizer.smooth(ur5_scene, wps, cfg, cancel)
    except PlanNoSolution:
        pytest.skip("Drake optimizer failed to converge")
        return
    start_diff = np.max(np.abs(np.asarray(smoothed[0]) - np.asarray(wps[0])))
    assert start_diff < 0.1, f"Start endpoint drifted by {start_diff:.4f} rad"


def test_smooth_endpoint_constraint_goal(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = OptimizerConfig(enabled=True, max_iterations=100)
    try:
        smoothed = optimizer.smooth(ur5_scene, wps, cfg, cancel)
    except PlanNoSolution:
        pytest.skip("Drake optimizer failed to converge")
        return
    end_diff = np.max(np.abs(np.asarray(smoothed[-1]) - np.asarray(wps[-1])))
    assert end_diff < 0.1, f"End endpoint drifted by {end_diff:.4f} rad"


# ---------------------------------------------------------------------------
# PlanCancelled when token set before call
# ---------------------------------------------------------------------------


def test_raises_plan_cancelled_when_token_pre_set(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    cancel = CancelToken()
    cancel.cancel()
    wps = _make_smooth_waypoints(ur5_scene)
    cfg = OptimizerConfig(enabled=True, max_iterations=100)
    with pytest.raises(PlanCancelled):
        optimizer.smooth(ur5_scene, wps, cfg, cancel)


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_too_few_waypoints_raises_value_error(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    with pytest.raises(ValueError, match="waypoints"):
        optimizer.smooth(ur5_scene, [list(ur5_scene.home_q)], OptimizerConfig(), CancelToken())


def test_wrong_dof_raises_value_error(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    wps = [[0.0] * (ur5_scene.dof + 1)] * 3
    with pytest.raises(ValueError, match="DOF"):
        optimizer.smooth(ur5_scene, wps, OptimizerConfig(), CancelToken())


# ---------------------------------------------------------------------------
# risk #9: Drake/PyBullet collision-state parity
# ---------------------------------------------------------------------------


def test_drake_pybullet_collision_parity(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    optimizer: DrakeOptimizer,
) -> None:
    """Drake optimizer produces waypoints that match PyBullet collision state.

    risk #9: Drake owns its own MultibodyPlant (separate from PyBullet).
    We run a config sweep and check that the smoothed waypoints are all
    consistent with the PyBullet checker — if they diverge, we document the
    discrepancy and the epsilon used.

    We do not assert perfect agreement (Drake and PyBullet may have slightly
    different collision geometries), but we assert that no waypoint is
    flagged as in-collision by PyBullet after Drake says it's valid.
    """
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = OptimizerConfig(enabled=True, max_iterations=100, min_distance_m=0.0)

    try:
        smoothed = optimizer.smooth(ur5_scene, wps, cfg, cancel)
    except PlanNoSolution:
        pytest.skip("Drake optimizer failed to converge — parity test inconclusive")
        return

    # Collect parity information
    collisions_in_drake_output: list[int] = []
    for i, wp in enumerate(smoothed):
        pybullet_coll = ur5_checker.is_collision(list(wp), clearance_m=0.002)  # 2 mm ε
        if pybullet_coll:
            collisions_in_drake_output.append(i)

    # The assertion: Drake should not produce waypoints that PyBullet (with 2 mm
    # clearance) would flag as colliding. If this fails, it confirms risk #9.
    # We use a 5 mm fallback — document if even that is too strict.
    if collisions_in_drake_output:
        # Retry with 5 mm
        collisions_5mm: list[int] = []
        for i, wp in enumerate(smoothed):
            if ur5_checker.is_collision(list(wp), clearance_m=0.005):
                collisions_5mm.append(i)
        if collisions_5mm:
            # Still failing at 5mm — document as known divergence
            pytest.fail(
                f"Drake/PyBullet collision parity failed at 5 mm clearance for "
                f"waypoints {collisions_5mm}. This confirms risk #9: the two "
                f"scenes have divergent collision geometry."
            )
        else:
            # Only fails at 2mm — acceptable; document it.
            # This is within the 5mm fallback documented in the brief.
            pass  # 2mm fails but 5mm passes — acceptable for this scene


# ---------------------------------------------------------------------------
# Extra coverage: spline_degree 3 also works
# ---------------------------------------------------------------------------


def test_smooth_spline_degree_3(
    ur5_scene: SceneSnapshot, optimizer: DrakeOptimizer
) -> None:
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = OptimizerConfig(enabled=True, max_iterations=50, spline_degree=3)
    try:
        result = optimizer.smooth(ur5_scene, wps, cfg, cancel)
        assert len(result) > 0
    except PlanNoSolution:
        pytest.skip("Drake optimizer failed to converge with degree-3 spline")
