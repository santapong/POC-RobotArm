"""Tests for the in-memory motion recorder (:mod:`src.motion.recorder`).

These tests pin down the contract advertised by :class:`Recorder`: every
``record_*`` helper must append the right IR step in insertion order; the
``set_*`` mutators must affect *future* moves only; and the recorder must
materialise into a JSON-round-trippable :class:`Program`.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from src.motion import (
    Comment,
    IOKind,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    Program,
    Recorder,
    SpeedData,
    ToolData,
    Wait,
    WObjData,
    ZoneData,
    ZoneKind,
    dump,
    load,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _identity_quat() -> tuple[float, float, float, float]:
    return (1.0, 0.0, 0.0, 0.0)


@pytest.fixture
def tool() -> ToolData:
    return ToolData("tool0", 0.5, (0.0, 0.0, 0.1), _identity_quat())


@pytest.fixture
def wobj() -> WObjData:
    return WObjData("wobj0", (0.0, 0.0, 0.0), _identity_quat())


@pytest.fixture
def recorder(tool: ToolData, wobj: WObjData) -> Recorder:
    return Recorder(default_tool=tool, default_wobj=wobj)


# ---------------------------------------------------------------------------
# Constructor / type validation
# ---------------------------------------------------------------------------


def test_recorder_construct_with_defaults(tool: ToolData, wobj: WObjData) -> None:
    """Default speed/zone are populated when not supplied."""
    rec = Recorder(default_tool=tool, default_wobj=wobj)
    assert rec.default_tool is tool
    assert rec.default_wobj is wobj
    assert isinstance(rec.default_speed, SpeedData)
    assert rec.default_speed.v_tcp_mm_s == 100.0
    assert isinstance(rec.default_zone, ZoneData)
    assert rec.default_zone.kind == ZoneKind.FINE
    assert len(rec) == 0


def test_recorder_rejects_wrong_default_types(tool: ToolData, wobj: WObjData) -> None:
    with pytest.raises(TypeError, match="default_tool"):
        Recorder(default_tool="not a tool", default_wobj=wobj)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="default_wobj"):
        Recorder(default_tool=tool, default_wobj="not a wobj")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="default_speed"):
        Recorder(
            default_tool=tool,
            default_wobj=wobj,
            default_speed="fast",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="default_zone"):
        Recorder(
            default_tool=tool,
            default_wobj=wobj,
            default_zone="fine",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# record_* helpers
# ---------------------------------------------------------------------------


def test_record_move_joint_creates_move_abs_j_with_right_joint_count(
    recorder: Recorder, tool: ToolData, wobj: WObjData
) -> None:
    q = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    move = recorder.record_move_joint(q)

    assert isinstance(move, Move)
    assert move.kind == MoveKind.MOVE_ABS_J
    assert isinstance(move.target, JointTarget)
    assert move.target.q_rad == q
    assert len(move.target.q_rad) == 6
    # Defaults must be propagated by reference (frozen instances).
    assert move.tool is tool
    assert move.wobj is wobj
    assert move.speed is recorder.default_speed
    assert move.zone is recorder.default_zone
    # Logged in order.
    assert recorder.log == (move,)
    assert len(recorder) == 1


def test_record_move_linear_creates_move_l_with_supplied_pose(
    recorder: Recorder, tool: ToolData, wobj: WObjData
) -> None:
    xyz = (0.5, 0.1, 0.4)
    quat = (1.0, 0.0, 0.0, 0.0)
    move = recorder.record_move_linear(xyz, quat)

    assert isinstance(move, Move)
    assert move.kind == MoveKind.MOVE_L
    assert isinstance(move.target, PoseTarget)
    assert move.target.xyz_m == xyz
    assert move.target.quat_wxyz == quat
    assert move.tool is tool
    assert move.wobj is wobj
    assert recorder.log == (move,)


def test_record_io_appends_io_op(recorder: Recorder) -> None:
    op = recorder.record_io("do_grip", 1, IOKind.SET)
    assert isinstance(op, IOOp)
    assert op.signal == "do_grip"
    assert op.value == 1
    assert op.kind == IOKind.SET
    assert recorder.log == (op,)
    # Default kind == IOKind.SET when omitted.
    op2 = recorder.record_io("do_release", 0)
    assert op2.kind == IOKind.SET


def test_record_wait_appends_time_wait(recorder: Recorder) -> None:
    wait = recorder.record_wait(1.5)
    assert isinstance(wait, Wait)
    assert wait.seconds == 1.5
    assert wait.signal is None
    assert recorder.log == (wait,)


def test_record_comment_appends_comment(recorder: Recorder) -> None:
    cmt = recorder.record_comment("startup")
    assert isinstance(cmt, Comment)
    assert cmt.text == "startup"
    assert recorder.log == (cmt,)


# ---------------------------------------------------------------------------
# set_speed / set_zone modal semantics
# ---------------------------------------------------------------------------


def test_set_speed_affects_only_subsequent_moves(recorder: Recorder) -> None:
    initial_speed = recorder.default_speed
    move_a = recorder.record_move_joint((0.0,) * 6)

    new_speed = SpeedData(250.0)
    recorder.set_speed(new_speed)
    assert recorder.default_speed is new_speed

    move_b = recorder.record_move_joint((0.1,) * 6)

    # The earlier move must retain the original speed.
    assert move_a.speed is initial_speed
    # The later move picks up the new modal speed.
    assert move_b.speed is new_speed


def test_set_zone_affects_only_subsequent_moves(recorder: Recorder) -> None:
    initial_zone = recorder.default_zone

    move_a = recorder.record_move_joint((0.0,) * 6)

    new_zone = ZoneData(ZoneKind.RADIUS, 10.0)
    recorder.set_zone(new_zone)
    assert recorder.default_zone is new_zone

    move_b = recorder.record_move_linear((0.5, 0.0, 0.4), _identity_quat())

    assert move_a.zone is initial_zone
    assert move_b.zone is new_zone


def test_set_speed_rejects_wrong_type(recorder: Recorder) -> None:
    with pytest.raises(TypeError, match="speed"):
        recorder.set_speed("fast")  # type: ignore[arg-type]


def test_set_zone_rejects_wrong_type(recorder: Recorder) -> None:
    with pytest.raises(TypeError, match="zone"):
        recorder.set_zone("fine")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# as_program
# ---------------------------------------------------------------------------


def test_as_program_preserves_insertion_order(
    recorder: Recorder, tool: ToolData, wobj: WObjData
) -> None:
    """The Program's procedure body must mirror the recording order exactly."""
    recorder.record_comment("startup")
    recorder.record_move_joint((0.0,) * 6)
    recorder.record_move_linear((0.5, 0.1, 0.4), _identity_quat())
    recorder.record_io("do_grip", 1, IOKind.SET)
    recorder.record_wait(0.25)

    prog = recorder.as_program(name="test_program")

    assert isinstance(prog, Program)
    assert prog.name == "test_program"
    assert prog.tools == (tool,)
    assert prog.wobjs == (wobj,)
    assert len(prog.procedures) == 1

    proc = prog.procedures[0]
    assert isinstance(proc, Procedure)
    assert proc.name == "main"
    assert len(proc.body) == 5

    # Verify types in order.
    assert isinstance(proc.body[0], Comment)
    assert isinstance(proc.body[1], Move)
    assert proc.body[1].kind == MoveKind.MOVE_ABS_J
    assert isinstance(proc.body[2], Move)
    assert proc.body[2].kind == MoveKind.MOVE_L
    assert isinstance(proc.body[3], IOOp)
    assert isinstance(proc.body[4], Wait)


