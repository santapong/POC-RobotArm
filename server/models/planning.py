"""Pydantic v2 models for the planning REST + WebSocket surface.

Wire-format models that mirror the planning-lib domain dataclasses
(``src.planning.types``). All field names are snake_case. Conversions between
wire models and domain objects are provided by ``to_domain`` / ``from_domain``
classmethods.

Notes
-----
- ``PlanRequestModel.to_domain()`` converts to the frozen ``PlanRequest``
  dataclass used by the planning pipeline.
- ``TimedTrajectoryModel.from_domain()`` converts a ``TimedTrajectory``
  dataclass to its wire representation.
- ``PlanProgressFrame`` is the payload streamed over ``/ws/planning/progress``.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from src.planning.types import PlanRequest, TimedTrajectory


# ---------------------------------------------------------------------------
# Enums (wire-format mirrors of planning-lib enums)
# ---------------------------------------------------------------------------


class PlannerKindModel(str, Enum):
    """Sampling planner selection."""

    RRT = "rrt"
    RRT_STAR = "rrt_star"
    PRM = "prm"


class PlanStageModel(str, Enum):
    """Pipeline stage labels."""

    QUEUED = "queued"
    IK = "ik"
    SAMPLING = "sampling"
    OPTIMIZING = "optimizing"
    PARAMETERISING = "parameterising"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanStatusModel(str, Enum):
    """Final status of a plan run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class PlannerConfigModel(BaseModel):
    """Sampler-stage configuration."""

    model_config = ConfigDict(from_attributes=True)

    kind: PlannerKindModel = PlannerKindModel.RRT_STAR
    timeout_s: float = Field(default=5.0, gt=0)
    smoothing_iterations: int = Field(default=50, ge=0)
    range_rad: float = Field(default=0.5, gt=0)
    clearance_m: float = Field(default=0.005, ge=0)
    qdd_max_rad_s2_default: Optional[float] = Field(default=None, gt=0)


class OptimizerConfigModel(BaseModel):
    """Trajectory-optimiser configuration."""

    model_config = ConfigDict(from_attributes=True)

    enabled: bool = False
    max_iterations: int = Field(default=100, ge=1)
    min_distance_m: float = Field(default=0.005, ge=0)
    spline_degree: int = Field(default=5)

    @model_validator(mode="after")
    def _validate_spline_degree(self) -> "OptimizerConfigModel":
        if self.spline_degree not in (3, 5):
            raise ValueError(
                f"OptimizerConfigModel.spline_degree must be 3 or 5, got {self.spline_degree}"
            )
        return self


class ParameteriserConfigModel(BaseModel):
    """Time-parameteriser configuration."""

    model_config = ConfigDict(from_attributes=True)

    qd_scale: float = Field(default=1.0, gt=0, le=1)
    qdd_scale: float = Field(default=1.0, gt=0, le=1)
    grid_points: int = Field(default=200, ge=16)


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class PlanRequestModel(BaseModel):
    """Body for ``POST /api/planning/plans``."""

    model_config = ConfigDict(from_attributes=True)

    robot_id: str
    q_start: list[float] = Field(min_length=1)
    goal_q: Optional[list[float]] = None
    # Exactly 3 floats required: wrong-length payloads return VALIDATION_ERROR
    # 422 here (Pydantic) rather than an IndexError 500 inside to_domain().
    goal_pose_xyz_m: Annotated[Optional[list[float]], Field(min_length=3, max_length=3)] = None
    # Exactly 4 floats required (w, x, y, z).  Same rationale as above.
    goal_pose_quat_wxyz: Annotated[Optional[list[float]], Field(min_length=4, max_length=4)] = None
    obstacles: list[str] = []
    planner: PlannerConfigModel = Field(default_factory=PlannerConfigModel)
    optimizer: OptimizerConfigModel = Field(default_factory=OptimizerConfigModel)
    parameteriser: ParameteriserConfigModel = Field(default_factory=ParameteriserConfigModel)

    @model_validator(mode="after")
    def _exactly_one_goal(self) -> "PlanRequestModel":
        # Error-taxonomy note (PM decision):
        # This validator (and Pydantic field-type mismatches) raise
        # ValidationError -> FastAPI global handler -> 422 VALIDATION_ERROR.
        # PLANNING_BAD_CONFIG 422 is reserved for downstream ValueError raised
        # by to_domain() or PlanRequest.__post_init__ (e.g. quat not unit-
        # normalised, DOF length mismatch) — config that passes Pydantic but
        # fails inside the planning lib.
        has_q = self.goal_q is not None
        has_pose = (
            self.goal_pose_xyz_m is not None and self.goal_pose_quat_wxyz is not None
        )
        if has_q == has_pose:
            raise ValueError(
                "PlanRequestModel: provide exactly one of goal_q or goal_pose_*"
            )
        return self

    def to_domain(self) -> "PlanRequest":
        """Convert to the frozen ``PlanRequest`` domain dataclass."""
        from src.planning.types import (
            OptimizerConfig,
            ParameteriserConfig,
            PlannerConfig,
            PlannerKind,
            PlanRequest,
        )

        planner_cfg = PlannerConfig(
            kind=PlannerKind(self.planner.kind.value),
            timeout_s=self.planner.timeout_s,
            smoothing_iterations=self.planner.smoothing_iterations,
            range_rad=self.planner.range_rad,
            clearance_m=self.planner.clearance_m,
            qdd_max_rad_s2_default=self.planner.qdd_max_rad_s2_default,
        )
        optimizer_cfg = OptimizerConfig(
            enabled=self.optimizer.enabled,
            max_iterations=self.optimizer.max_iterations,
            min_distance_m=self.optimizer.min_distance_m,
            spline_degree=self.optimizer.spline_degree,
        )
        parameteriser_cfg = ParameteriserConfig(
            qd_scale=self.parameteriser.qd_scale,
            qdd_scale=self.parameteriser.qdd_scale,
            grid_points=self.parameteriser.grid_points,
        )

        goal_pose = None
        if self.goal_pose_xyz_m is not None and self.goal_pose_quat_wxyz is not None:
            goal_pose = (
                (
                    float(self.goal_pose_xyz_m[0]),
                    float(self.goal_pose_xyz_m[1]),
                    float(self.goal_pose_xyz_m[2]),
                ),
                (
                    float(self.goal_pose_quat_wxyz[0]),
                    float(self.goal_pose_quat_wxyz[1]),
                    float(self.goal_pose_quat_wxyz[2]),
                    float(self.goal_pose_quat_wxyz[3]),
                ),
            )

        return PlanRequest(
            robot_id=self.robot_id,
            q_start=tuple(float(v) for v in self.q_start),
            goal_q=tuple(float(v) for v in self.goal_q) if self.goal_q is not None else None,
            goal_pose=goal_pose,
            obstacles=tuple(self.obstacles),
            planner=planner_cfg,
            optimizer=optimizer_cfg,
            parameteriser=parameteriser_cfg,
        )


