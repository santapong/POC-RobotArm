"""End-to-end demo: build a small motion program and emit ABB RAPID source.

Run from the repo root::

    python examples/demo_export_rapid.py

This writes ``hello.mod`` next to the script, and prints the source to stdout.
The generated module is loadable into a RobotStudio Virtual Controller
(IRC5 or OmniCore) via *Add Module* in the FlexPendant simulator.
"""

from __future__ import annotations

import os
from pathlib import Path

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
from src.post import RAPIDPost


def build_hello_program() -> Program:
    """Tiny pick-and-place style program for the IRB 1200."""
    tool = ToolData(
        name="tGripper",
        mass_kg=0.5,
        tcp_xyz_m=(0.0, 0.0, 0.120),       # 120 mm tool offset along Z
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        cog_xyz_m=(0.0, 0.0, 0.060),
    )
    wobj = WObjData(
        name="wTable",
        base_xyz_m=(0.5, 0.0, 0.0),         # table sits 500 mm in front of base
        base_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )

    # Joint home pose (all zeros, IRB 1200 home).
    home = JointTarget((0.0,) * 6)

    # Three Cartesian targets, all pointing tool-Z down.
    quat_down = (0.0, 0.0, 1.0, 0.0)        # 180-deg rotation about X
    above_pick = PoseTarget((0.40, 0.10, 0.30), quat_down)
    pick       = PoseTarget((0.40, 0.10, 0.10), quat_down)
    above_drop = PoseTarget((0.40,-0.10, 0.30), quat_down)
    drop       = PoseTarget((0.40,-0.10, 0.10), quat_down)

    v200 = SpeedData(200.0)                  # 200 mm/s travel
    v50  = SpeedData(50.0)                   # 50 mm/s approach/retract
    z10  = ZoneData(ZoneData.RADIUS, 10.0)
    fine = ZoneData.fine()

    body = [
        Move(MoveKind.MOVE_ABS_J, home,        v200, fine, tool, wobj),
        Move(MoveKind.MOVE_J,     above_pick,  v200, z10,  tool, wobj),
        Move(MoveKind.MOVE_L,     pick,        v50,  fine, tool, wobj),
        # ... close gripper here in a real cell ...
        Move(MoveKind.MOVE_L,     above_pick,  v50,  z10,  tool, wobj),
        Move(MoveKind.MOVE_J,     above_drop,  v200, z10,  tool, wobj),
        Move(MoveKind.MOVE_L,     drop,        v50,  fine, tool, wobj),
        # ... open gripper here in a real cell ...
        Move(MoveKind.MOVE_L,     above_drop,  v50,  z10,  tool, wobj),
        Move(MoveKind.MOVE_ABS_J, home,        v200, fine, tool, wobj),
    ]

    return Program(
        name="HelloPickPlace",
        modules_metadata={"target_robot": "ABB IRB 1200-5/0.9", "demo": "pick-and-place"},
        tools=[tool],
        wobjs=[wobj],
        procedures=[Procedure("main", body=body)],
    )


def main() -> None:
    program = build_hello_program()
    rapid_source = RAPIDPost().emit(program)
    print(rapid_source)

    out_path = Path(os.path.dirname(__file__)) / "hello.mod"
    RAPIDPost().emit_to_file(program, str(out_path))
    print(f"# Wrote {out_path}")


if __name__ == "__main__":
    main()
