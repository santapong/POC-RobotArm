"""Tests for the Universal Robots URScript post-processor."""

from __future__ import annotations

import math
import re

import pytest

from src.motion.ir import (
    Comment,
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
from src.post import Post, URScriptPost

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_urscriptpost_satisfies_post_protocol():
    post = URScriptPost()
    assert isinstance(post, Post)
    assert post.name == "ur_script"
    assert post.file_extension == ".script"


# ---------------------------------------------------------------------------
# Program skeleton: def main(): ... end / main()
# ---------------------------------------------------------------------------


def test_emits_def_main_and_call(gripper, wobj0):
    prog = Program(
        name="Hello",
        tools=[gripper],
        wobjs=[wobj0],
        procedures=[Procedure("main", body=[])],
    )
    src = URScriptPost().emit(prog)
    assert "def main():" in src
    assert src.rstrip().endswith("main()")
    # Single closing 'end' for the def
    assert "\nend\n" in src


def test_program_name_and_metadata_in_header(gripper, wobj0):
    prog = Program(
        name="Hello",
        modules_metadata={"author": "demo", "version": "1.0"},
        tools=[gripper],
        wobjs=[wobj0],
        procedures=[Procedure("main", body=[])],
    )
    src = URScriptPost().emit(prog)
    assert "# program: Hello" in src
    assert "# author: demo" in src
    assert "# version: 1.0" in src


# ---------------------------------------------------------------------------
# Move emission — every MoveKind
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
                IOOp("doGrip1", 1, IOKind.SET),
                Wait(seconds=0.5),
                IOOp("diHome2", 1, IOKind.WAIT_HIGH),
            ]),
        ],
    )


def test_move_abs_j_emits_movej_with_joint_array(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    # MOVE_ABS_J → movej with [j1..j6] joint list
    assert "movej([0, 0, 0, 0, 0, 0]" in src


def test_move_j_emits_movej_with_pose(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    assert re.search(r"movej\(p\[", src)


def test_move_l_emits_movel(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    assert re.search(r"movel\(p\[", src)


def test_move_c_emits_movec_via_then_target(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    assert re.search(r"movec\(p\[[^\]]+\], p\[[^\]]+\],", src)


# ---------------------------------------------------------------------------
# Speed / blend conversion (boundary: mm/s → m/s, mm → m)
# ---------------------------------------------------------------------------


def test_speed_emitted_as_v_in_meters_per_second(gripper, wobj0):
    """v_tcp_mm_s = 100 → ``v=0.1`` in URScript."""
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(
                MoveKind.MOVE_L,
                PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0)),
                SpeedData(100.0), ZoneData.fine(), gripper, wobj0,
            ),
        ])],
    )
    src = URScriptPost().emit(prog)
    assert "v=0.1" in src


def test_blend_radius_emitted_in_meters(gripper, wobj0):
    """Zone radius 10 mm → ``r=0.01`` in URScript."""
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(
                MoveKind.MOVE_L,
                PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0)),
                SpeedData(100.0),
                ZoneData(ZoneData.RADIUS, 10.0),
                gripper, wobj0,
            ),
        ])],
    )
    src = URScriptPost().emit(prog)
    assert "r=0.01" in src


def test_fine_zone_omits_r_argument(gripper, wobj0):
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(
                MoveKind.MOVE_L,
                PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0)),
                SpeedData(100.0), ZoneData.fine(), gripper, wobj0,
            ),
        ])],
    )
    src = URScriptPost().emit(prog)
    move_line = next(line for line in src.splitlines() if "movel(" in line)
    assert "r=" not in move_line


# ---------------------------------------------------------------------------
# IO and Wait
# ---------------------------------------------------------------------------


def test_io_set_emits_set_digital_out_true(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    assert "set_digital_out(1, True)" in src


def test_io_set_zero_emits_false(gripper, wobj0):
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[IOOp("do7", 0, IOKind.SET)])],
    )
    src = URScriptPost().emit(prog)
    assert "set_digital_out(7, False)" in src


def test_wait_seconds_emits_sleep(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    assert "sleep(0.5)" in src


def test_wait_high_emits_while_loop(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    assert "while get_digital_in(2) != True:" in src
    assert "sync()" in src
    # The while loop is followed by a closing 'end' inside the def.
    assert re.search(r"while get_digital_in\(2\) != True:\n\s*sync\(\)\n\s*end", src)


def test_wait_low_emits_while_loop(gripper, wobj0):
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[IOOp("di3", 0, IOKind.WAIT_LOW)])],
    )
    src = URScriptPost().emit(prog)
    assert "while get_digital_in(3) != False:" in src


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def test_comment_emitted_with_hash(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    assert "# warmup" in src


# ---------------------------------------------------------------------------
# Tool / WObj
# ---------------------------------------------------------------------------


def test_set_tcp_emitted_for_active_tool(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = URScriptPost().emit(prog)
    # TCP at (0,0,0.12) m, identity rotation → p[0, 0, 0.12, 0, 0, 0]
    assert "set_tcp(p[0, 0, 0.12, 0, 0, 0])" in src


def test_wobj_emitted_as_comment(gripper, fixture_wobj):
    prog = Program(
        name="P", tools=[gripper], wobjs=[fixture_wobj],
        procedures=[Procedure("main", body=[
            Move(
                MoveKind.MOVE_L,
                PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0)),
                SpeedData(100.0), ZoneData.fine(), gripper, fixture_wobj,
            ),
        ])],
    )
    src = URScriptPost().emit(prog)
    # Wobj is emitted as a comment; identity rotation → all zeros
    assert "# wobj wFixture: base = [0.5, 0.2, 0, 0, 0, 0]" in src


