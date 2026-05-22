"""Pipeline orchestration: sample → optimise → parameterise.

The :func:`plan` function is the single entry point most callers use. It
takes pre-built planner / optimiser / parameteriser / IK instances and
runs them in sequence, converting every domain exception into a
:class:`PlanResult` with the correct ``error_code``. The server layer
wraps this call in a ``run_in_executor`` and never directly catches the
underlying exceptions.

Error-code mapping (Phase 3 contract in master plan §C):

* :class:`PlanCancelled`            → ``PLANNING_CANCELLED``
* :class:`PlanTimeout`              → ``PLANNING_TIMEOUT``
* :class:`PlanNoSolution`           → ``PLANNING_NO_SOLUTION``
* :class:`PlanLimitsExceeded`       → ``PLANNING_LIMITS_EXCEEDED``
* :class:`PlanningIKUnreachable`    → ``PLANNING_IK_UNREACHABLE``
* Other exceptions                  → ``PLANNING_FAILED``

Notes
-----
* All blocking calls run on the caller's thread (typically a
  ``ThreadPoolExecutor`` worker). The caller is responsible for posting
  WebSocket fan-out via ``loop.call_soon_threadsafe`` if it wants to.
* The ``cache_hit`` field is always ``False`` at this layer; the server
  layer's plan cache (Stream 2) is what populates it.
"""

from __future__ import annotations

import time
from typing import Callable

from src.planning.budgets import CancelToken, PlanCancelled, PlanTimeout
from src.planning.collision import CollisionChecker
from src.planning.ik import IKSolver, PlanningIKUnreachable
from src.planning.optimizer import TrajectoryOptimizer
from src.planning.parameteriser import PlanLimitsExceeded, TimeParameteriser
from src.planning.samplers import Planner, PlanNoSolution
from src.planning.scene import SceneSnapshot
from src.planning.types import (
    PlannerStage,
    PlanRequest,
    PlanResult,
    PlanStatus,
)


def _failure_result(
    plan_id: str,
    stage: PlannerStage,
    elapsed_s: float,
    error_code: str,
    error_message: str,
    status: PlanStatus = PlanStatus.FAILED,
    sampler_path_length: int = 0,
    optimizer_iterations: int = 0,
    parameteriser_grid_points: int = 0,
    singularity_hint: tuple[int, ...] = (),
) -> PlanResult:
    """Build a :class:`PlanResult` for a failed / cancelled plan."""
    return PlanResult(
        plan_id=plan_id,
        status=status,
        stage=stage,
        trajectory=None,
        elapsed_s=elapsed_s,
        sampler_path_length=sampler_path_length,
        optimizer_iterations=optimizer_iterations,
        parameteriser_grid_points=parameteriser_grid_points,
        cache_hit=False,
        error_code=error_code,
        error_message=error_message,
        singularity_hint=singularity_hint,
    )