# ---------------------------------------------------------------------------
# Trajectory models
# ---------------------------------------------------------------------------


class TrajectorySampleModel(BaseModel):
    """One sample of a time-parameterised trajectory."""

    model_config = ConfigDict(from_attributes=True)

    t_s: float
    q_rad: list[float]
    qd_rad_s: list[float]
    qdd_rad_s2: list[float]


class TimedTrajectoryModel(BaseModel):
    """A time-parameterised joint trajectory for wire transfer."""

    model_config = ConfigDict(from_attributes=True)

    robot_id: str
    dt_s: float
    samples: list[TrajectorySampleModel]
    duration_s: float

    @classmethod
    def from_domain(cls, obj: "TimedTrajectory") -> "TimedTrajectoryModel":
        """Convert a domain ``TimedTrajectory`` to its wire model."""
        return cls(
            robot_id=obj.robot_id,
            dt_s=obj.dt_s,
            samples=[
                TrajectorySampleModel(
                    t_s=s.t_s,
                    q_rad=list(s.q_rad),
                    qd_rad_s=list(s.qd_rad_s),
                    qdd_rad_s2=list(s.qdd_rad_s2),
                )
                for s in obj.samples
            ],
            duration_s=obj.duration_s,
        )


# ---------------------------------------------------------------------------
# Run record (plan status + optional result)
# ---------------------------------------------------------------------------


class PlanRunRecord(BaseModel):
    """Full status record for a plan run, returned by REST GET endpoints."""

    model_config = ConfigDict(from_attributes=True)

    plan_id: str
    status: PlanStatusModel
    stage: PlanStageModel
    request: PlanRequestModel
    created_at: float
    finished_at: Optional[float] = None
    elapsed_s: Optional[float] = None
    sampler_path_length: int = 0
    optimizer_iterations: int = 0
    parameteriser_grid_points: int = 0
    cache_hit: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    singularity_hint: list[int] = []
    trajectory: Optional[TimedTrajectoryModel] = None


# ---------------------------------------------------------------------------
# REST response models
# ---------------------------------------------------------------------------


class PlanCreateResponse(BaseModel):
    """Response body for ``POST /api/planning/plans``."""

    model_config = ConfigDict(from_attributes=True)

    plan_id: str
    status: PlanStatusModel


class PlanExecuteRequest(BaseModel):
    """Body for ``POST /api/planning/plans/{plan_id}/execute``."""

    model_config = ConfigDict(from_attributes=True)

    dt_s: float = Field(default=0.01, gt=0)


class PlanExecuteResponse(BaseModel):
    """Response body for ``POST /api/planning/plans/{plan_id}/execute``."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str


# ---------------------------------------------------------------------------
# WebSocket progress frame
# ---------------------------------------------------------------------------


class PlanProgressFrame(BaseModel):
    """Server-push frame over ``/ws/planning/progress``."""

    model_config = ConfigDict(from_attributes=True)

    plan_id: str
    stage: PlanStageModel
    percent: float
    eta_s: Optional[float] = None
    monotonic_s: float = Field(default_factory=time.monotonic)


__all__ = [
    "OptimizerConfigModel",
    "ParameteriserConfigModel",
    "PlanCreateResponse",
    "PlanExecuteRequest",
    "PlanExecuteResponse",
    "PlanProgressFrame",
    "PlanRequestModel",
    "PlanRunRecord",
    "PlanStageModel",
    "PlanStatusModel",
    "PlannerConfigModel",
    "PlannerKindModel",
    "TimedTrajectoryModel",
    "TrajectorySampleModel",
]
