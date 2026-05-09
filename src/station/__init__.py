"""Station model: scene-graph + CAD import for the RobotStudio-style shell.

The :mod:`src.station.scene` module defines a flat, name-keyed scene graph
that mirrors how RobotStudio describes a station: frames carry parents by
name, and the rest of the entities (robots, tools, workpieces, fixtures,
I/O signals) hang off frames by name. JSON I/O round-trips through the
same ``__type__`` discriminator pattern as :mod:`src.motion.ir` so future
extensions don't break older saves.

The :mod:`src.station.cad_import` module wraps :mod:`trimesh` and
:mod:`ezdxf` for STL / OBJ / PLY meshes and DXF polylines. Both of those
imports are deferred so importing :mod:`src.station.scene` does not pull
heavy CAD dependencies.
"""

from .scene import (
    FixtureEntry,
    Frame,
    IOSignal,
    RobotEntry,
    Station,
    ToolEntry,
    WorkpieceEntry,
    dump,
    from_dict,
    load,
    to_dict,
)

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
