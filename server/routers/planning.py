"""Planning REST router.

Endpoints
---------
- ``POST   /api/planning/plans``                          — schedule a plan.
- ``GET    /api/planning/plans``                          — list all plans.
- ``GET    /api/planning/plans/{plan_id}``                — get one plan record.
- ``POST   /api/planning/plans/{plan_id}/cancel``         — cancel a plan.
- ``GET    /api/planning/plans/{plan_id}/trajectory``     — trajectory (when done).
- ``POST   /api/planning/plans/{plan_id}/execute``        — hand trajectory to sim.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from server.models.planning import (
    PlanCreateResponse,
    PlanExecuteRequest,
    PlanExecuteResponse,
    PlanRequestModel,
    PlanRunRecord,
    PlanStatusModel,
    TimedTrajectoryModel,
)
from server.services.errors import http_error
from server.services.session import Session, get_session

router = APIRouter(prefix="/api/planning")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_planning_runtime(session: Session):
    """Return the ``PlanningRuntime`` or raise 503 ``PLANNING_NOT_INITIALIZED``."""
    if session.planning_runtime is None:
        raise http_error(
            503,
            "PLANNING_NOT_INITIALIZED",
            "Planning runtime not initialised — spawn a robot and submit a plan first.",
        )
    return session.planning_runtime


def _record_to_response(record) -> PlanRunRecord:
    """Convert a ``_PlanRunRecord`` to the ``PlanRunRecord`` wire model."""
    from server.models.planning import TimedTrajectoryModel

    traj_model = None
    result = record.result
    if result is not None and result.trajectory is not None:
        traj_model = TimedTrajectoryModel.from_domain(result.trajectory)

    elapsed: float | None = None
    if result is not None:
        elapsed = result.elapsed_s

    error_code: str | None = None
    error_message: str | None = None
    singularity_hint: list[int] = []
    sampler_path_length = 0
    optimizer_iterations = 0
    parameteriser_grid_points = 0
    cache_hit = False

    if result is not None:
        error_code = result.error_code
        error_message = result.error_message
        singularity_hint = list(result.singularity_hint)
        sampler_path_length = result.sampler_path_length
        optimizer_iterations = result.optimizer_iterations
        parameteriser_grid_points = result.parameteriser_grid_points
        cache_hit = result.cache_hit

    # Reconstruct the PlanRequestModel from the domain request.
    req = record.request
    from server.models.planning import (
        OptimizerConfigModel,
        ParameteriserConfigModel,
        PlannerConfigModel,
        PlannerKindModel,
    )

    req_model = PlanRequestModel(
        robot_id=req.robot_id,
        q_start=list(req.q_start),
        goal_q=list(req.goal_q) if req.goal_q is not None else None,
        goal_pose_xyz_m=(
            list(req.goal_pose[0]) if req.goal_pose is not None else None
        ),
        goal_pose_quat_wxyz=(
            list(req.goal_pose[1]) if req.goal_pose is not None else None
        ),
        obstacles=list(req.obstacles),
        planner=PlannerConfigModel(
            kind=PlannerKindModel(req.planner.kind.value),
            timeout_s=req.planner.timeout_s,
            smoothing_iterations=req.planner.smoothing_iterations,
            range_rad=req.planner.range_rad,
            clearance_m=req.planner.clearance_m,
            qdd_max_rad_s2_default=req.planner.qdd_max_rad_s2_default,
        ),
        optimizer=OptimizerConfigModel(
            enabled=req.optimizer.enabled,
            max_iterations=req.optimizer.max_iterations,
            min_distance_m=req.optimizer.min_distance_m,
            spline_degree=req.optimizer.spline_degree,
        ),
        parameteriser=ParameteriserConfigModel(
            qd_scale=req.parameteriser.qd_scale,
            qdd_scale=req.parameteriser.qdd_scale,
            grid_points=req.parameteriser.grid_points,
        ),
    )

    return PlanRunRecord(
        plan_id=record.plan_id,
        status=record.status,
        stage=record.stage,
        request=req_model,
        created_at=record.created_at,
        finished_at=record.finished_at,
        elapsed_s=elapsed,
        sampler_path_length=sampler_path_length,
        optimizer_iterations=optimizer_iterations,
        parameteriser_grid_points=parameteriser_grid_points,
        cache_hit=cache_hit,
        error_code=error_code,
        error_message=error_message,
        singularity_hint=singularity_hint,
        trajectory=traj_model,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/plans", response_model=PlanCreateResponse)
async def create_plan(
    body: PlanRequestModel,
    session: Session = Depends(get_session),
) -> PlanCreateResponse:
    """Schedule a plan and return immediately with a ``plan_id``."""
    # Validate that planning libraries are available.
    try:
        from src.planning.types import PlanningUnavailable  # noqa: F401
    except ImportError:
        raise http_error(
            422,
            "PLANNING_UNAVAILABLE",
            "Planning libraries (OMPL / Drake / toppra) are not installed on "
            "this platform. Use Linux or macOS, or install via WSL on Windows.",
        )

    # Lazily create PlanningRuntime.
    if session.planning_runtime is None:
        if session.sim_runtime is None:
            raise http_error(
                503,
                "PLANNING_NOT_INITIALIZED",
                "Simulator not initialised — spawn a robot first.",
            )
        from server.services.planning import PlanningRuntime

        session.planning_runtime = PlanningRuntime(
            catalog_name=session.sim_runtime.catalog_name,
            station_provider=lambda: session.station,
        )

    try:
        domain_req = body.to_domain()
    except ValueError as exc:
        raise http_error(422, "PLANNING_BAD_CONFIG", str(exc)) from exc

    runtime = session.planning_runtime
    record = await runtime.plan(domain_req)
    return PlanCreateResponse(plan_id=record.plan_id, status=PlanStatusModel.RUNNING)


@router.get("/plans", response_model=list[PlanRunRecord])
async def list_plans(
    session: Session = Depends(get_session),
) -> list[PlanRunRecord]:
    """Return all plan records."""
    if session.planning_runtime is None:
        return []
    return [_record_to_response(r) for r in session.planning_runtime.list_records()]


@router.get("/plans/{plan_id}", response_model=PlanRunRecord)
async def get_plan(
    plan_id: str,
    session: Session = Depends(get_session),
) -> PlanRunRecord:
    """Return a single plan record by ``plan_id``."""
    runtime = _require_planning_runtime(session)
    try:
        record = runtime.get_record(plan_id)
    except KeyError:
        raise http_error(404, "PLAN_UNKNOWN", f"Plan '{plan_id}' not found.")
    return _record_to_response(record)


@router.post("/plans/{plan_id}/cancel", response_model=PlanRunRecord)
async def cancel_plan(
    plan_id: str,
    session: Session = Depends(get_session),
) -> PlanRunRecord:
    """Cooperatively cancel a running plan."""
    runtime = _require_planning_runtime(session)
    try:
        record = await runtime.cancel(plan_id)
    except KeyError:
        raise http_error(404, "PLAN_UNKNOWN", f"Plan '{plan_id}' not found.")
    return _record_to_response(record)


@router.get("/plans/{plan_id}/trajectory", response_model=TimedTrajectoryModel)
async def get_trajectory(
    plan_id: str,
    session: Session = Depends(get_session),
) -> TimedTrajectoryModel:
    """Return the trajectory for a completed plan."""
    runtime = _require_planning_runtime(session)
    try:
        record = runtime.get_record(plan_id)
    except KeyError:
        raise http_error(404, "PLAN_UNKNOWN", f"Plan '{plan_id}' not found.")

    if record.status != PlanStatusModel.COMPLETED:
        raise http_error(
            409,
            "PLAN_NOT_COMPLETED",
            f"Plan '{plan_id}' is not completed (status: {record.status.value}).",
        )

    result = record.result
    if result is None or result.trajectory is None:
        raise http_error(
            409,
            "PLAN_NOT_COMPLETED",
            f"Plan '{plan_id}' has no trajectory data.",
        )

    return TimedTrajectoryModel.from_domain(result.trajectory)


@router.post("/plans/{plan_id}/execute", response_model=PlanExecuteResponse)
async def execute_plan(
    plan_id: str,
    body: PlanExecuteRequest,
    session: Session = Depends(get_session),
) -> PlanExecuteResponse:
    """Hand a completed trajectory to the simulator for execution."""
    runtime = _require_planning_runtime(session)
    try:
        record = runtime.get_record(plan_id)
    except KeyError:
        raise http_error(404, "PLAN_UNKNOWN", f"Plan '{plan_id}' not found.")

    if record.status != PlanStatusModel.COMPLETED:
        raise http_error(
            409,
            "PLAN_NOT_COMPLETED",
            f"Plan '{plan_id}' is not completed (status: {record.status.value}).",
        )

    result = record.result
    if result is None or result.trajectory is None:
        raise http_error(
            409,
            "PLAN_NOT_COMPLETED",
            f"Plan '{plan_id}' has no trajectory data.",
        )

    sim = session.sim_runtime
    if sim is None:
        raise http_error(503, "SIM_DISCONNECTED", "Simulator not initialised.")

    traj = result.trajectory
    waypoints = [list(s.q_rad) for s in traj.samples]
    sim.bridge.start_trajectory(waypoints, body.dt_s)

    run_id = str(uuid.uuid4())
    import time as _time

    from server.models.runtime import RunRecord

    session.runs[run_id] = RunRecord(
        run_id=run_id,
        program_id=plan_id,
        status="running",
        created_at=_time.time(),
    )

    return PlanExecuteResponse(run_id=run_id)


__all__ = ["router"]
