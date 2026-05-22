"""Program management router.

Endpoints
---------
- ``GET  /api/programs``                   — list available programs.
- ``GET  /api/programs/{id}``              — get a program by id.
- ``POST /api/programs/{id}/post``         — emit post-processed source code.
- ``POST /api/programs/{id}/run``          — start a simulated run.
- ``GET  /api/programs/runs/{run_id}``     — get a run record.
- ``POST /api/programs/runs/{run_id}/stop`` — cancel an active run.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends

from server.models.motion import ProgramModel
from server.models.planning import PlannerConfigModel, PlannerKindModel, PlanRequestModel
from server.models.runtime import PostRequest, PostResponse, RunRecord, RunStart
from server.services.errors import http_error
from server.services.programs import get_program, list_programs
from server.services.session import Session, get_session

router = APIRouter(prefix="/api/programs")


@router.get("")
async def list_programs_endpoint() -> list[dict]:
    """Return the list of available programs."""
    return list_programs()


# NOTE: /runs/{run_id} must be declared BEFORE /{id} so FastAPI doesn't treat
#       "runs" as a program id.
@router.get("/runs/{run_id}", response_model=RunRecord)
async def get_run(
    run_id: str,
    session: Session = Depends(get_session),
) -> RunRecord:
    """Return the RunRecord for ``run_id``."""
    if run_id not in session.runs:
        raise http_error(404, "RUN_UNKNOWN", f"Run '{run_id}' not found.")
    return session.runs[run_id]


@router.post("/runs/{run_id}/stop", response_model=RunRecord)
async def stop_run(
    run_id: str,
    session: Session = Depends(get_session),
) -> RunRecord:
    """Cancel an active run."""
    if run_id not in session.runs:
        raise http_error(404, "RUN_UNKNOWN", f"Run '{run_id}' not found.")
    record = session.runs[run_id]
    if record.status not in ("queued", "running"):
        return record

    if session.sim_runtime is not None:
        session.sim_runtime.bridge.cancel_trajectory()

    updated = RunRecord(
        run_id=record.run_id,
        program_id=record.program_id,
        status="failed",
        created_at=record.created_at,
        finished_at=time.time(),
        violation_count=record.violation_count,
        error="Cancelled by operator",
    )
    session.runs[run_id] = updated
    await session.push_event(
        {"type": "run_failed", "payload": {"run_id": run_id, "error": "Cancelled by operator"}}
    )
    return updated


@router.get("/{program_id}", response_model=ProgramModel)
async def get_program_endpoint(program_id: str) -> ProgramModel:
    """Return the full program model for ``program_id``."""
    try:
        prog = get_program(program_id)
    except KeyError as exc:
        raise http_error(404, "PROGRAM_UNKNOWN", str(exc)) from exc
    return ProgramModel.from_domain(prog)


@router.post("/{program_id}/post", response_model=PostResponse)
async def post_program(
    program_id: str,
    body: PostRequest,
    session: Session = Depends(get_session),
) -> PostResponse:
    """Emit post-processed source code for the given program."""
    try:
        prog = get_program(program_id)
    except KeyError as exc:
        raise http_error(404, "PROGRAM_UNKNOWN", str(exc)) from exc

    vendor = body.vendor
    if vendor == "rapid":
        from src.post import RAPIDPost

        source = RAPIDPost().emit(prog)
        ext = ".mod"
    elif vendor == "krl":
        from src.post import KRLPost

        source = KRLPost().emit(prog)
        ext = ".src"
    elif vendor == "urscript":
        from src.post import URScriptPost

        source = URScriptPost().emit(prog)
        ext = ".script"
    else:
        raise http_error(422, "VALIDATION_ERROR", f"Unknown vendor: {vendor!r}")

    await session.push_event(
        {"type": "program_emitted", "payload": {"program_id": program_id, "vendor": vendor}}
    )
    return PostResponse(vendor=vendor, source=source, file_extension=ext)


@router.post("/{program_id}/run")
async def run_program(
    program_id: str,
    body: RunStart,
    session: Session = Depends(get_session),
) -> dict:
    """Schedule a simulated run of the program.

    Returns ``{"run_id": str}``.
    """
    try:
        prog = get_program(program_id)
    except KeyError as exc:
        raise http_error(404, "PROGRAM_UNKNOWN", str(exc)) from exc

    run_id = str(uuid.uuid4())
    record = RunRecord(
        run_id=run_id,
        program_id=program_id,
        status="queued",
        created_at=time.time(),
    )
    session.runs[run_id] = record

    if session.sim_runtime is None:
        # No sim; mark completed immediately (no-op run).
        session.runs[run_id] = RunRecord(
            run_id=run_id,
            program_id=program_id,
            status="failed",
            created_at=record.created_at,
            finished_at=time.time(),
            error="Simulator not initialised. Spawn a robot first.",
        )
        return {"run_id": run_id}

    runtime = session.sim_runtime

    # Run asynchronously in the background.
    asyncio.create_task(_run_program_task(session, run_id, prog, runtime, body))

    await session.push_event({"type": "run_started", "payload": {"run_id": run_id, "error": None}})
    return {"run_id": run_id}


def _move_to_plan_request(step, current_q: list[float], runtime, station) -> PlanRequestModel:
    """Build a ``PlanRequestModel`` from a MOVE_L / MOVE_J / MOVE_C step.

    Uses the step's ``PoseTarget`` as the Cartesian goal and all station
    fixtures as obstacles. Falls back to the step target's joints for
    MOVE_ABS_J / joint-target MOVE_J.
    """
    from src.motion.ir import PoseTarget

    target = step.target
    goal_q = None
    goal_pose_xyz_m = None
    goal_pose_quat_wxyz = None

    if isinstance(target, PoseTarget):
        goal_pose_xyz_m = list(target.xyz_m)
        goal_pose_quat_wxyz = list(target.quat_wxyz)
    else:
        # JointTarget fallback.
        goal_q = list(target.q_rad)

    obstacle_names = [f.name for f in station.fixtures]

    return PlanRequestModel(
        robot_id=runtime.catalog_name,
        q_start=list(current_q),
        goal_q=goal_q,
        goal_pose_xyz_m=goal_pose_xyz_m,
        goal_pose_quat_wxyz=goal_pose_quat_wxyz,
        obstacles=obstacle_names,
        planner=PlannerConfigModel(kind=PlannerKindModel.RRT_STAR),
    )


async def _wait_complete(record, timeout: float = 60.0) -> None:
    """Wait for a ``_PlanRunRecord.future`` to finish."""

    if record.future is None:
        return
    try:
        await asyncio.wait_for(asyncio.wrap_future(record.future), timeout=timeout)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        pass


def _eval_predicate(value: bool | int | float, op: Any, threshold: bool | int | float) -> bool:
    """Evaluate ``value <op> threshold`` for a :class:`~src.motion.ir.SignalOp`.

    Parameters
    ----------
    value:
        Live signal value read from the adapter.
    op:
        A ``SignalOp`` enum member (``EQ``, ``NEQ``, ``GT``, ``GTE``, ``LT``, ``LTE``).
    threshold:
        The comparison threshold from the IR step.
    """
    from src.motion.ir import SignalOp

    if op == SignalOp.EQ:
        return value == threshold
    if op == SignalOp.NEQ:
        return value != threshold
    if op == SignalOp.GT:
        return value > threshold  # type: ignore[operator]
    if op == SignalOp.GTE:
        return value >= threshold  # type: ignore[operator]
    if op == SignalOp.LT:
        return value < threshold  # type: ignore[operator]
    if op == SignalOp.LTE:
        return value <= threshold  # type: ignore[operator]
    return False


async def _execute_io_step(
    session: Session,
    step: Any,
    on_branch: Callable[[list[Any]], Awaitable[None]],
) -> None:
    """Execute a single I/O step from the program IR.

    Handles :class:`~src.motion.ir.SetSignal`,
    :class:`~src.motion.ir.WaitSignal`, and
    :class:`~src.motion.ir.IfSignal`.

    Parameters
    ----------
    session:
        The active session (provides ``io_runtime``).
    step:
        A ``SetSignal``, ``WaitSignal``, or ``IfSignal`` IR step.
    on_branch:
        Recursive callback used by ``IfSignal`` to execute the chosen body.
        The callback receives the branch body (list of ``ProcedureStep``) and
        awaits it — this keeps the executor reentrant for nested
        ``IfSignal`` steps.

    Raises
    ------
    HTTPException (503)
        If ``session.io_runtime`` has not been initialised yet.
    """
    from src.motion.ir import IfSignal, SetSignal, WaitSignal

    iohost = session.io_runtime
    if iohost is None:
        raise http_error(503, "IO_NOT_INITIALIZED", "I/O runtime not started")

    if isinstance(step, SetSignal):
        await iohost.write(step.connection, step.signal, step.value)

    elif isinstance(step, WaitSignal):
        await iohost.wait_for_signal(
            step.connection,
            step.signal,
            predicate=lambda v: _eval_predicate(v, step.op, step.value),
            timeout_s=step.timeout_s,
        )

    elif isinstance(step, IfSignal):
        snap = await iohost.read(step.connection, step.signal)
        body = (
            step.then_body
            if _eval_predicate(snap.value if snap.value is not None else 0, step.op, step.value)
            else step.else_body
        )
        await on_branch(list(body))


async def _run_program_task(session: Session, run_id: str, prog, runtime, body: RunStart) -> None:
    """Background task: interpolate and play the program through the bridge."""
    from src.motion.path import interpolate_program

    session.runs[run_id] = RunRecord(
        run_id=run_id,
        program_id=session.runs[run_id].program_id,
        status="running",
        created_at=session.runs[run_id].created_at,
    )

    try:
        if body.planner == "rrt":
            await _run_program_task_rrt(session, run_id, prog, runtime, body)
            return

        # Detect whether the program contains any I/O steps.  If not, fall
        # through to the unmodified batch-interpolation path so motion-only
        # programs remain byte-identical to Phases 0-3.
        from src.motion.ir import IfSignal, Move, SetSignal, WaitSignal

        has_io_steps = any(
            isinstance(step, (SetSignal, WaitSignal, IfSignal))
            for procedure in prog.procedures
            for step in procedure.body
        )

        if not has_io_steps:
            # --- Original batch path (unchanged) ---
            def _play(sim):
                try:
                    import roboticstoolbox as rtb  # type: ignore[import]

                    robot = rtb.models.__dict__.get(runtime.catalog_name.title())
                    if robot is None:
                        robot = rtb.DHRobot([])
                except Exception:  # noqa: BLE001
                    robot = None

                if robot is None:
                    home = sim.get_joint_angles()
                    runtime.bridge.start_trajectory([home], body.dt_s)
                    return None

                path = interpolate_program(prog, robot, dt_s=body.dt_s, raise_on_violation=False)
                waypoints = [list(s.q_rad) for s in path.samples]
                runtime.bridge.start_trajectory(waypoints, body.dt_s)
                return path

            await asyncio.to_thread(runtime.bridge.submit, _play)

        else:
            # --- Step-by-step path for programs with I/O steps ---
            # Move steps are batched per-procedure; I/O steps run in the order
            # they appear in the body.  Within each procedure: collect Move steps
            # into one batch, play them through the bridge, then execute any I/O
            # steps that follow (in body order).
            #
            # Recursive helper for IfSignal.then_body / else_body.
            async def _run_body(steps: list[Any]) -> None:
                move_steps_inner = [s for s in steps if isinstance(s, Move)]
                if move_steps_inner:
                    _play_moves_inner(move_steps_inner)
                for step_inner in steps:
                    if isinstance(step_inner, (SetSignal, WaitSignal, IfSignal)):
                        await _execute_io_step(session, step_inner, on_branch=_run_body)

            def _play_moves_inner(moves_list: list[Any]) -> None:
                """Run a list of Move steps synchronously through the bridge."""
                if not moves_list:
                    return
                try:
                    import roboticstoolbox as rtb  # type: ignore[import]

                    robot = rtb.models.__dict__.get(runtime.catalog_name.title())
                    if robot is None:
                        robot = rtb.DHRobot([])
                except Exception:  # noqa: BLE001
                    robot = None

                def _play_inner(sim):
                    if robot is None:
                        home = sim.get_joint_angles()
                        runtime.bridge.start_trajectory([home], body.dt_s)
                        return
                    # Build a mini-program with only these moves for interpolation.
                    from src.motion.ir import Procedure, Program

                    mini_prog = Program(
                        name=prog.name,
                        procedures=(
                            Procedure(
                                name="main",
                                body=tuple(moves_list),
                            ),
                        ),
                    )
                    path = interpolate_program(
                        mini_prog, robot, dt_s=body.dt_s, raise_on_violation=False
                    )
                    waypoints = [list(s.q_rad) for s in path.samples]
                    runtime.bridge.start_trajectory(waypoints, body.dt_s)

                runtime.bridge.submit(_play_inner)

            for procedure in prog.procedures:
                move_steps: list[Any] = []
                for step in procedure.body:
                    if isinstance(step, Move):
                        move_steps.append(step)
                    elif isinstance(step, (SetSignal, WaitSignal, IfSignal)):
                        # Flush accumulated Move steps first.
                        if move_steps:
                            await asyncio.to_thread(
                                lambda ms=move_steps: _play_moves_inner(ms)  # noqa: B023
                            )
                            move_steps = []
                        await _execute_io_step(session, step, on_branch=_run_body)
                    # IOOp / Wait / Comment are ignored (post-processor-only).
                # Flush any remaining Move steps at end of procedure.
                if move_steps:
                    await asyncio.to_thread(
                        lambda ms=move_steps: _play_moves_inner(ms)  # noqa: B023
                    )

        session.runs[run_id] = RunRecord(
            run_id=run_id,
            program_id=session.runs[run_id].program_id,
            status="completed",
            created_at=session.runs[run_id].created_at,
            finished_at=time.time(),
        )
        await session.push_event(
            {"type": "run_completed", "payload": {"run_id": run_id, "error": None}}
        )
    except Exception as exc:  # noqa: BLE001
        session.runs[run_id] = RunRecord(
            run_id=run_id,
            program_id=session.runs[run_id].program_id,
            status="failed",
            created_at=session.runs[run_id].created_at,
            finished_at=time.time(),
            error=str(exc),
        )
        await session.push_event(
            {"type": "run_failed", "payload": {"run_id": run_id, "error": str(exc)}}
        )


async def _run_program_task_rrt(
    session: Session, run_id: str, prog, runtime, body: RunStart
) -> None:
    """RRT-planner path: route Cartesian moves through PlanningRuntime.

    Steps are iterated in body order. Move steps go through the RRT planner
    and the bridge.  I/O steps (SetSignal, WaitSignal, IfSignal) are executed
    immediately in sequence, interleaved with Move steps.
    IOOp / Wait / Comment steps are silently skipped (post-processor-only).
    """
    from server.models.planning import PlanStatusModel
    from server.services.planning import PlanningRuntime

    if session.planning_runtime is None:
        session.planning_runtime = PlanningRuntime(
            catalog_name=runtime.catalog_name,
            station_provider=lambda: session.station,
        )

    from src.motion.ir import IfSignal, Move, MoveKind, SetSignal, WaitSignal

    # Obtain current joint angles as starting configuration.
    def _get_joints(sim):
        return list(sim.get_joint_angles())

    try:
        current_q = await asyncio.to_thread(runtime.bridge.submit, _get_joints)
    except Exception:  # noqa: BLE001
        current_q = [0.0] * runtime.dof

    has_waypoints = False

    async def _run_body_rrt(steps: list[Any]) -> None:
        """Recursive helper for IfSignal branches in the RRT path."""
        nonlocal current_q, has_waypoints
        for step_inner in steps:
            if isinstance(step_inner, Move):
                if step_inner.kind not in (MoveKind.MOVE_L, MoveKind.MOVE_C, MoveKind.MOVE_J):
                    continue
                req_model = _move_to_plan_request(step_inner, current_q, runtime, session.station)
                try:
                    domain_req = req_model.to_domain()
                except ValueError as exc:
                    raise http_error(422, "IO_BAD_CONFIG", f"PLANNING_BAD_CONFIG: {exc}") from exc
                rec = await session.planning_runtime.plan(domain_req)
                await _wait_complete(rec)
                if rec.status != PlanStatusModel.COMPLETED:
                    msg = (rec.result.error_message or "no path") if rec.result else "no path"
                    raise http_error(503, "PLANNING_FAILED", f"PLANNING_FAILED: {msg}")
                step_waypoints = [list(s.q_rad) for s in rec.result.trajectory.samples]
                if step_waypoints:
                    runtime.bridge.start_trajectory(step_waypoints, body.dt_s)
                    current_q = step_waypoints[-1]
                    has_waypoints = True
            elif isinstance(step_inner, (SetSignal, WaitSignal, IfSignal)):
                await _execute_io_step(session, step_inner, on_branch=_run_body_rrt)

    for procedure in prog.procedures:
        for step in procedure.body:
            if isinstance(step, Move):
                if step.kind not in (MoveKind.MOVE_L, MoveKind.MOVE_C, MoveKind.MOVE_J):
                    continue

                req_model = _move_to_plan_request(step, current_q, runtime, session.station)
                try:
                    domain_req = req_model.to_domain()
                except ValueError as exc:
                    _mark_failed(session, run_id, f"PLANNING_BAD_CONFIG: {exc}")
                    await session.push_event(
                        {"type": "run_failed", "payload": {"run_id": run_id, "error": str(exc)}}
                    )
                    return

                rec = await session.planning_runtime.plan(domain_req)
                await _wait_complete(rec)

                if rec.status != PlanStatusModel.COMPLETED:
                    msg = (rec.result.error_message or "no path") if rec.result else "no path"
                    _mark_failed(session, run_id, f"PLANNING_FAILED: {msg}")
                    await session.push_event(
                        {"type": "run_failed", "payload": {"run_id": run_id, "error": msg}}
                    )
                    return

                step_waypoints = [list(s.q_rad) for s in rec.result.trajectory.samples]
                if step_waypoints:
                    runtime.bridge.start_trajectory(step_waypoints, body.dt_s)
                    current_q = step_waypoints[-1]
                    has_waypoints = True

            elif isinstance(step, (SetSignal, WaitSignal, IfSignal)):
                try:
                    await _execute_io_step(session, step, on_branch=_run_body_rrt)
                except Exception as exc:  # noqa: BLE001
                    _mark_failed(session, run_id, str(exc))
                    await session.push_event(
                        {"type": "run_failed", "payload": {"run_id": run_id, "error": str(exc)}}
                    )
                    return
            # IOOp / Wait / Comment ignored (post-processor-only types).

    session.runs[run_id] = RunRecord(
        run_id=run_id,
        program_id=session.runs[run_id].program_id,
        status="completed",
        created_at=session.runs[run_id].created_at,
        finished_at=time.time(),
    )
    await session.push_event(
        {"type": "run_completed", "payload": {"run_id": run_id, "error": None}}
    )


def _mark_failed(session: Session, run_id: str, error: str) -> None:
    """Update run record to failed status."""
    rec = session.runs.get(run_id)
    if rec is None:
        return
    session.runs[run_id] = RunRecord(
        run_id=rec.run_id,
        program_id=rec.program_id,
        status="failed",
        created_at=rec.created_at,
        finished_at=time.time(),
        error=error,
    )


__all__ = ["router"]
