"""Frozen dataclass IR for motion planning requests, configs, and results.

Mirrors the convention established by :mod:`src.motion.ir`:

* All dataclasses are ``frozen=True`` (safe to share across worker threads).
* Validation runs in ``__post_init__`` — bad inputs raise :class:`ValueError`.
* JSON round-trip is provided through :func:`to_dict` / :func:`from_dict`
  with a ``__type__`` discriminator so dicts can be reconstructed without
  positional cues.

Notes
-----
* Module top is import-cheap: stdlib + numpy only. No PyBullet, no OMPL,
  no Drake, no toppra so :mod:`src.planning.types` works on Windows.
* All vectors are SI (metres, radians, seconds); quaternions are
  ``(w, x, y, z)``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Sentinels and tolerances
# ---------------------------------------------------------------------------

QUAT_NORM_TOL = 1e-6


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PlanningUnavailable(RuntimeError):
    """Raised on Windows (and other unsupported platforms) when an OMPL /
    Drake / TOPP-RA-backed concrete class is instantiated.

    The :mod:`src.planning` package is importable on every platform, but the
    underlying libraries do not ship Windows wheels; the contract is to
    raise at first concrete-class ``__init__`` rather than at module import
    time so type / scene / budget utilities remain useful.
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_float_tuple(
    value: Any, length: Optional[int] = None, name: str = "value"
) -> tuple[float, ...]:
    """Coerce a sequence to a tuple of floats; optionally enforce length."""
    if value is None:
        raise ValueError(f"{name} must not be None")
    try:
        out = tuple(float(v) for v in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be a sequence of numbers, got {value!r}"
        ) from exc
    if length is not None and len(out) != length:
        raise ValueError(f"{name} must have length {length}, got {len(out)}")
    for i, v in enumerate(out):
        if not math.isfinite(v):
            raise ValueError(f"{name}[{i}] must be finite, got {v!r}")
    return out


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlannerKind(str, Enum):
    """Sampling planner selection."""

    RRT = "rrt"
    RRT_STAR = "rrt_star"
    PRM = "prm"


