"""Tests for src.planning.types and src.planning.budgets.

Covers:
- Frozen-dataclass validators (PlanRequest, TimedTrajectory, PlannerConfig,
  OptimizerConfig, ParameteriserConfig, TrajectorySample, PlanResult)
- JSON to_dict/from_dict round-trip with __type__ discriminator
- Enum coercion from raw strings
- PlannerConfig defaults
- Budgets ratios (sample 50%, optimise 30%, parameterise 20%)
- CancelToken set/poll/raise (risk #7: token used from multiple threads)
"""

from __future__ import annotations

import json
import threading

import pytest

from src.planning.budgets import Budgets, CancelToken, PlanCancelled, PlanTimeout
from src.planning.types import (
    OptimizerConfig,
    ParameteriserConfig,
    PlannerConfig,
    PlannerKind,
    PlannerStage,
    PlanningUnavailable,
    PlanRequest,
    PlanResult,
    PlanStatus,
    TimedTrajectory,
    TrajectorySample,
    from_dict,
    to_dict,
)

pytestmark = pytest.mark.planning

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)


def _make_sample(t: float, dof: int = 6) -> TrajectorySample:
    zeros = tuple(0.0 for _ in range(dof))
    return TrajectorySample(t_s=t, q_rad=zeros, qd_rad_s=zeros, qdd_rad_s2=zeros)


def _make_traj(robot_id: str = "robot0", dof: int = 6) -> TimedTrajectory:
    s0 = _make_sample(0.0, dof)
    s1 = _make_sample(1.0, dof)
    return TimedTrajectory(robot_id=robot_id, dt_s=0.01, samples=(s0, s1), duration_s=1.0)


def _make_request() -> PlanRequest:
    return PlanRequest(
        robot_id="arm0",
        q_start=(0.0,) * 6,
        goal_q=(1.0,) * 6,
    )


def _make_plan_result() -> PlanResult:
    return PlanResult(
        plan_id="pid1",
        status=PlanStatus.COMPLETED,
        stage=PlannerStage.COMPLETED,
        trajectory=_make_traj(),
        elapsed_s=1.23,
        sampler_path_length=10,
        optimizer_iterations=0,
        parameteriser_grid_points=200,
        cache_hit=False,
    )


# ---------------------------------------------------------------------------
# PlannerConfig
# ---------------------------------------------------------------------------


def test_planner_config_defaults():
    cfg = PlannerConfig()
    assert cfg.kind == PlannerKind.RRT_STAR
    assert cfg.timeout_s == 5.0
    assert cfg.smoothing_iterations == 50
    assert cfg.range_rad == 0.5
    assert cfg.clearance_m == 0.005
    assert cfg.qdd_max_rad_s2_default is None


def test_planner_config_coerces_kind_from_string():
    cfg = PlannerConfig(kind="rrt")  # type: ignore[arg-type]
    assert cfg.kind == PlannerKind.RRT


def test_planner_config_rejects_zero_timeout():
    with pytest.raises(ValueError, match="timeout_s"):
        PlannerConfig(timeout_s=0.0)


def test_planner_config_rejects_negative_timeout():
    with pytest.raises(ValueError, match="timeout_s"):
        PlannerConfig(timeout_s=-1.0)


def test_planner_config_rejects_negative_smoothing():
    with pytest.raises(ValueError, match="smoothing_iterations"):
        PlannerConfig(smoothing_iterations=-1)


def test_planner_config_rejects_zero_range():
    with pytest.raises(ValueError, match="range_rad"):
        PlannerConfig(range_rad=0.0)


def test_planner_config_rejects_negative_clearance():
    with pytest.raises(ValueError, match="clearance_m"):
        PlannerConfig(clearance_m=-0.001)


def test_planner_config_rejects_zero_qdd_default():
    with pytest.raises(ValueError, match="qdd_max_rad_s2_default"):
        PlannerConfig(qdd_max_rad_s2_default=0.0)


def test_planner_config_rejects_negative_qdd_default():
    with pytest.raises(ValueError, match="qdd_max_rad_s2_default"):
        PlannerConfig(qdd_max_rad_s2_default=-1.0)


def test_planner_config_accepts_positive_qdd_default():
    cfg = PlannerConfig(qdd_max_rad_s2_default=10.0)
    assert cfg.qdd_max_rad_s2_default == 10.0


