"""Tests for the KUKA KRL post-processor."""

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
from src.post import KRLPost, Post
from src.post.kuka_krl import DAT_SEPARATOR

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


def test_krlpost_satisfies_post_protocol():
    post = KRLPost()
    assert isinstance(post, Post)
    assert post.name == "kuka_krl"
    assert post.file_extension == ".src"


# ---------------------------------------------------------------------------
# Module / file skeleton
# ---------------------------------------------------------------------------


def test_emits_def_end_skeleton(gripper, wobj0):
    prog = Program(
        name="Hello",
        tools=[gripper],
        wobjs=[wobj0],
        procedures=[Procedure("main", body=[])],
    )
    src = KRLPost().emit(prog)
    assert "DEF Hello()" in src
    assert "END" in src
    # Both .src and .dat sections present, separated by the marker.
    assert DAT_SEPARATOR in src
    src_part, _, dat_part = src.partition(DAT_SEPARATOR + "\n")
    assert src_part.startswith("&ACCESS RVP\n")
    assert dat_part.startswith("&ACCESS RVP\n")
    assert "DEFDAT Hello" in dat_part
    assert "ENDDAT" in dat_part


def test_module_metadata_emitted_as_comments(gripper, wobj0):
    prog = Program(
        name="P",
        modules_metadata={"author": "demo", "version": "1.0"},
        tools=[gripper],
        wobjs=[wobj0],
        procedures=[Procedure("main", body=[])],
    )
    src = KRLPost().emit(prog)
    assert "; author: demo" in src
    assert "; version: 1.0" in src


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


def test_move_abs_j_emits_ptp_axis(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    # MOVE_ABS_J → PTP J1 with the AXIS literal in the .dat
    assert "PTP J1" in src
    assert "{AXIS: A1 0, A2 0, A3 0, A4 0, A5 0, A6 0}" in src


def test_move_j_emits_ptp_pose(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    # MOVE_J with pose target uses PTP <pose-name>
    assert re.search(r"PTP P\d+", src)


def test_move_l_emits_lin(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    assert re.search(r"\bLIN P\d+", src)


def test_move_c_emits_circ_via_then_target(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    assert re.search(r"CIRC P\d+, P\d+", src)


def test_zone_radius_sets_apo_cdis_and_c_dis_marker(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    # RADIUS-10 mm move → $APO.CDIS = 10 plus C_DIS continuation marker
    assert "$APO.CDIS = 10" in src
    assert "C_DIS" in src


def test_zone_fine_does_not_emit_apo_for_first_move(gripper, wobj0):
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
    src = KRLPost().emit(prog)
    src_only = src.split(DAT_SEPARATOR, 1)[0]
    assert "$APO.CDIS" not in src_only
    # No C_DIS continuation either, since FINE is exact stop.
    assert "C_DIS" not in src_only


# ---------------------------------------------------------------------------
# IO and Wait
# ---------------------------------------------------------------------------


def test_io_set_emits_out_assign(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    assert "$OUT[1] = TRUE" in src


def test_io_set_zero_emits_false(gripper, wobj0):
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[IOOp("do7", 0, IOKind.SET)])],
    )
    src = KRLPost().emit(prog)
    assert "$OUT[7] = FALSE" in src


def test_wait_seconds_emits_wait_sec(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    assert "WAIT SEC 0.5" in src


def test_wait_signal_emits_wait_for_in(gripper, wobj0):
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[Wait(signal="diReady3")])],
    )
    src = KRLPost().emit(prog)
    assert "WAIT FOR $IN[3]" in src


def test_wait_high_emits_wait_for_in(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    assert "WAIT FOR $IN[2]" in src


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def test_comment_emitted_with_semicolon(gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    src = KRLPost().emit(prog)
    assert "; warmup" in src


# ---------------------------------------------------------------------------
# Speed conversion (boundary: m/s for $VEL.CP, percentage for $VEL_AXIS)
# ---------------------------------------------------------------------------


def test_lin_speed_emitted_in_m_per_s(gripper, wobj0):
    """v_tcp_mm_s = 100 → $VEL.CP = 0.1 m/s for LIN moves."""
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
    src = KRLPost().emit(prog)
    assert "$VEL.CP = 0.1" in src


def test_ptp_speed_emitted_as_axis_percent(gripper, wobj0):
    """v_tcp_mm_s = 5000 → $VEL_AXIS = 50%."""
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(
                MoveKind.MOVE_J,
                PoseTarget((0.5, 0.0, 0.4), (1.0, 0.0, 0.0, 0.0)),
                SpeedData(5000.0), ZoneData.fine(), gripper, wobj0,
            ),
        ])],
    )
    src = KRLPost().emit(prog)
    assert "$VEL_AXIS[1] = 50" in src


