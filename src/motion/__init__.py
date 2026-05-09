"""Vendor-neutral motion intermediate representation.

The :mod:`src.motion.ir` module defines the data model that round-trips
between the simulator, the toolpath planner, and post-processors that emit
ABB RAPID, KUKA KRL, and UR Script. Importing from this package re-exports
the public API directly, including the Phase 2 :class:`Recorder` /
:class:`Player` pair that bolts record/playback on top of the IR, and the
Phase 3 :class:`SampledPath` interpolator.
"""

from .frames import FrameMode
from .ir import (
    Comment,
    ConfigData,
    IOKind,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    ProcedureStep,
    Program,
    SpeedData,
    ToolData,
    Wait,
    WObjData,
    ZoneData,
    ZoneKind,
    dump,
    from_dict,
    load,
    to_dict,
)
from .limits import LimitsExceeded, LimitViolation, assert_no_violations, validate_move
from .path import Sample, SampledPath, interpolate_move, interpolate_program
from .player import Player
from .recorder import Recorder

__all__ = [
    "Comment",
    "ConfigData",
    "FrameMode",
    "IOKind",
    "IOOp",
    "JointTarget",
    "LimitViolation",
    "LimitsExceeded",
    "Move",
    "MoveKind",
    "Player",
    "PoseTarget",
    "Procedure",
    "ProcedureStep",
    "Program",
    "Recorder",
    "Sample",
    "SampledPath",
    "SpeedData",
    "ToolData",
    "WObjData",
    "Wait",
    "ZoneData",
    "ZoneKind",
    "assert_no_violations",
    "dump",
    "from_dict",
    "interpolate_move",
    "interpolate_program",
    "load",
    "to_dict",
    "validate_move",
]