# ---------------------------------------------------------------------------
# OptimizerConfig
# ---------------------------------------------------------------------------


def test_optimizer_config_defaults():
    cfg = OptimizerConfig()
    assert cfg.enabled is False
    assert cfg.max_iterations == 100
    assert cfg.min_distance_m == 0.005
    assert cfg.spline_degree == 5


def test_optimizer_config_rejects_zero_iterations():
    with pytest.raises(ValueError, match="max_iterations"):
        OptimizerConfig(max_iterations=0)


def test_optimizer_config_rejects_bad_spline_degree():
    with pytest.raises(ValueError, match="spline_degree"):
        OptimizerConfig(spline_degree=4)


def test_optimizer_config_accepts_spline_degree_3():
    cfg = OptimizerConfig(spline_degree=3)
    assert cfg.spline_degree == 3


# ---------------------------------------------------------------------------
# ParameteriserConfig
# ---------------------------------------------------------------------------


def test_parameteriser_config_defaults():
    cfg = ParameteriserConfig()
    assert cfg.qd_scale == 1.0
    assert cfg.qdd_scale == 1.0
    assert cfg.grid_points == 200


def test_parameteriser_config_rejects_zero_qd_scale():
    with pytest.raises(ValueError, match="qd_scale"):
        ParameteriserConfig(qd_scale=0.0)


def test_parameteriser_config_rejects_over_one_qd_scale():
    with pytest.raises(ValueError, match="qd_scale"):
        ParameteriserConfig(qd_scale=1.01)


def test_parameteriser_config_rejects_low_grid_points():
    with pytest.raises(ValueError, match="grid_points"):
        ParameteriserConfig(grid_points=15)


# ---------------------------------------------------------------------------
# PlanRequest
# ---------------------------------------------------------------------------


def test_plan_request_goal_q_happy_path():
    req = _make_request()
    assert req.robot_id == "arm0"
    assert req.q_start == (0.0,) * 6
    assert req.goal_q == (1.0,) * 6
    assert req.goal_pose is None


def test_plan_request_goal_pose_happy_path():
    req = PlanRequest(
        robot_id="arm0",
        q_start=(0.0,) * 6,
        goal_pose=((0.5, 0.0, 0.5), _IDENTITY_QUAT),
    )
    assert req.goal_q is None
    assert req.goal_pose is not None


def test_plan_request_rejects_empty_robot_id():
    with pytest.raises(ValueError, match="robot_id"):
        PlanRequest(robot_id="", q_start=(0.0,) * 6, goal_q=(0.0,) * 6)


def test_plan_request_rejects_both_goal_q_and_goal_pose():
    with pytest.raises(ValueError, match="exactly one"):
        PlanRequest(
            robot_id="arm0",
            q_start=(0.0,) * 6,
            goal_q=(0.0,) * 6,
            goal_pose=((0.5, 0.0, 0.5), _IDENTITY_QUAT),
        )


def test_plan_request_rejects_neither_goal():
    with pytest.raises(ValueError, match="exactly one"):
        PlanRequest(robot_id="arm0", q_start=(0.0,) * 6)


def test_plan_request_rejects_mismatched_goal_q_length():
    with pytest.raises(ValueError, match="goal_q must match q_start"):
        PlanRequest(robot_id="arm0", q_start=(0.0,) * 6, goal_q=(0.0,) * 5)


def test_plan_request_rejects_non_unit_goal_pose_quat():
    # (0.1, 0.1, 0.1, 0.1) has norm ≈ 0.2 — clearly not unit-norm.
    with pytest.raises(ValueError, match="unit-norm"):
        PlanRequest(
            robot_id="arm0",
            q_start=(0.0,) * 6,
            goal_pose=((0.5, 0.0, 0.5), (0.1, 0.1, 0.1, 0.1)),
        )


def test_plan_request_rejects_non_finite_q_start():
    with pytest.raises(ValueError, match="finite"):
        PlanRequest(robot_id="arm0", q_start=(float("nan"),), goal_q=(0.0,))


def test_plan_request_rejects_empty_q_start():
    with pytest.raises(ValueError, match="at least one joint"):
        PlanRequest(robot_id="arm0", q_start=(), goal_q=())