def test_as_program_default_name_is_recording(recorder: Recorder) -> None:
    recorder.record_move_joint((0.0,) * 6)
    prog = recorder.as_program()
    assert prog.name == "recording"


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_program_round_trips_through_json(recorder: Recorder) -> None:
    """A recording must survive a dump/load cycle without loss."""
    recorder.record_comment("hello")
    recorder.record_move_joint((0.0, 0.1, 0.2, 0.3, 0.4, 0.5))
    recorder.record_move_linear((0.5, 0.1, 0.4), _identity_quat())
    recorder.set_zone(ZoneData(ZoneKind.RADIUS, 25.0))
    recorder.record_move_linear((0.6, 0.1, 0.4), _identity_quat())
    recorder.record_io("do_grip", 1, IOKind.SET)
    recorder.record_wait(0.5)

    prog = recorder.as_program(name="json_rt")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "rec.json")
        dump(prog, path)
        assert os.path.isfile(path)
        reloaded = load(path)

    assert isinstance(reloaded, Program)
    assert reloaded == prog
    # Spot-check that the modal zone change survived.
    body = reloaded.procedures[0].body
    assert body[2].zone.kind == ZoneKind.FINE
    assert body[3].zone.kind == ZoneKind.RADIUS
    assert body[3].zone.radius_mm == 25.0


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


def test_clear_empties_log_but_keeps_defaults(recorder: Recorder) -> None:
    recorder.record_move_joint((0.0,) * 6)
    recorder.record_comment("note")
    assert len(recorder) == 2

    saved_speed = recorder.default_speed
    saved_zone = recorder.default_zone
    saved_tool = recorder.default_tool
    saved_wobj = recorder.default_wobj

    recorder.clear()

    assert len(recorder) == 0
    assert recorder.log == ()
    # Defaults must be untouched.
    assert recorder.default_speed is saved_speed
    assert recorder.default_zone is saved_zone
    assert recorder.default_tool is saved_tool
    assert recorder.default_wobj is saved_wobj

    # Recording continues to work after clear().
    move = recorder.record_move_joint((0.1,) * 6)
    assert recorder.log == (move,)
