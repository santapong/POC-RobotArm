"""Tests for the ABB RAPID post-processor."""

from __future__ import annotations

import math
import re

import pytest

from src.motion.ir import (
    Comment,
    ConfigData,
    IOKind,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    Program,
    SpeedData,
    ToolData,
    Wait,
    WObjData,
    ZoneData,
)
from src.post import Post, RAPIDPost

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tool0() -> ToolData:
    return ToolData("tool0", 0.001, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))


@pytest.fixture
def gripper() -> ToolData:
    return ToolData(
        name="tGripper",
        mass_kg=0.5,
        tcp_xyz_m=(0.0, 0.0, 0.120),
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        cog_xyz_m=(0.0, 0.0, 0.060),
    )


@pytest.fixture
def wobj0() -> WObjData:
    return WObjData("wobj0", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))


@pytest.fixture
def fixture_wobj() -> WObjData:
    return WObjData(
        name="wFixture",
        base_xyz_m=(0.5, 0.2, 0.0),
        base_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        user_xyz_m=(0.0, 0.0, 0.0),
        user_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_rapidpost_satisfies_post_protocol():
    post = RAPIDPost()
    assert isinstance(post, Post)
    assert post.name == "abb_rapid"
    assert post.file_extension == ".mod"


# ---------------------------------------------------------------------------
# Module skeleton
# ---------------------------------------------------------------------------


def test_emits_module_skeleton(tool0, wobj0):
    prog = Program(
        name="Hello",
        procedures=[Procedure("main", body=[])],
    )
    src = RAPIDPost().emit(prog)
    assert src.startswith("MODULE Hello\n")
    assert src.rstrip().endswith("ENDMODULE")
    assert "PROC main()" in src
    assert "ENDPROC" in src


def test_module_metadata_emitted_as_comments():
    prog = Program(
        name="P",
        modules_metadata={"author": "demo", "version": "1.0"},
        procedures=[Procedure("main", body=[])],
    )
    src = RAPIDPost().emit(prog)
    assert "! author: demo" in src
    assert "! version: 1.0" in src


# ---------------------------------------------------------------------------
# Tool / WObj declarations
# ---------------------------------------------------------------------------


def test_tooldata_declared_in_mm_with_mass(gripper):
    prog = Program(
        name="P",
        tools=[gripper],
        procedures=[Procedure("main", body=[])],
    )
    src = RAPIDPost().emit(prog)
    # TCP at (0,0,0.120) m → (0,0,120) mm
    assert "PERS tooldata tGripper := [TRUE, [[0, 0, 120]" in src
    # Mass appears in load record
    assert "[0.5, [0, 0, 60]" in src


def test_wobjdata_declared_in_mm(fixture_wobj):
    prog = Program(
        name="P",
        wobjs=[fixture_wobj],
        procedures=[Procedure("main", body=[])],
    )
    src = RAPIDPost().emit(prog)
    # base xyz 0.5,0.2,0.0 m → 500,200,0 mm. user xyz 0 → [0,0,0].
    assert "PERS wobjdata wFixture" in src
    assert "[500, 200, 0]" in src


def test_tool0_zero_mass_floored():
    """RAPID rejects mass==0; emitter must floor to a tiny positive value."""
    t = ToolData("t0", 0.0, (0, 0, 0), (1, 0, 0, 0))
    prog = Program(name="P", tools=[t], procedures=[Procedure("m", body=[])])
    src = RAPIDPost().emit(prog)
    # Look for a tooldata line where mass is the first element of the inner load
    line = next(line for line in src.splitlines() if "PERS tooldata t0" in line)
    assert "[0.001," in line


# ---------------------------------------------------------------------------
# Move emission
# ---------------------------------------------------------------------------


def _hello_program(tool, wobj) -> Program:
    home = JointTarget((0.0,) * 6)
    p1 = PoseTarget((0.5, 0.1, 0.4), (0.0, 0.0, 1.0, 0.0))
    p2 = PoseTarget((0.4, 0.0, 0.5), (0.0, 0.0, 1.0, 0.0))
    via = PoseTarget((0.45, 0.05, 0.45), (0.0, 0.0, 1.0, 0.0))
    v100 = SpeedData(100.0)
    v200 = SpeedData(200.0)
    z10 = ZoneData(ZoneData.RADIUS, 10.0)
    return Program(
        name="Hello",
        tools=[tool],
        wobjs=[wobj],
        procedures=[
            Procedure("main", body=[
                Comment("warmup"),
                Move(MoveKind.MOVE_ABS_J, home, v200, ZoneData.fine(), tool, wobj),
                Move(MoveKind.MOVE_J,    p1,   v200, z10,              tool, wobj),
                Move(MoveKind.MOVE_L,    p2,   v100, ZoneData.fine(),  tool, wobj),
                Move(MoveKind.MOVE_C,    p2,   v100, z10,              tool, wobj, circ_via=via),
                IOOp("doGrip", 1, IOKind.SET),
                Wait(seconds=0.5),
                IOOp("diHome", 1, IOKind.WAIT_HIGH),
            ]),
        ],
    )


def test_movej_uses_predefined_speed_and_zone(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = RAPIDPost().emit(prog)
    # Predefined v200 + z10 reused; tool wins; wobj0 omitted (default)
    # j1 is the absolute joint home target emitted first.
    assert "MoveAbsJ j1, v200, fine, tGripper" in src
    assert "MoveJ p1, v200, z10, tGripper" in src
    assert "MoveL p2, v100, fine, tGripper" in src


def test_movec_emits_via_then_target(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = RAPIDPost().emit(prog)
    # The via and the target are both PoseTargets; via should appear first
    assert re.search(r"MoveC p\d+, p\d+, v100, z10, tGripper", src)


def test_io_set_pulse_wait(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = RAPIDPost().emit(prog)
    assert "SetDO doGrip, 1;" in src
    assert "WaitTime 0.5;" in src
    assert "WaitDI diHome, 1;" in src


def test_comment_emitted_as_bang_line(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = RAPIDPost().emit(prog)
    assert "! warmup" in src


def test_non_default_wobj_passed_via_switch(gripper, fixture_wobj):
    prog = Program(
        name="P",
        tools=[gripper],
        wobjs=[fixture_wobj],
        procedures=[Procedure("main", body=[
            Move(
                MoveKind.MOVE_L,
                PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0)),
                SpeedData(100.0),
                ZoneData.fine(),
                gripper,
                fixture_wobj,
            ),
        ])],
    )
    src = RAPIDPost().emit(prog)
    assert "\\WObj:=wFixture" in src
    assert "MoveL p1, v100, fine, tGripper\\WObj:=wFixture;" in src


# ---------------------------------------------------------------------------
# Custom speed / zone declarations
# ---------------------------------------------------------------------------


def test_non_predefined_speed_gets_custom_decl(gripper, wobj0):
    odd_speed = SpeedData(v_tcp_mm_s=137.5)
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(
                MoveKind.MOVE_L,
                PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0)),
                odd_speed, ZoneData.fine(), gripper, wobj0,
            ),
        ])],
    )
    src = RAPIDPost().emit(prog)
    assert "CONST speeddata v_137p5_500" in src
    assert "MoveL p1, v_137p5_500" in src


