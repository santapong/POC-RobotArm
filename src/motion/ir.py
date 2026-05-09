"""Vendor-neutral motion intermediate representation (IR).

This module is the data model that round-trips between the simulator, the
toolpath planner, and post-processors that emit ABB RAPID, KUKA KRL, and
UR Script. It is intentionally vendor-agnostic: only SI units are stored
(metres, metres/second, radians) and the conversion to vendor-specific
units (mm, deg) lives in the post-processors.

The dataclasses here are all ``frozen=True`` so they're hashable and safe to
share across threads. Validation runs in ``__post_init__`` — bad inputs raise
``ValueError`` immediately, never silently propagate into a generated program.

JSON I/O is provided through :func:`to_dict` / :func:`from_dict` for the
:class:`Program` aggregate. A discriminator key (``__type__``) is used wherever
the schema is a Union (e.g. ``Move.target`` may be either a :class:`PoseTarget`
or a :class:`JointTarget`).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Optional, Union

# ---------------------------------------------------------------------------
# Tolerances and helpers
# ---------------------------------------------------------------------------

QUAT_NORM_TOL = 1e-6


def _as_float_tuple(value: Any, length: Optional[int] = None, name: str = "value") -> tuple[float, ...]:
    """Coerce a sequence to a tuple of floats; optionally enforce length."""
    if value is None:
        raise ValueError(f"{name} must not be None")
    try:
        out = tuple(float(v) for v in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a sequence of numbers, got {value!r}") from exc
    if length is not None and len(out) != length:
        raise ValueError(f"{name} must have length {length}, got {len(out)}")
    return out


def check_quat(quat: tuple[float, ...], name: str = "quaternion") -> None:
    """Validate ``quat`` is a 4-element unit-norm wxyz quaternion.

    Raises :class:`ValueError` with ``name`` interpolated into the message if
    the length is wrong or the norm differs from 1 by more than
    :data:`QUAT_NORM_TOL`. Public so driver / IR call-sites at the boundary
    can enforce the same invariant the IR enforces internally.
    """
    if len(quat) != 4:
        raise ValueError(f"{name} must have 4 components (w, x, y, z), got {len(quat)}")
    norm = math.sqrt(sum(c * c for c in quat))
    if abs(norm - 1.0) > QUAT_NORM_TOL:
        raise ValueError(
            f"{name} must be unit-norm within {QUAT_NORM_TOL}; |q|={norm:.9f}"
        )


def canonicalise_quat(quat: tuple[float, ...]) -> tuple[float, float, float, float]:
    """Return ``quat`` flipped to the ``w >= 0`` hemisphere.

    A quaternion ``q`` and ``-q`` represent the same rotation, but post-processors
    that compute ``angle = 2 * acos(w)`` (URScript's rotation-vector emit, for
    example) pick the long way around when ``w < 0``. Canonicalising every
    quaternion at the IR boundary closes that footgun without changing
    semantics. Caller is expected to have already ensured length 4.
    """
    if quat[0] < 0.0:
        return (-quat[0], -quat[1], -quat[2], -quat[3])
    return (quat[0], quat[1], quat[2], quat[3])


# Backwards-compatible alias for code paths that imported the private name.
_check_quat = check_quat


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ZoneKind(str, Enum):
    """Blend behaviour at a Move endpoint.

    ``FINE`` stops exactly on the target; ``RADIUS`` blends through the target
    along a circular arc of the given radius (vendor terminology: zonedata).
    """

    FINE = "FINE"
    RADIUS = "RADIUS"


class MoveKind(str, Enum):
    """Robot motion primitive."""

    MOVE_J = "MOVE_J"  # joint-interpolated, pose target
    MOVE_L = "MOVE_L"  # linear in Cartesian space, pose target
    MOVE_C = "MOVE_C"  # circular through via point, pose target
    MOVE_ABS_J = "MOVE_ABS_J"  # absolute joint-space target


class IOKind(str, Enum):
    """Digital I/O operation."""

    SET = "SET"
    PULSE = "PULSE"
    WAIT_HIGH = "WAIT_HIGH"
    WAIT_LOW = "WAIT_LOW"


# ---------------------------------------------------------------------------
# Tool / Workobject / Speed / Zone / Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolData:
    """End-effector tool definition.

    The TCP (tool centre point) is expressed in the wrist/flange frame.
    ``mass_kg`` is the tool mass; ``cog_xyz_m`` is its centre of gravity in the
    flange frame. ``robhold`` indicates that the tool is mounted on the robot
    flange (True) rather than fixed in the world while the robot holds the part
    (False, i.e. RTCP mode).
    """

    name: str
    mass_kg: float
    tcp_xyz_m: tuple[float, ...]
    tcp_quat_wxyz: tuple[float, ...]
    cog_xyz_m: tuple[float, ...] = (0.0, 0.0, 0.0)
    robhold: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ToolData.name must not be empty")
        if self.mass_kg < 0.0:
            raise ValueError(f"ToolData.mass_kg must be >= 0, got {self.mass_kg}")
        object.__setattr__(self, "tcp_xyz_m", _as_float_tuple(self.tcp_xyz_m, 3, "tcp_xyz_m"))
        object.__setattr__(
            self, "tcp_quat_wxyz", _as_float_tuple(self.tcp_quat_wxyz, 4, "tcp_quat_wxyz")
        )
        object.__setattr__(self, "cog_xyz_m", _as_float_tuple(self.cog_xyz_m, 3, "cog_xyz_m"))
        _check_quat(self.tcp_quat_wxyz, "tcp_quat_wxyz")
        object.__setattr__(self, "tcp_quat_wxyz", canonicalise_quat(self.tcp_quat_wxyz))
        object.__setattr__(self, "robhold", bool(self.robhold))


@dataclass(frozen=True)
class WObjData:
    """Workobject (a.k.a. user/object frame) definition.

    A workobject combines a *user* frame and an *object* frame. ``base_*``
    expresses the object frame relative to the user frame; ``user_*`` expresses
    the user frame relative to the world (or robot base, when ``robhold`` is
    true).
    """

    name: str
    base_xyz_m: tuple[float, ...]
    base_quat_wxyz: tuple[float, ...]
    user_xyz_m: tuple[float, ...] = (0.0, 0.0, 0.0)
    user_quat_wxyz: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0)
    robhold: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("WObjData.name must not be empty")
        object.__setattr__(self, "base_xyz_m", _as_float_tuple(self.base_xyz_m, 3, "base_xyz_m"))
        object.__setattr__(
            self, "base_quat_wxyz", _as_float_tuple(self.base_quat_wxyz, 4, "base_quat_wxyz")
        )
        object.__setattr__(self, "user_xyz_m", _as_float_tuple(self.user_xyz_m, 3, "user_xyz_m"))
        object.__setattr__(
            self, "user_quat_wxyz", _as_float_tuple(self.user_quat_wxyz, 4, "user_quat_wxyz")
        )
        _check_quat(self.base_quat_wxyz, "base_quat_wxyz")
        _check_quat(self.user_quat_wxyz, "user_quat_wxyz")
        object.__setattr__(self, "base_quat_wxyz", canonicalise_quat(self.base_quat_wxyz))
        object.__setattr__(self, "user_quat_wxyz", canonicalise_quat(self.user_quat_wxyz))


@dataclass(frozen=True)
class SpeedData:
    """Velocity profile.

    ``v_tcp_mm_s`` is the headline TCP linear velocity. The other fields cover
    orientation rate and external-axis rates and have sane defaults that mirror
    common ABB v100/v500 presets. ``a_tcp_mm_s2`` and ``a_ori_deg_s2`` are
    optional acceleration caps; ``None`` means unconstrained.
    """

    v_tcp_mm_s: float
    v_ori_deg_s: float = 500.0
    v_lin_ext_mm_s: float = 5000.0
    v_rot_ext_deg_s: float = 1000.0
    a_tcp_mm_s2: float | None = None
    a_ori_deg_s2: float | None = None

    def __post_init__(self) -> None:
        for fname in ("v_tcp_mm_s", "v_ori_deg_s", "v_lin_ext_mm_s", "v_rot_ext_deg_s"):
            v = getattr(self, fname)
            if v <= 0.0:
                raise ValueError(f"SpeedData.{fname} must be > 0, got {v}")
        if self.a_tcp_mm_s2 is not None and self.a_tcp_mm_s2 <= 0.0:
            raise ValueError(
                f"SpeedData.a_tcp_mm_s2 must be > 0, got {self.a_tcp_mm_s2}"
            )
        if self.a_ori_deg_s2 is not None and self.a_ori_deg_s2 <= 0.0:
            raise ValueError(
                f"SpeedData.a_ori_deg_s2 must be > 0, got {self.a_ori_deg_s2}"
            )


@dataclass(frozen=True)
class ZoneData:
    """Blend zone (a.k.a. zonedata).

    Use :meth:`ZoneData.fine` for an exact stop; otherwise pass
    ``ZoneData(ZoneData.RADIUS, radius_mm=10.0)``.
    """

    # Convenience aliases so callers don't have to import ZoneKind for the
    # common case (``ZoneData(ZoneData.RADIUS, 10.0)``).
    FINE = ZoneKind.FINE
    RADIUS = ZoneKind.RADIUS

    kind: ZoneKind
    radius_mm: float = 0.0

    def __post_init__(self) -> None:
        # Allow string aliases for ergonomic JSON round-tripping.
        if not isinstance(self.kind, ZoneKind):
            object.__setattr__(self, "kind", ZoneKind(self.kind))
        if self.kind == ZoneKind.FINE:
            if self.radius_mm != 0.0:
                raise ValueError("ZoneData.FINE requires radius_mm == 0")
        else:  # RADIUS
            if self.radius_mm <= 0.0:
                raise ValueError("ZoneData.RADIUS requires radius_mm > 0")

    @classmethod
    def fine(cls) -> "ZoneData":
        return cls(ZoneKind.FINE, 0.0)


@dataclass(frozen=True)
class ConfigData:
    """ABB-style configuration data (cf1, cf4, cf6, cfx).

    Other vendors don't expose this, but ABB RAPID needs it and it's harmless
    to carry. Posters for non-ABB targets simply ignore it.
    """

    cf1: int
    cf4: int
    cf6: int
    cfx: int


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JointTarget:
    """Pure joint-space target (radians, SI)."""

    q_rad: tuple[float, ...]
    ext_axes_rad: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        q = _as_float_tuple(self.q_rad, name="q_rad")
        if len(q) == 0:
            raise ValueError("JointTarget.q_rad must have at least one joint")
        object.__setattr__(self, "q_rad", q)
        object.__setattr__(self, "ext_axes_rad", _as_float_tuple(self.ext_axes_rad, name="ext_axes_rad"))


@dataclass(frozen=True)
class PoseTarget:
    """Cartesian (pose) target. ``quat_wxyz`` must be unit-norm."""

    xyz_m: tuple[float, ...]
    quat_wxyz: tuple[float, ...]
    config: Optional[ConfigData] = None
    ext_axes_rad: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "xyz_m", _as_float_tuple(self.xyz_m, 3, "xyz_m"))
        object.__setattr__(self, "quat_wxyz", _as_float_tuple(self.quat_wxyz, 4, "quat_wxyz"))
        object.__setattr__(self, "ext_axes_rad", _as_float_tuple(self.ext_axes_rad, name="ext_axes_rad"))
        _check_quat(self.quat_wxyz, "quat_wxyz")
        object.__setattr__(self, "quat_wxyz", canonicalise_quat(self.quat_wxyz))


# ---------------------------------------------------------------------------
# Procedure steps
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    """Single robot motion primitive."""

    kind: MoveKind
    target: Union[PoseTarget, JointTarget]
    speed: SpeedData
    zone: ZoneData
    tool: ToolData
    wobj: WObjData
    circ_via: Optional[PoseTarget] = None  # MOVE_C only

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MoveKind):
            object.__setattr__(self, "kind", MoveKind(self.kind))

        if self.kind == MoveKind.MOVE_ABS_J:
            if not isinstance(self.target, JointTarget):
                raise ValueError("MOVE_ABS_J requires a JointTarget target")
            if self.circ_via is not None:
                raise ValueError("MOVE_ABS_J must not carry a circ_via")
        elif self.kind in (MoveKind.MOVE_L, MoveKind.MOVE_C):
            if not isinstance(self.target, PoseTarget):
                raise ValueError(f"{self.kind.value} requires a PoseTarget target")
            if self.kind == MoveKind.MOVE_C:
                if self.circ_via is None:
                    raise ValueError("MOVE_C requires circ_via to be set")
                if not isinstance(self.circ_via, PoseTarget):
                    raise ValueError("MOVE_C circ_via must be a PoseTarget")
            else:
                if self.circ_via is not None:
                    raise ValueError("MOVE_L must not carry a circ_via")
        elif self.kind == MoveKind.MOVE_J:
            # MOVE_J accepts either: pose target with joint-interpolated motion.
            if not isinstance(self.target, (PoseTarget, JointTarget)):
                raise ValueError("MOVE_J target must be PoseTarget or JointTarget")
            if self.circ_via is not None:
                raise ValueError("MOVE_J must not carry a circ_via")


@dataclass(frozen=True)
class IOOp:
    """Digital I/O operation."""

    signal: str
    value: Union[int, float]
    kind: IOKind

    def __post_init__(self) -> None:
        if not self.signal:
            raise ValueError("IOOp.signal must not be empty")
        if not isinstance(self.kind, IOKind):
            object.__setattr__(self, "kind", IOKind(self.kind))


@dataclass(frozen=True)
class Wait:
    """Time- or signal-based wait. Exactly one of seconds/signal must be set."""

    seconds: Optional[float] = None
    signal: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.seconds is None) == (self.signal is None):
            raise ValueError("Wait requires exactly one of seconds or signal")
        if self.seconds is not None and self.seconds < 0.0:
            raise ValueError("Wait.seconds must be >= 0")


@dataclass(frozen=True)
class Comment:
    """Free-form comment that posters echo into the generated program."""

    text: str


ProcedureStep = Union[Move, IOOp, Wait, Comment]


# ---------------------------------------------------------------------------
# Procedure / Program
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Procedure:
    """A named subroutine (RAPID PROC, KRL DEF, UR Script def)."""

    name: str
    params: tuple[str, ...] = ()
    body: tuple[ProcedureStep, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Procedure.name must not be empty")
        # Accept lists for ergonomic construction; freeze to tuples.
        object.__setattr__(self, "params", tuple(self.params))
        object.__setattr__(self, "body", tuple(self.body))
        for i, step in enumerate(self.body):
            if not isinstance(step, (Move, IOOp, Wait, Comment)):
                raise ValueError(f"Procedure.body[{i}] is not a ProcedureStep: {type(step).__name__}")


@dataclass(frozen=True)
class Program:
    """Top-level container for a vendor-neutral motion program."""

    name: str
    modules_metadata: dict[str, str] = field(default_factory=dict)
    tools: tuple[ToolData, ...] = ()
    wobjs: tuple[WObjData, ...] = ()
    procedures: tuple[Procedure, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Program.name must not be empty")
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "wobjs", tuple(self.wobjs))
        object.__setattr__(self, "procedures", tuple(self.procedures))
        # frozen dataclass + dict means the dict itself is mutable; that's
        # acceptable given the practical need for ergonomic construction.
        # We do *not* deep-freeze to keep ergonomics; equality still works
        # element-wise.


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------

# Registry mapping the discriminator string to the dataclass. This is used
# both for serialization (to write ``__type__``) and deserialization (to
# resolve a dict back into the right class).
_TYPE_REGISTRY: dict[str, type] = {
    "ToolData": ToolData,
    "WObjData": WObjData,
    "SpeedData": SpeedData,
    "ZoneData": ZoneData,
    "ConfigData": ConfigData,
    "JointTarget": JointTarget,
    "PoseTarget": PoseTarget,
    "Move": Move,
    "IOOp": IOOp,
    "Wait": Wait,
    "Comment": Comment,
    "Procedure": Procedure,
    "Program": Program,
}

# Classes whose dataclass fields contain Union[...] of multiple dataclass types.
# We always emit ``__type__`` so the loader can disambiguate without relying on
# field-name positional cues.
_UNION_FIELDS: dict[type, set[str]] = {
    Move: {"target", "circ_via"},
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
    if isinstance(value, (int, float, bool, str)):
        return value
    raise TypeError(f"Cannot encode value of type {type(value).__name__}: {value!r}")


def _decode(value: Any, hint: Any = None) -> Any:
    """Recursively reconstruct dataclasses from JSON primitives.

    ``hint`` is consulted for non-dataclass primitives where we need to know
    whether to coerce to a tuple (e.g. ``tuple[float, ...]`` fields).
    """
    if value is None:
        return None

    # Dataclass dicts always carry ``__type__``.
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
                # Forward-compat: ignore unknown keys rather than crashing.
                continue
            kwargs[key] = _decode(raw, cls_fields[key].type)
        return cls(**kwargs)

    # Plain dict (e.g. ``modules_metadata: dict[str, str]``)
    if isinstance(value, dict):
        return {k: _decode(v) for k, v in value.items()}

    # List that should remain a list of decoded elements (or be coerced to a tuple).
    if isinstance(value, list):
        decoded = [_decode(v) for v in value]
        if isinstance(hint, str) and hint.startswith("tuple"):
            return tuple(decoded)
        return decoded

    # Primitives pass through; Enums get reconstructed inside __post_init__.
    return value


def to_dict(obj: Any) -> Any:
    """Serialize a dataclass tree (typically a :class:`Program`) to a dict."""
    return _encode(obj)


def from_dict(data: Any, cls: Optional[type] = None) -> Any:
    """Deserialize a dict tree back to dataclasses.

    The ``cls`` argument is currently advisory — the encoder always writes a
    ``__type__`` discriminator so the loader is fully self-describing. It is
    accepted for API symmetry and future use (e.g. legacy data without
    discriminators).
    """
    decoded = _decode(data)
    if cls is not None and not isinstance(decoded, cls):
        raise ValueError(
            f"Decoded type {type(decoded).__name__} does not match expected {cls.__name__}"
        )
    return decoded


def dump(program: Program, path: str) -> None:
    """Serialize ``program`` to ``path`` as pretty-printed JSON (utf-8)."""
    if not isinstance(program, Program):
        raise TypeError(f"dump() expects a Program, got {type(program).__name__}")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(to_dict(program), fh, indent=2)
        fh.write("\n")


def load(path: str) -> Program:
    """Load a :class:`Program` previously written by :func:`dump`."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    obj = from_dict(data, Program)
    return obj


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


__all__ = [
    "Comment",
    "ConfigData",
    "IOKind",
    "IOOp",
    "JointTarget",
    "Move",
    "MoveKind",
    "PoseTarget",
    "Procedure",
    "ProcedureStep",
    "Program",
    "QUAT_NORM_TOL",
    "SpeedData",
    "ToolData",
    "WObjData",
    "Wait",
    "ZoneData",
    "ZoneKind",
    "canonicalise_quat",
    "check_quat",
    "dump",
    "from_dict",
    "load",
    "to_dict",
]