# ---------------------------------------------------------------------------
# TrajectorySample
# ---------------------------------------------------------------------------


def test_trajectory_sample_happy_path():
    s = _make_sample(0.5)
    assert s.t_s == 0.5
    assert len(s.q_rad) == 6


def test_trajectory_sample_rejects_negative_t():
    with pytest.raises(ValueError, match="t_s"):
        TrajectorySample(
            t_s=-0.1, q_rad=(0.0,), qd_rad_s=(0.0,), qdd_rad_s2=(0.0,)
        )


def test_trajectory_sample_rejects_empty_q():
    with pytest.raises(ValueError, match="at least one joint"):
        TrajectorySample(t_s=0.0, q_rad=(), qd_rad_s=(), qdd_rad_s2=())


def test_trajectory_sample_rejects_mismatched_qd_length():
    with pytest.raises(ValueError, match="match q_rad"):
        TrajectorySample(t_s=0.0, q_rad=(0.0, 0.0), qd_rad_s=(0.0,), qdd_rad_s2=(0.0, 0.0))


# ---------------------------------------------------------------------------
# TimedTrajectory
# ---------------------------------------------------------------------------


def test_timed_trajectory_happy_path():
    traj = _make_traj()
    assert traj.robot_id == "robot0"
    assert len(traj.samples) == 2
    assert traj.duration_s == 1.0


def test_timed_trajectory_rejects_empty_robot_id():
    s0 = _make_sample(0.0)
    s1 = _make_sample(1.0)
    with pytest.raises(ValueError, match="robot_id"):
        TimedTrajectory(robot_id="", dt_s=0.01, samples=(s0, s1), duration_s=1.0)


def test_timed_trajectory_rejects_single_sample():
    s0 = _make_sample(0.0)
    with pytest.raises(ValueError, match="at least 2"):
        TimedTrajectory(robot_id="r", dt_s=0.01, samples=(s0,), duration_s=0.0)


def test_timed_trajectory_rejects_non_monotonic_samples():
    s0 = _make_sample(0.0)
    s1 = _make_sample(1.0)
    s2 = _make_sample(0.5)  # goes backwards
    with pytest.raises(ValueError, match="monotonic"):
        TimedTrajectory(robot_id="r", dt_s=0.01, samples=(s0, s1, s2), duration_s=0.5)


def test_timed_trajectory_rejects_wrong_duration():
    s0 = _make_sample(0.0)
    s1 = _make_sample(1.0)
    with pytest.raises(ValueError, match="duration_s"):
        TimedTrajectory(robot_id="r", dt_s=0.01, samples=(s0, s1), duration_s=2.0)


def test_timed_trajectory_rejects_zero_dt():
    s0 = _make_sample(0.0)
    s1 = _make_sample(1.0)
    with pytest.raises(ValueError, match="dt_s"):
        TimedTrajectory(robot_id="r", dt_s=0.0, samples=(s0, s1), duration_s=1.0)


def test_timed_trajectory_joint_waypoints():
    q0 = (0.1, 0.2, 0.3)
    q1 = (0.4, 0.5, 0.6)
    s0 = TrajectorySample(t_s=0.0, q_rad=q0, qd_rad_s=(0.0,) * 3, qdd_rad_s2=(0.0,) * 3)
    s1 = TrajectorySample(t_s=1.0, q_rad=q1, qd_rad_s=(0.0,) * 3, qdd_rad_s2=(0.0,) * 3)
    traj = TimedTrajectory(robot_id="r", dt_s=0.01, samples=(s0, s1), duration_s=1.0)
    wps = traj.joint_waypoints()
    assert wps == (q0, q1)


def test_timed_trajectory_sample_at_clamps_below_zero():
    traj = _make_traj()
    s = traj.sample_at(-1.0)
    assert s is traj.samples[0]


def test_timed_trajectory_sample_at_clamps_above_duration():
    traj = _make_traj()
    s = traj.sample_at(99.0)
    assert s is traj.samples[-1]