class PlannerStage(str, Enum):
    """Pipeline stage labels for progress reporting."""

    QUEUED = "queued"
    IK = "ik"
    SAMPLING = "sampling"
    OPTIMIZING = "optimizing"
    PARAMETERISING = "parameterising"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanStatus(str, Enum):
    """Final status of a plan run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannerConfig:
    """Sampler-stage configuration."""

    kind: PlannerKind = PlannerKind.RRT_STAR
    timeout_s: float = 5.0
    smoothing_iterations: int = 50
    range_rad: float = 0.5
    clearance_m: float = 0.005
    qdd_max_rad_s2_default: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PlannerKind):
            object.__setattr__(self, "kind", PlannerKind(self.kind))
        if self.timeout_s <= 0.0:
            raise ValueError(
                f"PlannerConfig.timeout_s must be > 0, got {self.timeout_s}"
            )
        if self.smoothing_iterations < 0:
            raise ValueError(
                "PlannerConfig.smoothing_iterations must be >= 0, got "
                f"{self.smoothing_iterations}"
            )
        if self.range_rad <= 0.0:
            raise ValueError(
                f"PlannerConfig.range_rad must be > 0, got {self.range_rad}"
            )
        if self.clearance_m < 0.0:
            raise ValueError(
                f"PlannerConfig.clearance_m must be >= 0, got {self.clearance_m}"
            )
        if self.qdd_max_rad_s2_default is not None:
            if self.qdd_max_rad_s2_default <= 0.0:
                raise ValueError(
                    "PlannerConfig.qdd_max_rad_s2_default must be > 0 if set, "
                    f"got {self.qdd_max_rad_s2_default}"
                )


@dataclass(frozen=True)
class OptimizerConfig:
    """Trajectory-optimiser configuration (Drake KinematicTrajectoryOptimization)."""

    enabled: bool = False
    max_iterations: int = 100
    min_distance_m: float = 0.005
    spline_degree: int = 5

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", bool(self.enabled))
        if self.max_iterations < 1:
            raise ValueError(
                f"OptimizerConfig.max_iterations must be >= 1, got {self.max_iterations}"
            )
        if self.min_distance_m < 0.0:
            raise ValueError(
                "OptimizerConfig.min_distance_m must be >= 0, got "
                f"{self.min_distance_m}"
            )
        if self.spline_degree not in (3, 5):
            raise ValueError(
                f"OptimizerConfig.spline_degree must be 3 or 5, got {self.spline_degree}"
            )


@dataclass(frozen=True)
class ParameteriserConfig:
    """Time-parameteriser configuration (TOPP-RA)."""

    qd_scale: float = 1.0
    qdd_scale: float = 1.0
    grid_points: int = 200

    def __post_init__(self) -> None:
        if not (0.0 < self.qd_scale <= 1.0):
            raise ValueError(
                "ParameteriserConfig.qd_scale must be in (0, 1], got "
                f"{self.qd_scale}"
            )
        if not (0.0 < self.qdd_scale <= 1.0):
            raise ValueError(
                "ParameteriserConfig.qdd_scale must be in (0, 1], got "
                f"{self.qdd_scale}"
            )
        if self.grid_points < 16:
            raise ValueError(
                "ParameteriserConfig.grid_points must be >= 16, got "
                f"{self.grid_points}"
            )


# ---------------------------------------------------------------------------
# Request / result
# ---------------------------------------------------------------------------


# Pose tuple: ((xyz), (wxyz))
PoseTuple = tuple[
    tuple[float, float, float], tuple[float, float, float, float]
]


@dataclass(frozen=True)
class PlanRequest:
    """One plan request: start config + goal (joint or Cartesian)."""

    robot_id: str
    q_start: tuple[float, ...]
    goal_q: tuple[float, ...] | None = None
    goal_pose: PoseTuple | None = None
    obstacles: tuple[str, ...] = ()
    planner: PlannerConfig = field(default_factory=PlannerConfig)
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    parameteriser: ParameteriserConfig = field(default_factory=ParameteriserConfig)

    def __post_init__(self) -> None:
        if not self.robot_id:
            raise ValueError("PlanRequest.robot_id must not be empty")
        object.__setattr__(
            self, "q_start", _as_float_tuple(self.q_start, name="q_start")
        )
        if len(self.q_start) == 0:
            raise ValueError("PlanRequest.q_start must have at least one joint")

        if self.goal_q is None and self.goal_pose is None:
            raise ValueError(
                "PlanRequest must set exactly one of goal_q or goal_pose; got neither"
            )
        if self.goal_q is not None and self.goal_pose is not None:
            raise ValueError(
                "PlanRequest must set exactly one of goal_q or goal_pose; got both"
            )

        if self.goal_q is not None:
            coerced = _as_float_tuple(self.goal_q, name="goal_q")
            if len(coerced) != len(self.q_start):
                raise ValueError(
                    "PlanRequest.goal_q must match q_start length "
                    f"({len(self.q_start)}), got {len(coerced)}"
                )
            object.__setattr__(self, "goal_q", coerced)

        if self.goal_pose is not None:
            xyz_raw, quat_raw = self.goal_pose
            xyz = _as_float_tuple(xyz_raw, 3, "goal_pose[xyz]")
            quat = _as_float_tuple(quat_raw, 4, "goal_pose[quat_wxyz]")
            norm = math.sqrt(sum(c * c for c in quat))
            if abs(norm - 1.0) > QUAT_NORM_TOL:
                raise ValueError(
                    f"PlanRequest.goal_pose quat must be unit-norm within {QUAT_NORM_TOL}; "
                    f"|q|={norm:.9f}"
                )
            object.__setattr__(self, "goal_pose", (xyz, quat))

        object.__setattr__(self, "obstacles", tuple(self.obstacles))
        for i, name in enumerate(self.obstacles):
            if not isinstance(name, str) or not name:
                raise ValueError(
                    f"PlanRequest.obstacles[{i}] must be a non-empty string, got {name!r}"
                )


@dataclass(frozen=True)
class TrajectorySample:
    """One sample of a time-parameterised trajectory."""

    t_s: float
    q_rad: tuple[float, ...]
    qd_rad_s: tuple[float, ...]
    qdd_rad_s2: tuple[float, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.t_s) or self.t_s < 0.0:
            raise ValueError(
                f"TrajectorySample.t_s must be a finite >= 0, got {self.t_s}"
            )
        q = _as_float_tuple(self.q_rad, name="q_rad")
        qd = _as_float_tuple(self.qd_rad_s, name="qd_rad_s")
        qdd = _as_float_tuple(self.qdd_rad_s2, name="qdd_rad_s2")
        if len(q) == 0:
            raise ValueError("TrajectorySample.q_rad must have at least one joint")
        if len(qd) != len(q) or len(qdd) != len(q):
            raise ValueError(
                "TrajectorySample.qd_rad_s and qdd_rad_s2 must match q_rad length "
                f"({len(q)}); got qd={len(qd)} qdd={len(qdd)}"
            )
        object.__setattr__(self, "q_rad", q)
        object.__setattr__(self, "qd_rad_s", qd)
        object.__setattr__(self, "qdd_rad_s2", qdd)


@dataclass(frozen=True)
class TimedTrajectory:
    """A time-parameterised joint trajectory ready for execution or preview."""

    robot_id: str
    dt_s: float
    samples: tuple[TrajectorySample, ...]
    duration_s: float

    def __post_init__(self) -> None:
        if not self.robot_id:
            raise ValueError("TimedTrajectory.robot_id must not be empty")
        if self.dt_s <= 0.0 or not math.isfinite(self.dt_s):
            raise ValueError(
                f"TimedTrajectory.dt_s must be a finite > 0, got {self.dt_s}"
            )
        object.__setattr__(self, "samples", tuple(self.samples))
        if len(self.samples) < 2:
            raise ValueError(
                "TimedTrajectory.samples must contain at least 2 samples, got "
                f"{len(self.samples)}"
            )
        prev_t = -math.inf
        dof = len(self.samples[0].q_rad)
        for i, s in enumerate(self.samples):
            if not isinstance(s, TrajectorySample):
                raise ValueError(
                    f"TimedTrajectory.samples[{i}] must be a TrajectorySample, got "
                    f"{type(s).__name__}"
                )
            if len(s.q_rad) != dof:
                raise ValueError(
                    f"TimedTrajectory.samples[{i}].q_rad length {len(s.q_rad)} "
                    f"differs from first sample DOF {dof}"
                )
            if s.t_s < prev_t:
                raise ValueError(
                    f"TimedTrajectory.samples must be monotonic in t_s; "
                    f"samples[{i}].t_s={s.t_s} < previous {prev_t}"
                )
            prev_t = s.t_s
        last_t = self.samples[-1].t_s
        if abs(self.duration_s - last_t) > 1e-9:
            raise ValueError(
                "TimedTrajectory.duration_s must equal samples[-1].t_s; "
                f"duration_s={self.duration_s}, last sample t_s={last_t}"
            )

    def joint_waypoints(self) -> tuple[tuple[float, ...], ...]:
        """Return the joint configurations at every sample (drop derivatives)."""
        return tuple(s.q_rad for s in self.samples)

    def sample_at(self, t_s: float) -> TrajectorySample:
        """Linearly interpolate (q, qd, qdd) at time ``t_s``.

        ``t_s`` is clamped to ``[0, duration_s]``. Interpolation is
        per-component; quaternion-style normalisation is not applied because
        the trajectory is in joint space.
        """
        if not math.isfinite(t_s):
            raise ValueError(f"sample_at requires finite t_s, got {t_s}")
        if t_s <= self.samples[0].t_s:
            return self.samples[0]
        if t_s >= self.samples[-1].t_s:
            return self.samples[-1]

        # Binary-search for the segment [lo, hi] containing t_s.
        lo, hi = 0, len(self.samples) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.samples[mid].t_s <= t_s:
                lo = mid
            else:
                hi = mid
        a = self.samples[lo]
        b = self.samples[hi]
        span = b.t_s - a.t_s
        if span <= 0.0:
            return a
        u = (t_s - a.t_s) / span
        q = tuple(a.q_rad[i] + u * (b.q_rad[i] - a.q_rad[i]) for i in range(len(a.q_rad)))
        qd = tuple(
            a.qd_rad_s[i] + u * (b.qd_rad_s[i] - a.qd_rad_s[i])
            for i in range(len(a.qd_rad_s))
        )
        qdd = tuple(
            a.qdd_rad_s2[i] + u * (b.qdd_rad_s2[i] - a.qdd_rad_s2[i])
            for i in range(len(a.qdd_rad_s2))
        )
        return TrajectorySample(t_s=t_s, q_rad=q, qd_rad_s=qd, qdd_rad_s2=qdd)


@dataclass(frozen=True)
class PlanResult:
    """Outcome of a :func:`src.planning.pipeline.plan` call."""

    plan_id: str
    status: PlanStatus
    stage: PlannerStage
    trajectory: TimedTrajectory | None
    elapsed_s: float
    sampler_path_length: int
    optimizer_iterations: int
    parameteriser_grid_points: int
    cache_hit: bool
    error_code: str | None = None
    error_message: str | None = None
    singularity_hint: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, PlanStatus):
            object.__setattr__(self, "status", PlanStatus(self.status))
        if not isinstance(self.stage, PlannerStage):
            object.__setattr__(self, "stage", PlannerStage(self.stage))
        if self.elapsed_s < 0.0 or not math.isfinite(self.elapsed_s):
            raise ValueError(
                f"PlanResult.elapsed_s must be a finite >= 0, got {self.elapsed_s}"
            )
        if self.sampler_path_length < 0:
            raise ValueError(
                "PlanResult.sampler_path_length must be >= 0, got "
                f"{self.sampler_path_length}"
            )
        if self.optimizer_iterations < 0:
            raise ValueError(
                "PlanResult.optimizer_iterations must be >= 0, got "
                f"{self.optimizer_iterations}"
            )
        if self.parameteriser_grid_points < 0:
            raise ValueError(
                "PlanResult.parameteriser_grid_points must be >= 0, got "
                f"{self.parameteriser_grid_points}"
            )
        object.__setattr__(self, "cache_hit", bool(self.cache_hit))
        # Coerce singularity_hint to a tuple of non-negative ints.
        hint = tuple(int(i) for i in self.singularity_hint)
        for v in hint:
            if v < 0:
                raise ValueError(
                    f"PlanResult.singularity_hint entries must be >= 0, got {v}"
                )
        object.__setattr__(self, "singularity_hint", hint)


# ---------------------------------------------------------------------------
# JSON I/O — mirrors src/motion/ir.py
# ---------------------------------------------------------------------------

_TYPE_REGISTRY: dict[str, type] = {
    "PlannerConfig": PlannerConfig,
    "OptimizerConfig": OptimizerConfig,
    "ParameteriserConfig": ParameteriserConfig,
    "PlanRequest": PlanRequest,
    "TrajectorySample": TrajectorySample,
    "TimedTrajectory": TimedTrajectory,
    "PlanResult": PlanResult,
}


def _encode(value: Any) -> Any:
    """Recursively convert a dataclass tree to JSON-friendly primitives."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        out: dict[str, Any] = {"__type__": type(value).__name__}
        for f in fields(value):
            out[f.name] = _encode(getattr(value, f.name))
        return out
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(
        f"Cannot encode value of type {type(value).__name__}: {value!r}"
    )


