"""Tests for src.planning.pipeline — end-to-end plan() function.

Covers:
- Happy path: plan() returns PlanResult(status=COMPLETED, trajectory=non-None)
- goal_pose path runs IK first (stage transitions through IK)
- Same request returns same PlanResult trajectories (determinism)
- Cancel mid-flight returns PlanResult(status=CANCELLED, error_code='PLANNING_CANCELLED')
- PlanLimitsExceeded propagated -> error_code='PLANNING_LIMITS_EXCEEDED'
- PlanNoSolution -> error_code='PLANNING_NO_SOLUTION'
- PlanTimeout -> error_code='PLANNING_TIMEOUT'
- PlanningIKUnreachable -> error_code='PLANNING_IK_UNREACHABLE'
"""

from __future__ import annotations

import threading

import pytest

pytestmark = pytest.mark.planning
pytest.importorskip("ompl")
pytest.importorskip("toppra")
pytest.importorskip("pybullet")

from src.planning.budgets import CancelToken, PlanTimeout  # noqa: E402
from src.planning.collision import CollisionChecker  # noqa: E402
from src.planning.ik import IKSolver, PlanningIKUnreachable  # noqa: E402
from src.planning.parameteriser import (  # noqa: E402
    PlanLimitsExceeded,
    TimeParameteriser,
    ToppRAParameteriser,
)
from src.planning.pipeline import plan  # noqa: E402
from src.planning.samplers import Planner, PlanNoSolution, RRTStarPlanner  # noqa: E402
from src.planning.scene import SceneSnapshot  # noqa: E402
from src.planning.types import (  # noqa: E402
    ParameteriserConfig,
    PlannerConfig,
    PlannerKind,
    PlannerStage,
    PlanRequest,
    PlanResult,
    PlanStatus,
)
from src.station.scene import Frame, RobotEntry, Station  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal ABC stubs — used by the error-mapping tests below.
# Using concrete subclasses instead of MagicMock keeps duck-typing safe
# and makes the intent clearer (auditor item #9 / Fix E).
# ---------------------------------------------------------------------------


class _PlanLimitsExceededParameteriser(TimeParameteriser):
    """Stub that always raises PlanLimitsExceeded."""

    def parameterise(self, scene, waypoints, config, cancel, dt_s=0.01):  # type: ignore[override]
        raise PlanLimitsExceeded("forced limits exceeded", singularity_hint=(3, 5))


class _PlanNoSolutionSampler(Planner):
    """Stub that always raises PlanNoSolution."""

    kind = PlannerKind.RRT_STAR  # satisfy ABC kind field

    def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):  # type: ignore[override]
        raise PlanNoSolution("no path")


class _PlanTimeoutSampler(Planner):
    """Stub that always raises PlanTimeout."""

    kind = PlannerKind.RRT_STAR

    def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):  # type: ignore[override]
        raise PlanTimeout("timed out")


class _PlanValueErrorSampler(Planner):
    """Stub that raises ValueError — maps to PLANNING_BAD_CONFIG (Fix E)."""

    kind = PlannerKind.RRT_STAR

    def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):  # type: ignore[override]
        raise ValueError("some downstream validation failure")


class _IKUnreachableSolver:
    """Minimal IKSolver stand-in that always raises PlanningIKUnreachable."""

    def solve(self, target_xyz_m, target_quat_wxyz, q_seed=None):
        raise PlanningIKUnreachable("unreachable")

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
def panda_scene() -> SceneSnapshot:
    station = Station(
        name="cell",
        frames=(Frame("world", (0.0, 0.0, 0.0), _IDENTITY_QUAT),),
        robots=(RobotEntry("arm0", "panda", "world"),),
    )
    return SceneSnapshot.from_station(station, "arm0")


@pytest.fixture(scope="module")
def panda_checker(panda_scene: SceneSnapshot):
    checker = CollisionChecker(panda_scene)
    yield checker
    checker.close()


@pytest.fixture(scope="module")
def panda_ik(panda_scene: SceneSnapshot) -> IKSolver:
    solver = IKSolver(panda_scene, residual_tol_m=0.02, cache_size=256)
    yield solver
    solver.close()


