"""Demo program lifted verbatim from ``src/ui/app.py:_demo_program``.

The server keeps its own copy (as agreed in design §A.8 / §F.3). The desktop
app is not modified — both copies are read-only at the IR level.
"""

from __future__ import annotations

from src.motion.ir import (
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    Program,
    SpeedData,
    ToolData,
    WObjData,
    ZoneData,
)


def _make_demo_program() -> Program:
    tool = ToolData(
        name="tool0",
        mass_kg=0.5,
        tcp_xyz_m=(0.0, 0.0, 0.12),
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    wobj = WObjData(
        name="wobj0",
        base_xyz_m=(0.5, 0.0, 0.0),
        base_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    home = JointTarget((0.0,) * 6)
    quat_down = (0.0, 0.0, 1.0, 0.0)
    above = PoseTarget((0.40, 0.10, 0.30), quat_down)
    pick = PoseTarget((0.40, 0.10, 0.10), quat_down)
    v200 = SpeedData(200.0)
    v50 = SpeedData(50.0)
    z10 = ZoneData(ZoneData.RADIUS, 10.0)
    fine = ZoneData.fine()
    return Program(
        name="StationDemo",
        modules_metadata={"author": "POC-RobotArm Station UI"},
        tools=[tool],
        wobjs=[wobj],
        procedures=[
            Procedure(
                "main",
                [],
                [
                    Move(MoveKind.MOVE_ABS_J, home, v200, fine, tool, wobj),
                    Move(MoveKind.MOVE_J, above, v200, z10, tool, wobj),
                    Move(MoveKind.MOVE_L, pick, v50, fine, tool, wobj),
                    Move(MoveKind.MOVE_L, above, v50, z10, tool, wobj),
                    Move(MoveKind.MOVE_ABS_J, home, v200, fine, tool, wobj),
                ],
            ),
        ],
    )


# Module-level constant — immutable after import.
DEMO_PROGRAM: Program = _make_demo_program()

_PROGRAMS: dict[str, Program] = {"demo": DEMO_PROGRAM}


def get_program(program_id: str) -> Program:
    """Return the program for ``program_id``, or raise ``KeyError`` if unknown."""
    if program_id not in _PROGRAMS:
        raise KeyError(f"Unknown program id: {program_id!r}")
    return _PROGRAMS[program_id]


def list_programs() -> list[dict[str, str]]:
    """Return the catalogue of available programs as ``[{"id": ..., "name": ...}]``."""
    return [{"id": k, "name": v.name} for k, v in _PROGRAMS.items()]


__all__ = ["DEMO_PROGRAM", "get_program", "list_programs"]