def _decode(value: Any, hint: Any = None) -> Any:
    """Recursively reconstruct dataclasses from JSON primitives."""
    if value is None:
        return None

    if isinstance(value, dict) and "__type__" in value:
        type_name = value["__type__"]
        cls = _TYPE_REGISTRY.get(type_name)
        if cls is None:
            raise ValueError(f"Unknown __type__ in JSON: {type_name!r}")
        kwargs: dict[str, Any] = {}
        cls_fields = {f.name: f for f in fields(cls)}
        for key, raw in value.items():
            if key == "__type__":
                continue
            if key not in cls_fields:
                # Forward-compat: drop unknown keys rather than crashing.
                continue
            kwargs[key] = _decode(raw, cls_fields[key].type)
        return cls(**kwargs)

    if isinstance(value, dict):
        return {k: _decode(v) for k, v in value.items()}

    if isinstance(value, list):
        decoded = [_decode(v) for v in value]
        if isinstance(hint, str) and hint.startswith("tuple"):
            return tuple(decoded)
        return decoded

    return value


def to_dict(obj: Any) -> Any:
    """Serialize a planning dataclass to a JSON-compatible dict."""
    return _encode(obj)


def from_dict(data: Any, cls: type | None = None) -> Any:
    """Deserialize a dict tree back to planning dataclasses."""
    decoded = _decode(data)
    if cls is not None and not isinstance(decoded, cls):
        raise ValueError(
            f"Decoded type {type(decoded).__name__} does not match expected {cls.__name__}"
        )
    return decoded


__all__ = [
    "PlannerKind",
    "PlannerStage",
    "PlanStatus",
    "PlannerConfig",
    "OptimizerConfig",
    "ParameteriserConfig",
    "PlanRequest",
    "TrajectorySample",
    "TimedTrajectory",
    "PlanResult",
    "PlanningUnavailable",
    "QUAT_NORM_TOL",
    "to_dict",
    "from_dict",
]