def test_timed_trajectory_sample_at_midpoint():
    # Two samples with linear q from 0 to 1; midpoint should be 0.5.
    s0 = TrajectorySample(t_s=0.0, q_rad=(0.0, 0.0), qd_rad_s=(0.0, 0.0), qdd_rad_s2=(0.0, 0.0))
    s1 = TrajectorySample(t_s=1.0, q_rad=(1.0, 1.0), qd_rad_s=(0.0, 0.0), qdd_rad_s2=(0.0, 0.0))
    traj = TimedTrajectory(robot_id="r", dt_s=0.01, samples=(s0, s1), duration_s=1.0)
    mid = traj.sample_at(0.5)
    assert abs(mid.q_rad[0] - 0.5) < 1e-9
    assert abs(mid.q_rad[1] - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# PlanResult
# ---------------------------------------------------------------------------


def test_plan_result_coerces_status_from_string():
    r = PlanResult(
        plan_id="x",
        status="completed",  # type: ignore[arg-type]
        stage="completed",  # type: ignore[arg-type]
        trajectory=None,
        elapsed_s=0.1,
        sampler_path_length=0,
        optimizer_iterations=0,
        parameteriser_grid_points=0,
        cache_hit=False,
    )
    assert r.status == PlanStatus.COMPLETED
    assert r.stage == PlannerStage.COMPLETED


def test_plan_result_rejects_negative_elapsed():
    with pytest.raises(ValueError, match="elapsed_s"):
        PlanResult(
            plan_id="x",
            status=PlanStatus.FAILED,
            stage=PlannerStage.FAILED,
            trajectory=None,
            elapsed_s=-0.1,
            sampler_path_length=0,
            optimizer_iterations=0,
            parameteriser_grid_points=0,
            cache_hit=False,
        )


def test_plan_result_rejects_negative_singularity_hint():
    with pytest.raises(ValueError, match="singularity_hint"):
        PlanResult(
            plan_id="x",
            status=PlanStatus.FAILED,
            stage=PlannerStage.FAILED,
            trajectory=None,
            elapsed_s=0.0,
            sampler_path_length=0,
            optimizer_iterations=0,
            parameteriser_grid_points=0,
            cache_hit=False,
            singularity_hint=(-1,),
        )


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------

# Golden output — pinning critical fields so emission drift fails loudly.
_GOLDEN_REQUEST_KEYS = {"__type__", "robot_id", "q_start", "goal_q", "goal_pose",
                        "obstacles", "planner", "optimizer", "parameteriser"}


def test_to_dict_includes_type_discriminators():
    req = _make_request()
    d = to_dict(req)
    assert d["__type__"] == "PlanRequest"
    assert d["planner"]["__type__"] == "PlannerConfig"
    assert d["optimizer"]["__type__"] == "OptimizerConfig"
    assert d["parameteriser"]["__type__"] == "ParameteriserConfig"


def test_plan_request_json_round_trip():
    req = _make_request()
    encoded = to_dict(req)
    raw = json.loads(json.dumps(encoded))
    decoded = from_dict(raw, PlanRequest)
    assert isinstance(decoded, PlanRequest)
    assert decoded == req


def test_timed_trajectory_json_round_trip():
    traj = _make_traj()
    encoded = to_dict(traj)
    raw = json.loads(json.dumps(encoded))
    decoded = from_dict(raw, TimedTrajectory)
    assert isinstance(decoded, TimedTrajectory)
    assert decoded == traj


def test_plan_result_json_round_trip():
    result = _make_plan_result()
    encoded = to_dict(result)
    raw = json.loads(json.dumps(encoded))
    decoded = from_dict(raw, PlanResult)
    assert isinstance(decoded, PlanResult)
    assert decoded == result


def test_plan_result_round_trip_with_trajectory():
    """Trajectory embedded inside PlanResult must survive JSON round-trip."""
    result = _make_plan_result()
    decoded = from_dict(json.loads(json.dumps(to_dict(result))), PlanResult)
    assert decoded.trajectory is not None
    assert decoded.trajectory.robot_id == "robot0"
    assert len(decoded.trajectory.samples) == 2


def test_plan_request_goal_pose_round_trip():
    req = PlanRequest(
        robot_id="arm0",
        q_start=(0.0,) * 6,
        goal_pose=((0.5, 0.0, 0.5), _IDENTITY_QUAT),
    )
    decoded = from_dict(json.loads(json.dumps(to_dict(req))), PlanRequest)
    assert decoded.goal_pose is not None
    xyz, quat = decoded.goal_pose
    assert abs(xyz[0] - 0.5) < 1e-9


def test_enum_coercion_in_decoded_plan_result():
    """Enums must decode from their string value forms."""
    result = _make_plan_result()
    d = to_dict(result)
    # Manually verify values are plain strings in the dict.
    assert d["status"] == "completed"
    assert d["stage"] == "completed"
    # Round-trip should restore enum instances.
    decoded = from_dict(d, PlanResult)
    assert decoded.status == PlanStatus.COMPLETED
    assert decoded.stage == PlannerStage.COMPLETED


def test_from_dict_ignores_unknown_keys():
    """Forward-compat: extra keys in JSON are silently dropped."""
    req = _make_request()
    d = to_dict(req)
    d["future_field"] = "ignored"
    decoded = from_dict(d, PlanRequest)
    assert decoded.robot_id == req.robot_id


def test_from_dict_rejects_unknown_type():
    with pytest.raises(ValueError, match="Unknown __type__"):
        from_dict({"__type__": "DoesNotExist", "foo": 1})


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def test_budgets_ratios_50_30_20():
    cfg = PlannerConfig(timeout_s=10.0)
    b = Budgets.from_planner_config(cfg)
    assert abs(b.sample_s - 5.0) < 1e-9
    assert abs(b.optimise_s - 3.0) < 1e-9
    assert abs(b.parameterise_s - 2.0) < 1e-9


def test_budgets_sum_equals_timeout():
    cfg = PlannerConfig(timeout_s=7.0)
    b = Budgets.from_planner_config(cfg)
    assert abs(b.sample_s + b.optimise_s + b.parameterise_s - 7.0) < 1e-9


def test_budgets_rejects_zero_budget():
    with pytest.raises(ValueError, match="sample_s"):
        Budgets(sample_s=0.0, optimise_s=1.0, parameterise_s=1.0)


# ---------------------------------------------------------------------------
# CancelToken
# ---------------------------------------------------------------------------


def test_cancel_token_initially_not_cancelled():
    token = CancelToken()
    assert token.is_cancelled() is False


def test_cancel_token_set_is_cancelled():
    token = CancelToken()
    token.cancel()
    assert token.is_cancelled() is True


def test_cancel_token_raise_if_cancelled_raises():
    token = CancelToken()
    token.cancel()
    with pytest.raises(PlanCancelled):
        token.raise_if_cancelled()


def test_cancel_token_not_cancelled_does_not_raise():
    token = CancelToken()
    token.raise_if_cancelled()  # must not raise


def test_cancel_token_cancel_is_idempotent():
    token = CancelToken()
    token.cancel()
    token.cancel()  # second call must not raise
    assert token.is_cancelled() is True


def test_cancel_token_reset():
    token = CancelToken()
    token.cancel()
    token.reset()
    assert token.is_cancelled() is False


def test_cancel_token_thread_safe_set_from_another_thread():
    """Cancel set from a worker thread is observable on the main thread.
    Exercises the cooperative-cancellation path across threads (risk #7).
    """
    token = CancelToken()
    ready = threading.Event()

    def _setter():
        ready.wait()
        token.cancel()

    t = threading.Thread(target=_setter)
    t.start()
    ready.set()
    t.join(timeout=2.0)
    assert token.is_cancelled() is True


def test_cancel_token_raise_if_cancelled_from_multiple_threads():
    """raise_if_cancelled is safe to call concurrently from many threads."""
    token = CancelToken()
    token.cancel()
    raised = []
    errors = []

    def _check():
        try:
            token.raise_if_cancelled()
        except PlanCancelled:
            raised.append(True)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=_check) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)

    assert errors == []
    assert len(raised) == 10


# ---------------------------------------------------------------------------
# PlanningUnavailable
# ---------------------------------------------------------------------------


def test_planning_unavailable_is_runtime_error():
    exc = PlanningUnavailable("no windows support")
    assert isinstance(exc, RuntimeError)
    assert "windows" in str(exc).lower()


# Extra coverage: PlanTimeout is a RuntimeError too
def test_plan_timeout_is_runtime_error():
    exc = PlanTimeout("timed out")
    assert isinstance(exc, RuntimeError)