# ---------------------------------------------------------------------------
# Distances pass through unchanged (URScript uses metres natively)
# ---------------------------------------------------------------------------


def test_distances_pass_through_in_meters(gripper, wobj0):
    pose = PoseTarget((0.5, 0.123, 0.4), (1.0, 0.0, 0.0, 0.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_L, pose, SpeedData(100.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = URScriptPost().emit(prog)
    assert "p[0.5, 0.123, 0.4, 0, 0, 0]" in src


def test_jointtarget_radians_pass_through(gripper, wobj0):
    home = JointTarget((0.0, math.pi / 2, 0.0, 0.0, math.pi / 6, 0.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_ABS_J, home, SpeedData(200.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = URScriptPost().emit(prog)
    # pi/2 → 1.570796, pi/6 → 0.523599 (rounded to 6 places)
    assert "1.570796" in src
    assert "0.523599" in src


# ---------------------------------------------------------------------------
# Quaternion → rotation-vector conversion (boundary)
# ---------------------------------------------------------------------------


def test_quat_to_rotvec_180_about_z(gripper, wobj0):
    """Rotation 180° about Z: q = (0, 0, 0, 1) → rotvec = (0, 0, pi)."""
    pose = PoseTarget((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_L, pose, SpeedData(100.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = URScriptPost().emit(prog)
    # pi rounded to 6 places is 3.141593.
    assert "p[0, 0, 0, 0, 0, 3.141593]" in src


def test_quat_to_rotvec_identity_is_zero(gripper, wobj0):
    """Identity quaternion → rotvec = (0, 0, 0)."""
    pose = PoseTarget((0.1, 0.2, 0.3), (1.0, 0.0, 0.0, 0.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_L, pose, SpeedData(100.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = URScriptPost().emit(prog)
    assert "p[0.1, 0.2, 0.3, 0, 0, 0]" in src


def test_quat_to_rotvec_90_about_y(gripper, wobj0):
    """Rotation 90° about Y: q = (cos(45°), 0, sin(45°), 0) → rotvec = (0, pi/2, 0)."""
    c = math.cos(math.pi / 4)
    s = math.sin(math.pi / 4)
    pose = PoseTarget((0.0, 0.0, 0.0), (c, 0.0, s, 0.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_L, pose, SpeedData(100.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = URScriptPost().emit(prog)
    # pi/2 rounded to 6 places: 1.570796
    assert "p[0, 0, 0, 0, 1.570796, 0]" in src


# ---------------------------------------------------------------------------
# emit_to_file
# ---------------------------------------------------------------------------


def test_emit_to_file_writes_script(tmp_path, gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    out = tmp_path / "hello.script"
    URScriptPost().emit_to_file(prog, str(out))
    text = out.read_text(encoding="utf-8")
    assert "def main():" in text
    assert text.rstrip().endswith("main()")


# ---------------------------------------------------------------------------
# Golden file: a small but realistic UR program emits exactly as expected
# ---------------------------------------------------------------------------


GOLDEN_HELLO = """\
# program: Hello
def main():
  set_tcp(p[0, 0, 0.12, 0, 0, 0])
  # wobj wobj0: base = [0, 0, 0, 0, 0, 0]
  movej([0, 0, 0, 0, 0, 0], a=1.4, v=0.2)
  movel(p[0.5, 0.1, 0.4, 0, 3.141593, 0], a=1.2, v=0.1, r=0.01)
end
main()
"""


def test_golden_hello_program(gripper, wobj0):
    home = JointTarget((0.0,) * 6)
    p1 = PoseTarget((0.5, 0.1, 0.4), (0.0, 0.0, 1.0, 0.0))
    prog = Program(
        name="Hello",
        tools=[gripper],
        wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_ABS_J, home, SpeedData(200.0),
                 ZoneData.fine(), gripper, wobj0),
            Move(MoveKind.MOVE_L, p1, SpeedData(100.0),
                 ZoneData(ZoneData.RADIUS, 10.0), gripper, wobj0),
        ])],
    )
    assert URScriptPost().emit(prog) == GOLDEN_HELLO
