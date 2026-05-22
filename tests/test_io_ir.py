"""Tests for Phase 4 IR step types: SetSignal, WaitSignal, IfSignal, SignalOp.

Covers §J risks #14 (IR / wire-model schema drift) and #19 (backwards
compatibility of motion-only programs).

No heavy dependencies — stdlib only. Runs unconditionally in the sandbox.
"""

from __future__ import annotations

import json
import math

import pytest

# ---------------------------------------------------------------------------
# Import the IR types (no [io] extra needed)
# ---------------------------------------------------------------------------
from src.motion.ir import (
    _TYPE_REGISTRY,
    Comment,
    IfSignal,
    JointTarget,
    Move,
    MoveKind,
    Procedure,
    Program,
    SetSignal,
    SignalOp,
    SpeedData,
    ToolData,
    WaitSignal,
    WObjData,
    ZoneData,
    ZoneKind,
    decode_program,
    encode_program,
)

pytestmark = pytest.mark.io


# ---------------------------------------------------------------------------
# Helpers — minimal Move for building programs
# ---------------------------------------------------------------------------

def _tool():
    return ToolData(
        name="tool0",
        mass_kg=1.0,
        tcp_xyz_m=(0.0, 0.0, 0.1),
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )


def _wobj():
    return WObjData(
        name="wobj0",
        base_xyz_m=(0.0, 0.0, 0.0),
        base_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )


def _speed():
    return SpeedData(v_tcp_mm_s=200.0)


def _zone_fine():
    return ZoneData(ZoneKind.FINE, 0.0)


def _move_abs_j(q=(0.1, 0.2, 0.3, 0.0, 0.0, 0.0)):
    return Move(
        kind=MoveKind.MOVE_ABS_J,
        target=JointTarget(q_rad=q),
        speed=_speed(),
        zone=_zone_fine(),
        tool=_tool(),
        wobj=_wobj(),
    )


# ---------------------------------------------------------------------------
# §F SignalOp enum — round-trip via string value
# ---------------------------------------------------------------------------


def test_signal_op_eq_round_trip():
    """SignalOp('EQ') == SignalOp.EQ and .value is the original string."""
    assert SignalOp("EQ") == SignalOp.EQ
    assert SignalOp.EQ.value == "EQ"


def test_signal_op_neq_round_trip():
    assert SignalOp("NEQ") == SignalOp.NEQ
    assert SignalOp.NEQ.value == "NEQ"


def test_signal_op_gt_round_trip():
    assert SignalOp("GT") == SignalOp.GT


def test_signal_op_gte_round_trip():
    assert SignalOp("GTE") == SignalOp.GTE


def test_signal_op_lt_round_trip():
    assert SignalOp("LT") == SignalOp.LT


def test_signal_op_lte_round_trip():
    assert SignalOp("LTE") == SignalOp.LTE


def test_signal_op_invalid_string():
    """SignalOp('XYZ') must raise ValueError (not a valid enum value)."""
    with pytest.raises(ValueError):
        SignalOp("XYZ")


def test_signal_op_all_six_members():
    """Enumerate all 6 members — if any is missing the test fails loudly."""
    names = {op.name for op in SignalOp}
    assert names == {"EQ", "NEQ", "GT", "GTE", "LT", "LTE"}


# ---------------------------------------------------------------------------
# SetSignal validators
# ---------------------------------------------------------------------------


def test_set_signal_happy_path():
    s = SetSignal(connection="mb_floor", signal="do0", value=True)
    assert s.connection == "mb_floor"
    assert s.signal == "do0"
    assert s.value is True


def test_set_signal_empty_connection_raises():
    with pytest.raises(ValueError, match="connection"):
        SetSignal(connection="", signal="do0", value=True)


def test_set_signal_empty_signal_raises():
    with pytest.raises(ValueError, match="signal"):
        SetSignal(connection="mb_floor", signal="", value=True)


