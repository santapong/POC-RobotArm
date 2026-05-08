"""Flat scene-graph for a RobotStudio-style station.

This module is the data model that the desktop shell (``src.ui``) edits and
that the simulator / post-processors consume. It is intentionally
thread-safe and dependency-free: only frozen dataclasses, JSON, and the
standard library — no Qt, no trimesh, no PyBullet here.

The scene graph is **flat**: every entity references its parent by *name*
into the ``Station.frames`` dictionary rather than holding a Python
reference to a ``Frame`` object. RobotStudio describes stations the same
way; the flat shape is much friendlier to JSON, undo/redo, and
referential-integrity checks than a recursive object tree.

Validation runs in ``__post_init__`` — bad inputs raise :class:`ValueError`
immediately, never silently propagate into a saved station file.

JSON I/O is provided through :func:`to_dict` / :func:`from_dict` for the
:class:`Station` aggregate. A discriminator key (``__type__``) is used so
future schema extensions don't break older saves, mirroring the convention
used by :mod:`src.motion.ir`.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Literal, Optional, Union

# ---------------------------------------------------------------------------
# Tolerances and helpers
# ---------------------------------------------------------------------------

QUAT_NORM_TOL = 1e-6

IOKindLiteral = Literal["DI", "DO", "AI", "AO"]
_IO_KINDS: tuple[str, ...] = ("DI", "DO", "AI", "AO")


def _as_float_tuple(
    value: Any, length: Optional[int] = None, name: str = "value"
) -> tuple[float, ...]:
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


def _check_quat(quat: tuple[float, ...], name: str) -> None:
    if len(quat) != 4:
        raise ValueError(f"{name} must have 4 components (w, x, y, z), got {len(quat)}")
    norm = math.sqrt(sum(c * c for c in quat))
    if abs(norm - 1.0) > QUAT_NORM_TOL:
        raise ValueError(
            f"{name} must be unit-norm within {QUAT_NORM_TOL}; |q|={norm:.9f}"
        )


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """Named reference frame.

    ``parent`` is either ``None`` (the world / station root) or the *name*
    of another :class:`Frame` registered in the same :class:`Station`. The
    pose ``(xyz_m, quat_wxyz)`` is expressed relative to that parent.
    """

    name: str
    xyz_m: tuple[float, ...]
    quat_wxyz: tuple[float, ...]
    parent: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Frame.name must not be empty")
        object.__setattr__(self, "xyz_m", _as_float_tuple(self.xyz_m, 3, "xyz_m"))
        object.__setattr__(
            self, "quat_wxyz", _as_float_tuple(self.quat_wxyz, 4, "quat_wxyz")
        )
        _check_quat(self.quat_wxyz, "quat_wxyz")
        if self.parent is not None and not self.parent:
            raise ValueError("Frame.parent must be None or a non-empty frame name")


@dataclass(frozen=True)
class RobotEntry:
    """A robot from the catalog placed in the station.

    ``robot_catalog_name`` is a short name (e.g. ``"abb_irb1200"``) resolved
    via :mod:`src.robots.catalog`. ``base_frame`` names the :class:`Frame`
    that the robot's base sits on.
    """

    name: str
    robot_catalog_name: str
    base_frame: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RobotEntry.name must not be empty")
        if not self.robot_catalog_name:
            raise ValueError("RobotEntry.robot_catalog_name must not be empty")
        if not self.base_frame:
            raise ValueError("RobotEntry.base_frame must not be empty")


@dataclass(frozen=True)
class ToolEntry:
    """End-effector mounted on a parent frame (typically a robot flange)."""

    name: str
    parent_frame: str
    mesh_path: Optional[str] = None
    tcp_xyz_m: tuple[float, ...] = (0.0, 0.0, 0.0)
    tcp_quat_wxyz: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ToolEntry.name must not be empty")
        if not self.parent_frame:
            raise ValueError("ToolEntry.parent_frame must not be empty")
        object.__setattr__(self, "tcp_xyz_m", _as_float_tuple(self.tcp_xyz_m, 3, "tcp_xyz_m"))
        object.__setattr__(
            self, "tcp_quat_wxyz", _as_float_tuple(self.tcp_quat_wxyz, 4, "tcp_quat_wxyz")
        )
        _check_quat(self.tcp_quat_wxyz, "tcp_quat_wxyz")


@dataclass(frozen=True)
class WorkpieceEntry:
    """Part to be operated on. Hangs off a parent frame (often a fixture)."""

    name: str
    parent_frame: str
    mesh_path: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("WorkpieceEntry.name must not be empty")
        if not self.parent_frame:
            raise ValueError("WorkpieceEntry.parent_frame must not be empty")


@dataclass(frozen=True)
class FixtureEntry:
    """Static fixture (table, jig, conveyor stand) anchored to a frame."""

    name: str
    parent_frame: str
    mesh_path: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FixtureEntry.name must not be empty")
        if not self.parent_frame:
            raise ValueError("FixtureEntry.parent_frame must not be empty")


@dataclass(frozen=True)
class IOSignal:
    """Single I/O signal definition.

    ``kind`` is one of ``"DI"``, ``"DO"``, ``"AI"``, ``"AO"``. The default
    value type is left flexible (int / float / bool) so analog and digital
    signals share one dataclass.
    """

    name: str
    kind: IOKindLiteral
    default_value: Union[int, float, bool] = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("IOSignal.name must not be empty")
        if self.kind not in _IO_KINDS:
            raise ValueError(
                f"IOSignal.kind must be one of {_IO_KINDS}, got {self.kind!r}"
            )
        if not isinstance(self.default_value, (int, float, bool)):
            raise ValueError(
                "IOSignal.default_value must be int, float, or bool; "
                f"got {type(self.default_value).__name__}"
            )


@dataclass(frozen=True)
class Station:
    """Top-level container for a station scene.

    All collections are tuples (frozen-dataclass-friendly). The flat
    name-keyed graph is enforced at construction time: every named parent
    reference (``Frame.parent``, ``RobotEntry.base_frame``,
    ``ToolEntry.parent_frame``, etc.) must resolve to a frame in
    ``frames``, and names must be unique within their kind.
    """

    name: str
    frames: tuple[Frame, ...] = ()
    robots: tuple[RobotEntry, ...] = ()
    tools: tuple[ToolEntry, ...] = ()
    workpieces: tuple[WorkpieceEntry, ...] = ()
    fixtures: tuple[FixtureEntry, ...] = ()
    io_signals: tuple[IOSignal, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Station.name must not be empty")
        # Accept lists for ergonomic construction; freeze to tuples.
        object.__setattr__(self, "frames", tuple(self.frames))
        object.__setattr__(self, "robots", tuple(self.robots))
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "workpieces", tuple(self.workpieces))
        object.__setattr__(self, "fixtures", tuple(self.fixtures))
        object.__setattr__(self, "io_signals", tuple(self.io_signals))

        frame_names = {f.name for f in self.frames}
        if len(frame_names) != len(self.frames):
            raise ValueError("Station.frames contains duplicate names")

        # Frame parents must resolve to a known frame.
        for fr in self.frames:
            if fr.parent is not None and fr.parent not in frame_names:
                raise ValueError(
                    f"Frame {fr.name!r} has unknown parent {fr.parent!r}"
                )

        for collection_name, items, attr in (
            ("robots", self.robots, "base_frame"),
            ("tools", self.tools, "parent_frame"),
            ("workpieces", self.workpieces, "parent_frame"),
            ("fixtures", self.fixtures, "parent_frame"),
        ):
            seen: set[str] = set()
            for item in items:
                if item.name in seen:
                    raise ValueError(
                        f"Station.{collection_name} contains duplicate name {item.name!r}"
                    )
                seen.add(item.name)
                ref = getattr(item, attr)
                if ref not in frame_names:
                    raise ValueError(
                        f"{type(item).__name__} {item.name!r} references unknown "
                        f"frame {ref!r}"
                    )

        io_names = {s.name for s in self.io_signals}
        if len(io_names) != len(self.io_signals):
            raise ValueError("Station.io_signals contains duplicate names")


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------

# Registry mapping the discriminator string to the dataclass. Used both for
# serialization (to write ``__type__``) and deserialization (to resolve a
# dict back into the right class).
_TYPE_REGISTRY: dict[str, type] = {
    "Frame": Frame,
    "RobotEntry": RobotEntry,
    "ToolEntry": ToolEntry,
    "WorkpieceEntry": WorkpieceEntry,
    "FixtureEntry": FixtureEntry,
    "IOSignal": IOSignal,
    "Station": Station,
}


def _encode(value: Any) -> Any:
    """Recursively convert a dataclass tree to JSON-friendly primitives."""
    if value is None:
        return None
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

    # Plain dict (no __type__) — pass through with values decoded.
    if isinstance(value, dict):
        return {k: _decode(v) for k, v in value.items()}

    # List that should remain a list (or be coerced to a tuple by the hint).
    if isinstance(value, list):
        decoded = [_decode(v) for v in value]
        if isinstance(hint, str) and hint.startswith("tuple"):
            return tuple(decoded)
        return decoded

    # Primitives pass through.
    return value


def to_dict(obj: Any) -> Any:
    """Serialize a dataclass tree (typically a :class:`Station`) to a dict."""
    return _encode(obj)


def from_dict(data: Any, cls: Optional[type] = None) -> Any:
    """Deserialize a dict tree back to dataclasses.

    ``cls`` is advisory — the encoder always writes a ``__type__``
    discriminator so the loader is fully self-describing. It is accepted
    for API symmetry with :mod:`src.motion.ir` and for forward use with
    legacy data.
    """
    decoded = _decode(data)
    if cls is not None and not isinstance(decoded, cls):
        raise ValueError(
            f"Decoded type {type(decoded).__name__} does not match expected {cls.__name__}"
        )
    return decoded


def dump(station: Station, path: str) -> None:
    """Serialize ``station`` to ``path`` as pretty-printed JSON (utf-8)."""
    if not isinstance(station, Station):
        raise TypeError(f"dump() expects a Station, got {type(station).__name__}")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(to_dict(station), fh, indent=2)
        fh.write("\n")


def load(path: str) -> Station:
    """Load a :class:`Station` previously written by :func:`dump`."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    obj = from_dict(data, Station)
    return obj


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


__all__ = [
    "FixtureEntry",
    "Frame",
    "IOSignal",
    "RobotEntry",
    "Station",
    "ToolEntry",
    "WorkpieceEntry",
    "dump",
    "from_dict",
    "load",
    "to_dict",
]