def test_non_predefined_zone_gets_custom_decl(gripper, wobj0):
    odd_zone = ZoneData(ZoneData.RADIUS, 7.5)
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(
                MoveKind.MOVE_L,
                PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0)),
                SpeedData(100.0), odd_zone, gripper, wobj0,
            ),
        ])],
    )
    src = RAPIDPost().emit(prog)
    assert "CONST zonedata z_7p5" in src
    assert "MoveL p1, v100, z_7p5" in src


# ---------------------------------------------------------------------------
# Joint angle conversion
# ---------------------------------------------------------------------------


def test_jointtarget_radians_converted_to_degrees(gripper, wobj0):
    home = JointTarget((0.0, math.pi / 2, 0.0, 0.0, math.pi / 6, 0.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_ABS_J, home, SpeedData(200.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = RAPIDPost().emit(prog)
    # 90deg and 30deg appear in the jointtarget declaration
    line = next(line for line in src.splitlines() if "CONST jointtarget" in line)
    assert "90" in line and "30" in line


# ---------------------------------------------------------------------------
# Configuration data
# ---------------------------------------------------------------------------


def test_pose_target_with_config(gripper, wobj0):
    cfg = ConfigData(0, 0, -1, 0)
    pose = PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0), config=cfg)
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_L, pose, SpeedData(100.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = RAPIDPost().emit(prog)
    assert "[0, 0, -1, 0]" in src


def test_pose_target_default_config_is_zeros(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = RAPIDPost().emit(prog)
    # All robtargets have [0, 0, 0, 0] config since none specify one.
    assert src.count("[0, 0, 0, 0]") >= 3


# ---------------------------------------------------------------------------
# emit_to_file
# ---------------------------------------------------------------------------


def test_emit_to_file_writes_module(tmp_path, gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    out = tmp_path / "hello.mod"
    RAPIDPost().emit_to_file(prog, str(out))
    text = out.read_text(encoding="utf-8")
    assert text.startswith("MODULE Hello\n")
    assert "ENDMODULE" in text


# ---------------------------------------------------------------------------
# Golden file: a small but realistic ABB program emits exactly as expected
# ---------------------------------------------------------------------------


GOLDEN_HELLO = """\
MODULE Hello

  PERS tooldata tGripper := [TRUE, [[0, 0, 120], [1, 0, 0, 0]], [0.5, [0, 0, 60], [1, 0, 0, 0], 0, 0, 0]];

  CONST robtarget p1 := [[500, 100, 400], [0, 0, 1, 0], [0, 0, 0, 0], [9E9, 9E9, 9E9, 9E9, 9E9, 9E9]];
  CONST jointtarget j1 := [[0, 0, 0, 0, 0, 0], [9E9, 9E9, 9E9, 9E9, 9E9, 9E9]];

  PROC main()
    MoveAbsJ j1, v200, fine, tGripper;
    MoveL p1, v100, z10, tGripper;
  ENDPROC

ENDMODULE
"""


def test_golden_hello_program(gripper, wobj0):
    home = JointTarget((0.0,) * 6)
    p1 = PoseTarget((0.5, 0.1, 0.4), (0.0, 0.0, 1.0, 0.0))
    prog = Program(
        name="Hello",
        tools=[gripper],  # wobj0 is the default; omit to exercise that path
        procedures=[
            Procedure("main", body=[
                Move(MoveKind.MOVE_ABS_J, home, SpeedData(200.0),
                     ZoneData.fine(), gripper, wobj0),
                Move(MoveKind.MOVE_L, p1, SpeedData(100.0),
                     ZoneData(ZoneData.RADIUS, 10.0), gripper, wobj0),
            ]),
        ],
    )
    assert RAPIDPost().emit(prog) == GOLDEN_HELLO