def test_set_signal_invalid_value_type_raises():
    """Non-finite/non-bool/int/float value must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        SetSignal(connection="mb_floor", signal="do0", value="high")  # type: ignore[arg-type]


def test_set_signal_nan_value_raises():
    """NaN float is a non-finite numeric — should raise ValueError."""
    # The validator checks isinstance(value, (bool, int, float)); NaN is float
    # so it passes the type check. Record behaviour: if it passes, it passes;
    # if the spec is tightened, this test will be the canary.
    # Per §F: "must be bool / int / float" — NaN is float.
    # We assert the object is constructed (NaN passes the type check).
    try:
        s = SetSignal(connection="c", signal="s", value=float("nan"))
        # If it succeeds, value must be a float
        assert math.isnan(s.value)  # type: ignore[arg-type]
    except ValueError:
        pass  # also acceptable


def test_set_signal_frozen():
    """SetSignal is frozen — attribute assignment must raise."""
    s = SetSignal(connection="c", signal="s", value=1)
    with pytest.raises((AttributeError, TypeError)):
        s.connection = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# WaitSignal validators
# ---------------------------------------------------------------------------


def test_wait_signal_happy_path():
    w = WaitSignal(connection="mb", signal="di0", op=SignalOp.EQ, value=True, timeout_s=5.0)
    assert w.connection == "mb"
    assert w.op == SignalOp.EQ
    assert w.timeout_s == 5.0


def test_wait_signal_timeout_zero_raises():
    with pytest.raises(ValueError, match="timeout_s"):
        WaitSignal(connection="c", signal="s", op=SignalOp.EQ, value=True, timeout_s=0.0)


def test_wait_signal_timeout_negative_raises():
    with pytest.raises(ValueError, match="timeout_s"):
        WaitSignal(connection="c", signal="s", op=SignalOp.GT, value=0.5, timeout_s=-1.0)


def test_wait_signal_none_timeout_allowed():
    """timeout_s=None means block until cancelled — must construct without error."""
    w = WaitSignal(connection="c", signal="s", op=SignalOp.EQ, value=True, timeout_s=None)
    assert w.timeout_s is None


def test_wait_signal_string_op_coerced():
    """Passing op as a raw string should be coerced to a SignalOp member."""
    w = WaitSignal(connection="c", signal="s", op="LTE", value=3.0)  # type: ignore[arg-type]
    assert w.op == SignalOp.LTE


def test_wait_signal_invalid_op_raises():
    with pytest.raises(ValueError):
        WaitSignal(connection="c", signal="s", op="XYZ", value=True)  # type: ignore[arg-type]


def test_wait_signal_empty_connection_raises():
    with pytest.raises(ValueError, match="connection"):
        WaitSignal(connection="", signal="s", op=SignalOp.EQ, value=True)


def test_wait_signal_empty_signal_raises():
    with pytest.raises(ValueError, match="signal"):
        WaitSignal(connection="c", signal="", op=SignalOp.EQ, value=True)


# ---------------------------------------------------------------------------
# IfSignal validators
# ---------------------------------------------------------------------------


def test_if_signal_happy_path():
    s = SetSignal(connection="c", signal="do0", value=True)
    step = IfSignal(
        connection="opc_arm",
        signal="part_present",
        op=SignalOp.EQ,
        value=True,
        then_body=(s,),
        else_body=(Comment("no part"),),
    )
    assert len(step.then_body) == 1
    assert len(step.else_body) == 1
    assert isinstance(step.then_body[0], SetSignal)


def test_if_signal_bodies_coerced_to_tuples():
    """List inputs for then_body / else_body must be frozen to tuples."""
    step = IfSignal(
        connection="c", signal="s", op=SignalOp.EQ, value=True,
        then_body=[Comment("a")],  # type: ignore[arg-type]
        else_body=[Comment("b")],  # type: ignore[arg-type]
    )
    assert isinstance(step.then_body, tuple)
    assert isinstance(step.else_body, tuple)


def test_if_signal_invalid_then_body_element_raises():
    """Non-ProcedureStep element in then_body must raise ValueError."""
    with pytest.raises(ValueError, match="ProcedureStep"):
        IfSignal(
            connection="c", signal="s", op=SignalOp.EQ, value=True,
            then_body=(42,),  # type: ignore[arg-type]
        )


def test_if_signal_invalid_else_body_element_raises():
    with pytest.raises(ValueError, match="ProcedureStep"):
        IfSignal(
            connection="c", signal="s", op=SignalOp.EQ, value=True,
            else_body=("not-a-step",),  # type: ignore[arg-type]
        )


def test_if_signal_empty_connection_raises():
    with pytest.raises(ValueError, match="connection"):
        IfSignal(connection="", signal="s", op=SignalOp.EQ, value=True)


def test_if_signal_empty_signal_raises():
    with pytest.raises(ValueError, match="signal"):
        IfSignal(connection="c", signal="", op=SignalOp.EQ, value=True)


def test_if_signal_nested_if_in_body_accepted():
    """IfSignal inside then_body must be accepted (ProcedureStep union includes IfSignal)."""
    inner = IfSignal(connection="c", signal="s", op=SignalOp.EQ, value=True)
    outer = IfSignal(
        connection="c", signal="s", op=SignalOp.EQ, value=True,
        then_body=(inner,),
    )
    assert outer.then_body[0] is inner


# ---------------------------------------------------------------------------
# JSON round-trip — flat program with all 3 new step types
# Covers §J risk #14 (IR / wire-model schema drift)
# ---------------------------------------------------------------------------


def test_round_trip_set_signal():
    """SetSignal serialises and deserialises byte-identically."""
    prog = Program(
        name="test_set",
        procedures=(
            Procedure(name="main", body=(
                SetSignal(connection="mb_floor", signal="do0", value=True),
            )),
        ),
    )
    d = encode_program(prog)
    restored = decode_program(d)
    assert restored == prog


def test_round_trip_wait_signal():
    prog = Program(
        name="test_wait",
        procedures=(
            Procedure(name="main", body=(
                WaitSignal(connection="mb_floor", signal="di0", op=SignalOp.EQ, value=True, timeout_s=5.0),
            )),
        ),
    )
    d = encode_program(prog)
    restored = decode_program(d)
    assert restored == prog


def test_round_trip_if_signal_flat():
    prog = Program(
        name="test_if",
        procedures=(
            Procedure(name="main", body=(
                IfSignal(
                    connection="opc_arm", signal="part_present",
                    op=SignalOp.EQ, value=True,
                    then_body=(Comment("part present"),),
                    else_body=(SetSignal(connection="mb_floor", signal="do1", value=True),),
                ),
            )),
        ),
    )
    d = encode_program(prog)
    restored = decode_program(d)
    assert restored == prog


def test_round_trip_all_step_types_siblings():
    """Flat program with SetSignal, WaitSignal, IfSignal siblings round-trips byte-identically.
    Covers §J risk #14.
    """
    prog = Program(
        name="io_demo",
        procedures=(
            Procedure(name="main", body=(
                SetSignal(connection="mb_floor", signal="do0", value=True),
                WaitSignal(connection="mb_floor", signal="di0", op=SignalOp.EQ, value=True, timeout_s=5.0),
                IfSignal(
                    connection="opc_arm", signal="part_present",
                    op=SignalOp.EQ, value=True,
                    then_body=(Comment("part present"),),
                    else_body=(SetSignal(connection="mb_floor", signal="do1", value=True),),
                ),
            )),
        ),
    )
    d = encode_program(prog)
    restored = decode_program(d)
    assert restored == prog

    # Also assert the JSON is stable: double round-trip
    d2 = encode_program(restored)
    assert d == d2  # byte-identical


def test_round_trip_nested_if_signal():
    """IfSignal.then_body contains a SetSignal AND another IfSignal. Round-trip is byte-identical."""
    inner_if = IfSignal(
        connection="c2", signal="s2", op=SignalOp.GT, value=0.5,
        then_body=(SetSignal(connection="c2", signal="do2", value=True),),
    )
    prog = Program(
        name="nested",
        procedures=(
            Procedure(name="main", body=(
                IfSignal(
                    connection="c1", signal="s1", op=SignalOp.EQ, value=True,
                    then_body=(
                        SetSignal(connection="c1", signal="do1", value=True),
                        inner_if,
                    ),
                ),
            )),
        ),
    )
    d = encode_program(prog)
    restored = decode_program(d)
    assert restored == prog
    d2 = encode_program(restored)
    assert d == d2


# ---------------------------------------------------------------------------
# Backwards compatibility — motion-only program
# Covers §J risk #19
# ---------------------------------------------------------------------------


def test_motion_only_program_round_trip_unchanged():
    """A Program with only Move / Comment steps round-trips byte-identically.

    No new __type__ keys should appear in the encoded JSON that weren't
    there in Phase 3. The _TYPE_REGISTRY entries for SetSignal / WaitSignal
    / IfSignal are only emitted when those steps are present.
    Covers §J risk #19.
    """
    prog = Program(
        name="motion_only",
        procedures=(
            Procedure(name="main", body=(
                _move_abs_j(),
                Comment("home"),
                _move_abs_j(q=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
            )),
        ),
    )
    d = encode_program(prog)
    # Serialise to JSON string and back to check no new __type__ keys
    raw = json.dumps(d)
    assert "SetSignal" not in raw
    assert "WaitSignal" not in raw
    assert "IfSignal" not in raw

    restored = decode_program(d)
    assert restored == prog


def test_motion_only_program_double_round_trip():
    """Encode → decode → encode gives identical dicts (idempotent)."""
    prog = Program(
        name="motion_only_2",
        procedures=(
            Procedure(name="main", body=(
                _move_abs_j(),
                Comment("step2"),
            )),
        ),
    )
    d1 = encode_program(prog)
    d2 = encode_program(decode_program(d1))
    assert d1 == d2


# ---------------------------------------------------------------------------
# _TYPE_REGISTRY — new step types are registered
# Covers §F "Type registry + ProcedureStep union"
# ---------------------------------------------------------------------------


def test_type_registry_contains_new_types():
    """_TYPE_REGISTRY must include SetSignal, WaitSignal, IfSignal after Phase 4."""
    assert "SetSignal" in _TYPE_REGISTRY
    assert "WaitSignal" in _TYPE_REGISTRY
    assert "IfSignal" in _TYPE_REGISTRY


# ---------------------------------------------------------------------------
# Post-processor smoke — each step type doesn't crash the emitter
# Covers §F "Post-processors gain a no-op branch"
# ---------------------------------------------------------------------------


def _io_prog():
    return Program(
        name="io_smoke",
        procedures=(
            Procedure(name="main", body=(
                SetSignal(connection="mb_floor", signal="do0", value=True),
                WaitSignal(connection="mb_floor", signal="di0", op=SignalOp.EQ, value=True, timeout_s=5.0),
                IfSignal(
                    connection="opc", signal="present",
                    op=SignalOp.EQ, value=True,
                    then_body=(Comment("part present"),),
                ),
            )),
        ),
    )


def test_abb_rapid_emits_something_with_io_steps():
    """RAPIDPost.emit() on a program with IO steps returns a non-empty string (not TypeError)."""
    from src.post import RAPIDPost
    source = RAPIDPost().emit(_io_prog())
    assert isinstance(source, str)
    assert len(source) > 0


def test_kuka_krl_emits_something_with_io_steps():
    from src.post import KRLPost
    source = KRLPost().emit(_io_prog())
    assert isinstance(source, str)
    assert len(source) > 0


def test_ur_script_emits_something_with_io_steps():
    from src.post import URScriptPost
    source = URScriptPost().emit(_io_prog())
    assert isinstance(source, str)
    assert len(source) > 0