def plan(
    request: PlanRequest,
    scene: SceneSnapshot,
    checker: CollisionChecker,
    ik: IKSolver,
    sampler: Planner,
    optimizer: TrajectoryOptimizer | None,
    parameteriser: TimeParameteriser,
    cancel: CancelToken,
    on_progress: Callable[[PlannerStage, float], None] | None = None,
    plan_id: str = "",
) -> PlanResult:
    """Run the full sample → optimise → parameterise pipeline.

    Returns a :class:`PlanResult` whose ``status`` and ``error_code`` reflect
    the outcome. The function never propagates a planning-domain exception;
    only programmer errors (e.g. ``TypeError`` from a wrong-kind argument)
    leak through.
    """
    t0 = time.monotonic()
    stage = PlannerStage.QUEUED

    def _progress(s: PlannerStage, pct: float) -> None:
        if on_progress is not None:
            try:
                on_progress(s, pct)
            except Exception:  # noqa: BLE001
                # Progress callbacks must never bring down the planner.
                pass

    try:
        # ------------------------------------------------------ IK (optional)
        if request.goal_q is not None:
            q_goal: tuple[float, ...] = request.goal_q
        else:
            stage = PlannerStage.IK
            _progress(stage, 0.0)
            assert request.goal_pose is not None  # validated by PlanRequest
            xyz, quat = request.goal_pose
            ik_result = ik.solve(
                target_xyz_m=xyz,
                target_quat_wxyz=quat,
                q_seed=request.q_start,
            )
            cancel.raise_if_cancelled()
            q_goal = ik_result.q_rad

        # --------------------------------------------------------- sampling
        stage = PlannerStage.SAMPLING
        _progress(stage, 0.0)
        waypoints = sampler.solve(
            scene=scene,
            checker=checker,
            q_start=request.q_start,
            q_goal=q_goal,
            config=request.planner,
            cancel=cancel,
            on_progress=lambda pct: _progress(PlannerStage.SAMPLING, pct),
        )
        sampler_path_length = len(waypoints)

        # ------------------------------------------------- optimisation (opt)
        optimizer_iterations = 0
        if optimizer is not None and request.optimizer.enabled:
            stage = PlannerStage.OPTIMIZING
            _progress(stage, 0.0)
            waypoints = optimizer.smooth(
                scene=scene,
                waypoints=waypoints,
                config=request.optimizer,
                cancel=cancel,
            )
            optimizer_iterations = int(request.optimizer.max_iterations)
            _progress(stage, 1.0)

        # ------------------------------------------------- parameterisation
        stage = PlannerStage.PARAMETERISING
        _progress(stage, 0.0)
        trajectory = parameteriser.parameterise(
            scene=scene,
            waypoints=waypoints,
            config=request.parameteriser,
            cancel=cancel,
        )
        _progress(PlannerStage.PARAMETERISING, 1.0)

        elapsed = time.monotonic() - t0
        _progress(PlannerStage.COMPLETED, 1.0)
        return PlanResult(
            plan_id=plan_id,
            status=PlanStatus.COMPLETED,
            stage=PlannerStage.COMPLETED,
            trajectory=trajectory,
            elapsed_s=elapsed,
            sampler_path_length=sampler_path_length,
            optimizer_iterations=optimizer_iterations,
            parameteriser_grid_points=int(request.parameteriser.grid_points),
            cache_hit=False,
            error_code=None,
            error_message=None,
            singularity_hint=(),
        )

    except PlanCancelled as exc:
        elapsed = time.monotonic() - t0
        return _failure_result(
            plan_id=plan_id,
            stage=PlannerStage.CANCELLED,
            elapsed_s=elapsed,
            error_code="PLANNING_CANCELLED",
            error_message=str(exc),
            status=PlanStatus.CANCELLED,
        )
    except PlanTimeout as exc:
        elapsed = time.monotonic() - t0
        return _failure_result(
            plan_id=plan_id,
            stage=stage,
            elapsed_s=elapsed,
            error_code="PLANNING_TIMEOUT",
            error_message=str(exc),
        )
    except PlanNoSolution as exc:
        elapsed = time.monotonic() - t0
        return _failure_result(
            plan_id=plan_id,
            stage=stage,
            elapsed_s=elapsed,
            error_code="PLANNING_NO_SOLUTION",
            error_message=str(exc),
        )
    except PlanLimitsExceeded as exc:
        elapsed = time.monotonic() - t0
        return _failure_result(
            plan_id=plan_id,
            stage=PlannerStage.PARAMETERISING,
            elapsed_s=elapsed,
            error_code="PLANNING_LIMITS_EXCEEDED",
            error_message=str(exc),
            singularity_hint=exc.singularity_hint,
        )
    except PlanningIKUnreachable as exc:
        elapsed = time.monotonic() - t0
        return _failure_result(
            plan_id=plan_id,
            stage=PlannerStage.IK,
            elapsed_s=elapsed,
            error_code="PLANNING_IK_UNREACHABLE",
            error_message=str(exc),
        )
    except ValueError as exc:
        # Validation failures from PlanRequest / dataclass __post_init__ etc.
        # bubble up here. Map to PLANNING_BAD_CONFIG so the server can return
        # a 422.
        elapsed = time.monotonic() - t0
        return _failure_result(
            plan_id=plan_id,
            stage=stage,
            elapsed_s=elapsed,
            error_code="PLANNING_BAD_CONFIG",
            error_message=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        return _failure_result(
            plan_id=plan_id,
            stage=stage,
            elapsed_s=elapsed,
            error_code="PLANNING_FAILED",
            error_message=f"{type(exc).__name__}: {exc}",
        )


__all__ = ["plan"]