# ---------------------------------------------------------------------------
# Distance conversion (m → mm at the boundary)
# ---------------------------------------------------------------------------


def test_distances_converted_to_millimetres(gripper, wobj0):
    pose = PoseTarget((0.5, 0.123, 0.4), (1.0, 0.0, 0.0, 0.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_L, pose, SpeedData(100.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = KRLPost().emit(prog)
    # 0.5 m → 500, 0.123 m → 123, 0.4 m → 400
    assert "X 500" in src and "Y 123" in src and "Z 400" in src


# ---------------------------------------------------------------------------
# Quaternion → ZYX Euler conversion (boundary)
# ---------------------------------------------------------------------------


def test_quat_to_zyx_180_about_z(gripper, wobj0):
    """Rotation 180° about Z: q = (0, 0, 0, 1) → A=180, B=0, C=0."""
    pose = PoseTarget((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_L, pose, SpeedData(100.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = KRLPost().emit(prog)
    # The pose declaration appears in the .dat section.
    assert re.search(r"DECL E6POS P1 = \{X 0, Y 0, Z 0, A 180, B 0, C 0\}", src)


def test_quat_to_zyx_identity(gripper, wobj0):
    """Identity quaternion → A=B=C=0."""
    pose = PoseTarget((0.1, 0.2, 0.3), (1.0, 0.0, 0.0, 0.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_L, pose, SpeedData(100.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = KRLPost().emit(prog)
    assert "{X 100, Y 200, Z 300, A 0, B 0, C 0}" in src


def test_jointtarget_radians_converted_to_degrees(gripper, wobj0):
    home = JointTarget((0.0, math.pi / 2, 0.0, 0.0, math.pi / 6, 0.0))
    prog = Program(
        name="P", tools=[gripper], wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_ABS_J, home, SpeedData(200.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    src = KRLPost().emit(prog)
    # 90° (pi/2) and 30° (pi/6) appear in the joint declaration
    line = next(line for line in src.splitlines() if "DECL E6AXIS" in line)
    assert "A2 90" in line and "A5 30" in line


# ---------------------------------------------------------------------------
# Tool / WObj declarations land in the .dat file
# ---------------------------------------------------------------------------


def test_tool_and_wobj_declared_in_dat(gripper, fixture_wobj):
    prog = Program(
        name="P",
        tools=[gripper],
        wobjs=[fixture_wobj],
        procedures=[Procedure("main", body=[])],
    )
    src = KRLPost().emit(prog)
    _, _, dat = src.partition(DAT_SEPARATOR + "\n")
    # Tool TCP at (0,0,0.120) m → (0,0,120) mm; wobj base at (0.5,0.2,0) m
    assert "DECL FRAME tGripper = {X 0, Y 0, Z 120" in dat
    assert "DECL FRAME wFixture = {X 500, Y 200, Z 0" in dat


# ---------------------------------------------------------------------------
# emit_to_file writes paired .src / .dat files
# ---------------------------------------------------------------------------


def test_emit_to_file_writes_paired_files(tmp_path, gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    out = tmp_path / "hello.src"
    KRLPost().emit_to_file(prog, str(out))
    src_text = (tmp_path / "hello.src").read_text(encoding="utf-8")
    dat_text = (tmp_path / "hello.dat").read_text(encoding="utf-8")
    assert "DEF Hello()" in src_text
    assert "DEFDAT Hello" in dat_text
    # Neither file leaks the cross-file separator
    assert DAT_SEPARATOR not in src_text
    assert DAT_SEPARATOR not in dat_text


def test_emit_to_file_accepts_path_without_extension(tmp_path, gripper, wobj0):
    prog = _hello_program(gripper, wobj0)
    base = tmp_path / "hello"
    KRLPost().emit_to_file(prog, str(base))
    assert (tmp_path / "hello.src").exists()
    assert (tmp_path / "hello.dat").exists()


# ---------------------------------------------------------------------------
# Golden file: a small but realistic KRL program emits exactly as expected
# ---------------------------------------------------------------------------


GOLDEN_HELLO = """\
&ACCESS RVP
&REL 1
DEF Hello()
  $TOOL = {X 0, Y 0, Z 120, A 0, B 0, C 0}
  $BASE = {X 0, Y 0, Z 0, A 0, B 0, C 0}
  $VEL_AXIS[1] = 2; $VEL_AXIS[2] = 2; $VEL_AXIS[3] = 2; $VEL_AXIS[4] = 2; $VEL_AXIS[5] = 2; $VEL_AXIS[6] = 2
  PTP J1
  $VEL.CP = 0.1
  $APO.CDIS = 10
  LIN P1 C_DIS
END
;FOLD .DAT FILE
&ACCESS RVP
&REL 1
DEFDAT Hello
  ; tool tGripper: mass 0.5 kg
  DECL FRAME tGripper = {X 0, Y 0, Z 120, A 0, B 0, C 0}
  DECL FRAME wobj0 = {X 0, Y 0, Z 0, A 0, B 0, C 0}

  DECL E6POS P1 = {X 500, Y 100, Z 400, A 180, B 0, C 180}
  DECL E6AXIS J1 = {AXIS: A1 0, A2 0, A3 0, A4 0, A5 0, A6 0}

ENDDAT
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
    assert KRLPost().emit(prog) == GOLDEN_HELLO


# ---------------------------------------------------------------------------
# Regression: emit_to_file extension handling (audit must-fix #1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("input_path,expected_basename", [
    ("foo",        "foo"),
    ("foo.src",    "foo"),
    ("foo.dat",    "foo"),
    ("foo.txt",    "foo"),
    ("path/to/x",  "path/to/x"),
])
def test_emit_to_file_strips_any_extension(tmp_path, gripper, wobj0,
                                           input_path, expected_basename):
    """Earlier the post only stripped a literal '.src' suffix, so passing
    'foo.dat' wrote 'foo.dat.src' + 'foo.dat.dat'. After the fix any
    trailing extension is stripped and the basename is paired cleanly.
    """
    home = JointTarget((0.0,) * 6)
    prog = Program(
        name="P",
        tools=[gripper],
        wobjs=[wobj0],
        procedures=[Procedure("main", body=[
            Move(MoveKind.MOVE_ABS_J, home, SpeedData(200.0),
                 ZoneData.fine(), gripper, wobj0),
        ])],
    )
    full = tmp_path / input_path
    full.parent.mkdir(parents=True, exist_ok=True)
    KRLPost().emit_to_file(prog, str(full))
    expected_full = tmp_path / expected_basename
    assert (expected_full.parent / (expected_full.name + ".src")).exists()
    assert (expected_full.parent / (expected_full.name + ".dat")).exists()
    # Belt-and-braces: ensure we did NOT produce the bad doubled extension.
    if input_path != expected_basename:
        assert not (full.parent / (full.name + ".src")).exists(), \
            f"emit_to_file wrote a doubled extension: {full}.src"
