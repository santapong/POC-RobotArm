"""Vendor-neutral motion intermediate representation.

The :mod:`src.motion.ir` module defines the data model that round-trips
between the simulator, the toolpath planner, and post-processors that emit
ABB RAPID, KUKA KRL, and UR Script. Importing from this package re-exports
the public API directly, including the Phase 2 :class:`Recorder` /
:class:`Player` pair that bolts record/playback on top of the IR.
"""

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
from .player import Player
from .recorder import Recorder

__all__ = [
    "Comment",
    "ConfigData",
    "IOKind",
    "IOOp",
    "JointTarget",
    "Move",
    "MoveKind",
    "Player",
    "PoseTarget",
    "Procedure",
    "ProcedureStep",
    "Program",
    "Recorder",
    "SpeedData",
    "ToolData",
    "WObjData",
    "Wait",
    "ZoneData",
    "ZoneKind",
    "dump",
    "from_dict",
    "load",
    "to_dict",
]