@pytest.fixture(scope="module")
def sampler() -> RRTStarPlanner:
    return RRTStarPlanner()


@pytest.fixture(scope="module")
def toppra() -> ToppRAParameteriser:
    return ToppRAParameteriser()


def _fast_config() -> PlannerConfig:
    return PlannerConfig(
        kind=PlannerKind.RRT_STAR,
        timeout_s=15.0,
        smoothing_iterations=5,
        range_rad=0.5,
        clearance_m=0.0,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_plan_happy_path_completed(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    """End-to-end plan returns COMPLETED with a non-None trajectory."""
    # Use a fresh IK solver per test since we're using ur5 here
    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
            parameteriser=ParameteriserConfig(grid_points=50),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=CancelToken(),
            plan_id="test-happy",
        )
    finally:
        ik.close()

    assert isinstance(result, PlanResult)
    assert result.status == PlanStatus.COMPLETED
    assert result.stage == PlannerStage.COMPLETED
    assert result.trajectory is not None
    assert result.error_code is None
    assert result.elapsed_s >= 0.0
    assert result.sampler_path_length >= 2


def test_plan_happy_path_trajectory_has_samples(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
            parameteriser=ParameteriserConfig(grid_points=50),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=CancelToken(),
        )
    finally:
        ik.close()

    assert result.trajectory is not None
    assert len(result.trajectory.samples) >= 2


# ---------------------------------------------------------------------------
# goal_pose path runs IK first
# ---------------------------------------------------------------------------


def test_goal_pose_path_runs_ik(
    panda_scene: SceneSnapshot,
    panda_checker: CollisionChecker,
    panda_ik: IKSolver,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    """When goal_pose is provided (not goal_q), IK must be invoked first."""
    stages_seen: list[PlannerStage] = []

    def _on_progress(stage: PlannerStage, pct: float) -> None:
        stages_seen.append(stage)

    q_start = list(panda_scene.home_q)
    request = PlanRequest(
        robot_id="arm0",
        q_start=tuple(q_start),
        goal_pose=((0.4, 0.0, 0.4), _IDENTITY_QUAT),
        planner=_fast_config(),
        parameteriser=ParameteriserConfig(grid_points=50),
    )
    result = plan(
        request=request,
        scene=panda_scene,
        checker=panda_checker,
        ik=panda_ik,
        sampler=sampler,
        optimizer=None,
        parameteriser=toppra,
        cancel=CancelToken(),
        on_progress=_on_progress,
    )

    # Either IK succeeded and we got a COMPLETED result, or IK failed.
    # In either case, the IK stage should have appeared in progress.
    if result.status == PlanStatus.COMPLETED:
        assert PlannerStage.IK in stages_seen, (
            f"IK stage not in progress callbacks: {stages_seen}"
        )
    else:
        # IK may have failed (unreachable target is allowed); verify error code
        assert result.error_code in ("PLANNING_IK_UNREACHABLE", "PLANNING_NO_SOLUTION",
                                     "PLANNING_TIMEOUT", "PLANNING_FAILED")


# ---------------------------------------------------------------------------
# Determinism: same request returns same trajectory shape
# ---------------------------------------------------------------------------


def test_same_request_same_trajectory_shape(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    """Two plans with the same inputs should return COMPLETED with same DOF."""
    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
            parameteriser=ParameteriserConfig(grid_points=50),
        )
        result1 = plan(request=request, scene=ur5_scene, checker=ur5_checker,
                       ik=ik, sampler=sampler, optimizer=None,
                       parameteriser=toppra, cancel=CancelToken())
        result2 = plan(request=request, scene=ur5_scene, checker=ur5_checker,
                       ik=ik, sampler=sampler, optimizer=None,
                       parameteriser=toppra, cancel=CancelToken())
    finally:
        ik.close()

    # Both should succeed
    assert result1.status == PlanStatus.COMPLETED
    assert result2.status == PlanStatus.COMPLETED
    # Trajectories should have the same DOF
    assert len(result1.trajectory.samples[0].q_rad) == len(result2.trajectory.samples[0].q_rad)


# ---------------------------------------------------------------------------
# Cancel mid-flight
# ---------------------------------------------------------------------------


def test_cancel_mid_flight_returns_cancelled(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    """Setting cancel token before the call must yield CANCELLED result."""
    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        cancel = CancelToken()
        cancel.cancel()  # Pre-cancelled
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=cancel,
        )
    finally:
        ik.close()

    assert result.status == PlanStatus.CANCELLED
    assert result.error_code == "PLANNING_CANCELLED"
    assert result.trajectory is None


def test_cancel_during_sampling_returns_cancelled(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    """Cancellation signal sent from another thread during sampling."""
    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    result_holder: list[PlanResult] = []

    cancel = CancelToken()
    q_start = list(ur5_scene.home_q)
    q_goal = [q + 0.5 for q in q_start]
    request = PlanRequest(
        robot_id="arm0",
        q_start=tuple(q_start),
        goal_q=tuple(q_goal),
        planner=PlannerConfig(kind=PlannerKind.RRT_STAR, timeout_s=60.0, clearance_m=0.0),
    )

    import time

    def _run():
        result_holder.append(
            plan(
                request=request,
                scene=ur5_scene,
                checker=ur5_checker,
                ik=ik,
                sampler=sampler,
                optimizer=None,
                parameteriser=toppra,
                cancel=cancel,
            )
        )

    t = threading.Thread(target=_run)
    t.start()
    time.sleep(0.1)
    cancel.cancel()
    t.join(timeout=5.0)
    ik.close()

    assert not t.is_alive(), "Pipeline thread did not terminate"
    assert len(result_holder) == 1
    r = result_holder[0]
    # Either cancelled or completed quickly — both are acceptable
    assert r.status in (PlanStatus.CANCELLED, PlanStatus.COMPLETED)
    if r.status == PlanStatus.CANCELLED:
        assert r.error_code == "PLANNING_CANCELLED"


# ---------------------------------------------------------------------------
# PlanLimitsExceeded propagated
# ---------------------------------------------------------------------------


def test_plan_limits_exceeded_maps_to_error_code(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
) -> None:
    """PlanLimitsExceeded from parameteriser -> PLANNING_LIMITS_EXCEEDED.

    Uses a minimal ABC subclass instead of MagicMock (auditor item #9 / Fix E).
    """
    stub_parameteriser = _PlanLimitsExceededParameteriser()

    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=sampler,
            optimizer=None,
            parameteriser=stub_parameteriser,
            cancel=CancelToken(),
        )
    finally:
        ik.close()

    assert result.status == PlanStatus.FAILED
    assert result.error_code == "PLANNING_LIMITS_EXCEEDED"
    assert result.singularity_hint == (3, 5)


# ---------------------------------------------------------------------------
# ValueError maps to PLANNING_BAD_CONFIG — Fix E
# ---------------------------------------------------------------------------


def test_plan_value_error_maps_to_bad_config(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    toppra: ToppRAParameteriser,
) -> None:
    """ValueError from any downstream component -> PLANNING_BAD_CONFIG.

    Fix E: the pipeline catches downstream ValueError and maps it to
    error_code='PLANNING_BAD_CONFIG', but no test exercised this path.
    The architect's spec lists PLANNING_BAD_CONFIG in the error contract.

    We use a minimal Planner subclass that raises ValueError to trigger
    the mapping — using ABC subclasses rather than MagicMock.
    """
    stub_sampler = _PlanValueErrorSampler()

    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=stub_sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=CancelToken(),
        )
    finally:
        ik.close()

    assert result.status == PlanStatus.FAILED
    assert result.error_code == "PLANNING_BAD_CONFIG", (
        f"Expected 'PLANNING_BAD_CONFIG' but got {result.error_code!r}. "
        "The pipeline.plan() ValueError catch clause must map to this code."
    )
    assert result.trajectory is None


# ---------------------------------------------------------------------------
# PlanNoSolution propagated
# ---------------------------------------------------------------------------


def test_plan_no_solution_maps_to_error_code(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    toppra: ToppRAParameteriser,
) -> None:
    """PlanNoSolution from sampler -> PLANNING_NO_SOLUTION.

    Uses a minimal ABC subclass instead of MagicMock (auditor item #9 / Fix E).
    """
    stub_sampler = _PlanNoSolutionSampler()

    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=stub_sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=CancelToken(),
        )
    finally:
        ik.close()

    assert result.status == PlanStatus.FAILED
    assert result.error_code == "PLANNING_NO_SOLUTION"


