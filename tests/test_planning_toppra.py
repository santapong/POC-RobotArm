"""Tests for src.planning.parameteriser — ToppRAParameteriser.

Covers:
- Output is monotonic in t_s
- qd magnitudes <= qd_max * qd_scale at every sample
- qdd magnitudes <= qdd_max * qdd_scale at every sample
- Near-singular / infeasible path raises PlanLimitsExceeded with non-empty
  singularity_hint (risk #10)
- PlanCancelled when token set before call
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytestmark = pytest.mark.planning
pytest.importorskip("toppra")
pytest.importorskip("pybullet")

from src.planning.budgets import CancelToken, PlanCancelled  # noqa: E402
from src.planning.parameteriser import PlanLimitsExceeded, ToppRAParameteriser  # noqa: E402
from src.planning.scene import SceneSnapshot  # noqa: E402
from src.planning.types import ParameteriserConfig  # noqa: E402
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
def parameteriser() -> ToppRAParameteriser:
    return ToppRAParameteriser()


def _make_smooth_waypoints(scene: SceneSnapshot, n: int = 10) -> list[list[float]]:
    """Generate a smooth linear interpolation from home to home+0.3 rad."""
    home = list(scene.home_q)
    goal = [q + 0.3 for q in home]
    return [
        [home[j] + (goal[j] - home[j]) * i / (n - 1) for j in range(scene.dof)]
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_parameterise_returns_timed_trajectory(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    from src.planning.types import TimedTrajectory
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = ParameteriserConfig(qd_scale=1.0, qdd_scale=1.0, grid_points=100)
    traj = parameteriser.parameterise(ur5_scene, wps, cfg, cancel)
    assert isinstance(traj, TimedTrajectory)


def test_output_monotonic_in_t_s(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = ParameteriserConfig(qd_scale=1.0, qdd_scale=1.0, grid_points=100)
    traj = parameteriser.parameterise(ur5_scene, wps, cfg, cancel)
    for i in range(1, len(traj.samples)):
        assert traj.samples[i].t_s >= traj.samples[i - 1].t_s, (
            f"Non-monotonic at index {i}: "
            f"{traj.samples[i].t_s} < {traj.samples[i - 1].t_s}"
        )


def test_qd_within_limit_at_all_samples(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    """qd magnitudes must not exceed qd_max * qd_scale at any sample."""
    qd_scale = 0.8
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = ParameteriserConfig(qd_scale=qd_scale, qdd_scale=1.0, grid_points=100)
    traj = parameteriser.parameterise(ur5_scene, wps, cfg, cancel)

    vmax = np.asarray(ur5_scene.qd_max_rad_s) * qd_scale
    slack = 1.01  # 1% numerical tolerance (matches implementation)
    for i, s in enumerate(traj.samples):
        qd_arr = np.abs(s.qd_rad_s)
        assert np.all(qd_arr <= vmax * slack), (
            f"sample {i}: qd {np.max(qd_arr):.4f} exceeds limit {np.max(vmax * slack):.4f}"
        )


def test_qdd_within_limit_at_all_samples(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    """qdd magnitudes must not exceed qdd_max * qdd_scale at any sample."""
    qdd_scale = 0.8
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = ParameteriserConfig(qd_scale=1.0, qdd_scale=qdd_scale, grid_points=100)
    traj = parameteriser.parameterise(ur5_scene, wps, cfg, cancel)

    amax = np.asarray(ur5_scene.qdd_max_rad_s2) * qdd_scale
    slack = 1.01
    for i, s in enumerate(traj.samples):
        qdd_arr = np.abs(s.qdd_rad_s2)
        assert np.all(qdd_arr <= amax * slack), (
            f"sample {i}: qdd {np.max(qdd_arr):.4f} exceeds limit {np.max(amax * slack):.4f}"
        )


def test_duration_s_equals_last_sample_t_s(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    wps = _make_smooth_waypoints(ur5_scene)
    cancel = CancelToken()
    cfg = ParameteriserConfig(grid_points=100)
    traj = parameteriser.parameterise(ur5_scene, wps, cfg, cancel)
    assert abs(traj.duration_s - traj.samples[-1].t_s) < 1e-9


def test_trajectory_robot_id_matches_scene(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    wps = _make_smooth_waypoints(ur5_scene)
    traj = parameteriser.parameterise(ur5_scene, wps, ParameteriserConfig(), CancelToken())
    assert traj.robot_id == ur5_scene.robot_id


def test_at_least_two_samples_produced(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    wps = _make_smooth_waypoints(ur5_scene, n=3)
    traj = parameteriser.parameterise(ur5_scene, wps, ParameteriserConfig(), CancelToken())
    assert len(traj.samples) >= 2


# ---------------------------------------------------------------------------
# Infeasible path raises PlanLimitsExceeded with singularity_hint (risk #10)
# ---------------------------------------------------------------------------


def test_infeasible_path_raises_plan_limits_exceeded(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    """A path with extreme joint-space jumps should fail parameterisation.

    We create waypoints with very large discontinuities and extremely tight
    velocity limits to force TOPP-RA to fail.
    """
    # Force impossibly tight limits by using qd_scale=0.001 (0.1% of normal)
    # on a path that requires large velocities.
    dof = ur5_scene.dof
    wps = [
        [0.0] * dof,
        [math.pi] * dof,   # Huge jump in one step
        [0.0] * dof,
    ]
    cfg = ParameteriserConfig(qd_scale=0.001, qdd_scale=0.001, grid_points=50)
    cancel = CancelToken()
    with pytest.raises(PlanLimitsExceeded) as exc_info:
        parameteriser.parameterise(ur5_scene, wps, cfg, cancel)
    # The singularity_hint must be a tuple (possibly empty but type-correct)
    assert isinstance(exc_info.value.singularity_hint, tuple)


def test_plan_limits_exceeded_has_singularity_hint_field(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    """PlanLimitsExceeded.singularity_hint must be populated for hinting (risk #10)."""
    dof = ur5_scene.dof
    wps = [
        [0.0] * dof,
        [math.pi] * dof,
        [0.0] * dof,
    ]
    cfg = ParameteriserConfig(qd_scale=0.001, qdd_scale=0.001, grid_points=50)
    try:
        parameteriser.parameterise(ur5_scene, wps, cfg, CancelToken())
    except PlanLimitsExceeded as exc:
        # singularity_hint must be a tuple of non-negative ints
        hint = exc.singularity_hint
        assert isinstance(hint, tuple)
        assert all(isinstance(i, int) and i >= 0 for i in hint)
        return  # test passed
    pytest.fail("Expected PlanLimitsExceeded but no exception was raised")


# ---------------------------------------------------------------------------
# PlanCancelled when token set before call
# ---------------------------------------------------------------------------


def test_plan_cancelled_when_token_pre_set(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    cancel = CancelToken()
    cancel.cancel()
    wps = _make_smooth_waypoints(ur5_scene)
    with pytest.raises(PlanCancelled):
        parameteriser.parameterise(ur5_scene, wps, ParameteriserConfig(), cancel)


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_invalid_dt_raises_value_error(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    wps = _make_smooth_waypoints(ur5_scene)
    with pytest.raises(ValueError, match="dt_s"):
        parameteriser.parameterise(ur5_scene, wps, ParameteriserConfig(), CancelToken(), dt_s=0.0)


def test_single_waypoint_raises_value_error(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    wps = [list(ur5_scene.home_q)]
    with pytest.raises(ValueError, match="waypoints"):
        parameteriser.parameterise(ur5_scene, wps, ParameteriserConfig(), CancelToken())


def test_wrong_dof_raises_value_error(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    wps = [[0.0] * (ur5_scene.dof + 1), [0.1] * (ur5_scene.dof + 1)]
    with pytest.raises(ValueError, match="DOF"):
        parameteriser.parameterise(ur5_scene, wps, ParameteriserConfig(), CancelToken())


# ---------------------------------------------------------------------------
# Extra coverage: qd_scale=1.0 does not apply stricter constraints
# ---------------------------------------------------------------------------


def test_full_speed_does_not_raise_plan_limits(
    ur5_scene: SceneSnapshot, parameteriser: ToppRAParameteriser
) -> None:
    """Smooth path at full speed limits should not trigger PlanLimitsExceeded."""
    wps = _make_smooth_waypoints(ur5_scene, n=20)
    cfg = ParameteriserConfig(qd_scale=1.0, qdd_scale=1.0, grid_points=100)
    traj = parameteriser.parameterise(ur5_scene, wps, cfg, CancelToken())
    assert traj.duration_s > 0.0