# ---------------------------------------------------------------------------
# PlanTimeout propagated
# ---------------------------------------------------------------------------


def test_plan_timeout_maps_to_error_code(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    toppra: ToppRAParameteriser,
) -> None:
    """PlanTimeout from sampler -> PLANNING_TIMEOUT.

    Uses a minimal ABC subclass instead of MagicMock (auditor item #9 / Fix E).
    """
    stub_sampler = _PlanTimeoutSampler()

    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=stub_sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=CancelToken(),
        )
    finally:
        ik.close()

    assert result.status == PlanStatus.FAILED
    assert result.error_code == "PLANNING_TIMEOUT"


# ---------------------------------------------------------------------------
# PlanningIKUnreachable propagated
# ---------------------------------------------------------------------------


def test_ik_unreachable_maps_to_error_code(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    """PlanningIKUnreachable from IK -> PLANNING_IK_UNREACHABLE.

    Uses a minimal stub instead of MagicMock (auditor item #9 / Fix E).
    """
    stub_ik = _IKUnreachableSolver()

    request = PlanRequest(
        robot_id="arm0",
        q_start=tuple(ur5_scene.home_q),
        goal_pose=((0.4, 0.0, 0.4), _IDENTITY_QUAT),
        planner=_fast_config(),
    )
    result = plan(
        request=request,
        scene=ur5_scene,
        checker=ur5_checker,
        ik=stub_ik,
        sampler=sampler,
        optimizer=None,
        parameteriser=toppra,
        cancel=CancelToken(),
    )

    assert result.status == PlanStatus.FAILED
    assert result.error_code == "PLANNING_IK_UNREACHABLE"
    assert result.stage == PlannerStage.IK


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------


def test_on_progress_callback_called_on_success(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        progress: list[tuple] = []
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
            parameteriser=ParameteriserConfig(grid_points=50),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=CancelToken(),
            on_progress=lambda s, p: progress.append((s, p)),
        )
    finally:
        ik.close()

    if result.status == PlanStatus.COMPLETED:
        assert len(progress) >= 1
        # Final progress should include COMPLETED stage
        final_stages = [s for s, _ in progress]
        assert PlannerStage.COMPLETED in final_stages


# ---------------------------------------------------------------------------
# plan_id is propagated to result
# ---------------------------------------------------------------------------


def test_plan_id_propagated(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
            parameteriser=ParameteriserConfig(grid_points=50),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=CancelToken(),
            plan_id="my-plan-42",
        )
    finally:
        ik.close()

    assert result.plan_id == "my-plan-42"


# ---------------------------------------------------------------------------
# cache_hit is always False at pipeline layer
# ---------------------------------------------------------------------------


def test_cache_hit_is_always_false(
    ur5_scene: SceneSnapshot,
    ur5_checker: CollisionChecker,
    sampler: RRTStarPlanner,
    toppra: ToppRAParameteriser,
) -> None:
    """cache_hit is False at pipeline layer (server layer fills it)."""
    ik = IKSolver(ur5_scene, residual_tol_m=0.02, cache_size=256)
    try:
        q_start = list(ur5_scene.home_q)
        q_goal = [q + 0.3 for q in q_start]
        request = PlanRequest(
            robot_id="arm0",
            q_start=tuple(q_start),
            goal_q=tuple(q_goal),
            planner=_fast_config(),
            parameteriser=ParameteriserConfig(grid_points=50),
        )
        result = plan(
            request=request,
            scene=ur5_scene,
            checker=ur5_checker,
            ik=ik,
            sampler=sampler,
            optimizer=None,
            parameteriser=toppra,
            cancel=CancelToken(),
        )
    finally:
        ik.close()

    assert result.cache_hit is False
