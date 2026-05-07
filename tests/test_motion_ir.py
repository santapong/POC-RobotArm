"""Tests for the vendor-neutral motion IR (src.motion.ir)."""

from __future__ import annotations

import json
import os
import tempfile

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
    ZoneKind,
    dump,
    from_dict,
    load,
    to_dict,
)

# ---------------------------------------------------------------------------
# Fixtures: small, valid building blocks used across the suite.
# ---------------------------------------------------------------------------


def _identity_quat() -> tuple[float, float, float, float]:
    return (1.0, 0.0, 0.0, 0.0)


def _make_tool() -> ToolData:
    return ToolData("tool0", 0.5, (0.0, 0.0, 0.1), _identity_quat())


def _make_wobj() -> WObjData:
    return WObjData("wobj0", (0.0, 0.0, 0.0), _identity_quat())


def _make_speed() -> SpeedData:
    return SpeedData(100.0)


def _make_pose() -> PoseTarget:
    return PoseTarget((0.5, 0.1, 0.4), _identity_quat())


def _make_joint(dof: int = 6) -> JointTarget:
    return JointTarget(tuple(0.0 for _ in range(dof)))


def _make_program() -> Program:
    tool = _make_tool()
    wobj = _make_wobj()
    speed = _make_speed()
    home = _make_joint(6)
    p1 = _make_pose()
    via = PoseTarget((0.55, 0.1, 0.45), _identity_quat())
    p2 = PoseTarget((0.6, 0.1, 0.4), _identity_quat())
    return Program(
        name="hello",
        modules_metadata={"author": "demo", "rev": "1"},
        tools=[tool],
        wobjs=[wobj],
        procedures=[
            Procedure(
                "main",
                [],
                [
                    Comment("startup"),
                    Move(MoveKind.MOVE_ABS_J, home, speed, ZoneData.fine(), tool, wobj),
                    Move(
                        MoveKind.MOVE_L,
                        p1,
                        speed,
                        ZoneData(ZoneKind.RADIUS, 10.0),
                        tool,
                        wobj,
                    ),
                    Move(
                        MoveKind.MOVE_C,
                        p2,
                        speed,
                        ZoneData(ZoneKind.RADIUS, 5.0),
                        tool,
                        wobj,
                        circ_via=via,
                    ),
                    IOOp("do_grip", 1, IOKind.SET),
                    Wait(seconds=0.25),
                    Wait(signal="di_ready"),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------


def test_construct_each_dataclass():
    """Every leaf dataclass can be constructed with valid inputs."""
    tool = ToolData("t", 1.0, (0.0, 0.0, 0.1), _identity_quat(), cog_xyz_m=(0.01, 0.0, 0.05))
    wobj = WObjData("w", (0.1, 0.0, 0.0), _identity_quat(), robhold=True)
    speed = SpeedData(250.0, v_ori_deg_s=720.0)
    zone_fine = ZoneData.fine()
    zone_radius = ZoneData(ZoneKind.RADIUS, 25.0)
    config = ConfigData(0, 0, 0, 0)
    joint = JointTarget((0.0, -1.57, 0.0, -1.57, 0.0, 0.0), ext_axes_rad=(0.0,))
    pose = PoseTarget((0.4, 0.0, 0.3), _identity_quat(), config=config)
    move_l = Move(MoveKind.MOVE_L, pose, speed, zone_radius, tool, wobj)
    move_abs_j = Move(MoveKind.MOVE_ABS_J, joint, speed, zone_fine, tool, wobj)
    via = PoseTarget((0.45, 0.05, 0.3), _identity_quat())
    p_end = PoseTarget((0.5, 0.0, 0.3), _identity_quat())
    move_c = Move(MoveKind.MOVE_C, p_end, speed, zone_radius, tool, wobj, circ_via=via)
    io_op = IOOp("do_signal", 1, IOKind.SET)
    wait_t = Wait(seconds=0.5)
    wait_s = Wait(signal="di_ready")
    comment = Comment("hello")
    proc = Procedure("subroutine", ("arg1",), (move_l, comment))
    prog = Program("p", {}, (tool,), (wobj,), (proc,))

    # Hashability (frozen dataclass invariant) — every leaf should be hashable.
    for obj in (tool, wobj, speed, zone_fine, zone_radius, config, joint, pose,
                move_l, move_abs_j, move_c, io_op, wait_t, wait_s, comment):
        hash(obj)
    assert prog.name == "p"
    assert proc.body[0] is move_l


# ---------------------------------------------------------------------------
# 2. Validation: bad quaternions
# ---------------------------------------------------------------------------


def test_validation_rejects_non_unit_quaternion():
    with pytest.raises(ValueError, match="unit-norm"):
        PoseTarget((0.0, 0.0, 0.0), (1.0, 1.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="unit-norm"):
        ToolData("t", 1.0, (0.0, 0.0, 0.0), (0.5, 0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="unit-norm"):
        WObjData("w", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0))


def test_validation_rejects_wrong_length_quaternion():
    with pytest.raises(ValueError, match="length 4"):
        PoseTarget((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# 3. Validation: speeds and zones
# ---------------------------------------------------------------------------


def test_validation_rejects_non_positive_speeds():
    with pytest.raises(ValueError, match="v_tcp_mm_s"):
        SpeedData(0.0)
    with pytest.raises(ValueError, match="v_tcp_mm_s"):
        SpeedData(-10.0)
    with pytest.raises(ValueError, match="v_ori_deg_s"):
        SpeedData(100.0, v_ori_deg_s=0.0)


def test_validation_zone_kind_radius_relationship():
    # FINE with non-zero radius must fail.
    with pytest.raises(ValueError, match="FINE"):
        ZoneData(ZoneKind.FINE, 5.0)
    # RADIUS with zero radius must fail.
    with pytest.raises(ValueError, match="RADIUS"):
        ZoneData(ZoneKind.RADIUS, 0.0)
    # RADIUS with negative radius must fail.
    with pytest.raises(ValueError, match="RADIUS"):
        ZoneData(ZoneKind.RADIUS, -1.0)
    # Sanity: valid pairs work.
    assert ZoneData.fine().kind == ZoneKind.FINE
    assert ZoneData(ZoneKind.RADIUS, 10.0).radius_mm == 10.0


# ---------------------------------------------------------------------------
# 4. Validation: Move kind / target type matrix
# ---------------------------------------------------------------------------


def test_validation_rejects_mismatched_move_kind_and_target():
    tool = _make_tool()
    wobj = _make_wobj()
    speed = _make_speed()
    pose = _make_pose()
    joint = _make_joint(6)
    via = _make_pose()

    # MOVE_ABS_J with PoseTarget: rejected.
    with pytest.raises(ValueError, match="MOVE_ABS_J requires a JointTarget"):
        Move(MoveKind.MOVE_ABS_J, pose, speed, ZoneData.fine(), tool, wobj)

    # MOVE_L with JointTarget: rejected.
    with pytest.raises(ValueError, match="MOVE_L requires a PoseTarget"):
        Move(MoveKind.MOVE_L, joint, speed, ZoneData.fine(), tool, wobj)

    # MOVE_C with JointTarget: rejected.
    with pytest.raises(ValueError, match="MOVE_C requires a PoseTarget"):
        Move(MoveKind.MOVE_C, joint, speed, ZoneData.fine(), tool, wobj, circ_via=via)

    # MOVE_C without circ_via: rejected.
    with pytest.raises(ValueError, match="MOVE_C requires circ_via"):
        Move(MoveKind.MOVE_C, pose, speed, ZoneData.fine(), tool, wobj)

    # MOVE_L with circ_via: rejected (circ_via is MOVE_C only).
    with pytest.raises(ValueError, match="MOVE_L must not carry a circ_via"):
        Move(MoveKind.MOVE_L, pose, speed, ZoneData.fine(), tool, wobj, circ_via=via)


def test_joint_target_must_be_non_empty():
    with pytest.raises(ValueError, match="at least one joint"):
        JointTarget(())


# ---------------------------------------------------------------------------
# 5. JSON dict round-trip preserves equality
# ---------------------------------------------------------------------------


def test_to_dict_from_dict_round_trip():
    prog = _make_program()
    encoded = to_dict(prog)
    # Encoded should be plain JSON-friendly primitives (dicts, lists, scalars).
    s = json.dumps(encoded)
    reloaded_raw = json.loads(s)
    decoded = from_dict(reloaded_raw, Program)
    assert isinstance(decoded, Program)
    assert decoded == prog


def test_to_dict_includes_type_discriminators():
    """Every dataclass in the tree must carry a __type__ tag."""
    prog = _make_program()
    encoded = to_dict(prog)
    assert encoded["__type__"] == "Program"
    main_proc = encoded["procedures"][0]
    assert main_proc["__type__"] == "Procedure"
    # The MOVE_ABS_J move's target is a JointTarget; the MOVE_L's is a PoseTarget.
    move_abs_j = main_proc["body"][1]
    move_l = main_proc["body"][2]
    assert move_abs_j["target"]["__type__"] == "JointTarget"
    assert move_l["target"]["__type__"] == "PoseTarget"


# ---------------------------------------------------------------------------
# 6. JSON file dump/load round-trip
# ---------------------------------------------------------------------------


def test_dump_load_file_round_trip():
    prog = _make_program()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "prog.json")
        dump(prog, path)
        assert os.path.isfile(path)
        loaded = load(path)
        assert isinstance(loaded, Program)
        assert loaded == prog


# ---------------------------------------------------------------------------
# 7. Union discriminator works for both target types
# ---------------------------------------------------------------------------


def test_union_discriminator_for_move_target():
    """Move.target's PoseTarget vs JointTarget must round-trip distinctly."""
    tool = _make_tool()
    wobj = _make_wobj()
    speed = _make_speed()

    move_pose = Move(MoveKind.MOVE_L, _make_pose(), speed, ZoneData.fine(), tool, wobj)
    move_joint = Move(MoveKind.MOVE_ABS_J, _make_joint(7), speed, ZoneData.fine(), tool, wobj)

    encoded_pose = to_dict(move_pose)
    encoded_joint = to_dict(move_joint)
    assert encoded_pose["target"]["__type__"] == "PoseTarget"
    assert encoded_joint["target"]["__type__"] == "JointTarget"

    # Round-trip via JSON.
    reloaded_pose = from_dict(json.loads(json.dumps(encoded_pose)))
    reloaded_joint = from_dict(json.loads(json.dumps(encoded_joint)))
    assert isinstance(reloaded_pose.target, PoseTarget)
    assert isinstance(reloaded_joint.target, JointTarget)
    assert reloaded_pose == move_pose
    assert reloaded_joint == move_joint
    # Joints with different DOF should also be preserved exactly.
    assert len(reloaded_joint.target.q_rad) == 7


def test_circ_via_round_trips_when_present_and_absent():
    tool = _make_tool()
    wobj = _make_wobj()
    speed = _make_speed()
    pose_end = PoseTarget((0.5, 0.1, 0.4), _identity_quat())
    via = PoseTarget((0.45, 0.1, 0.4), _identity_quat())

    move_c = Move(
        MoveKind.MOVE_C, pose_end, speed, ZoneData(ZoneKind.RADIUS, 5.0), tool, wobj, circ_via=via
    )
    move_l = Move(MoveKind.MOVE_L, pose_end, speed, ZoneData.fine(), tool, wobj)

    rl_c = from_dict(to_dict(move_c))
    rl_l = from_dict(to_dict(move_l))
    assert rl_c == move_c
    assert rl_c.circ_via == via
    assert rl_l == move_l
    assert rl_l.circ_via is None


# ---------------------------------------------------------------------------
# 8. Spec-given example works verbatim
# ---------------------------------------------------------------------------


def test_spec_example_program_builds_and_round_trips():
    """The README-style example from the spec must execute exactly."""
    tool0 = ToolData("tool0", 0.0, (0, 0, 0), (1, 0, 0, 0))
    wobj0 = WObjData("wobj0", (0, 0, 0), (1, 0, 0, 0))
    v100 = SpeedData(100.0)
    z10 = ZoneData(ZoneData.RADIUS, 10.0)

    home = JointTarget((0.0,) * 6)
    p1 = PoseTarget((0.5, 0.1, 0.4), (0, 0, 1, 0))

    prog = Program(
        name="hello",
        modules_metadata={"author": "demo"},
        tools=[tool0],
        wobjs=[wobj0],
        procedures=[
            Procedure(
                "main",
                [],
                [
                    Move(MoveKind.MOVE_ABS_J, home, v100, ZoneData.fine(), tool0, wobj0),
                    Move(MoveKind.MOVE_L, p1, v100, z10, tool0, wobj0),
                ],
            ),
        ],
    )
    assert prog.name == "hello"
    assert len(prog.procedures[0].body) == 2
    # Round-trip preserves equality.
    reloaded = from_dict(to_dict(prog))
    assert reloaded == prog


def test_io_and_wait_validation():
    # IOOp empty signal: rejected.
    with pytest.raises(ValueError, match="signal must not be empty"):
        IOOp("", 1, IOKind.SET)

    # Wait with neither: rejected.
    with pytest.raises(ValueError, match="exactly one"):
        Wait()
    # Wait with both: rejected.
    with pytest.raises(ValueError, match="exactly one"):
        Wait(seconds=1.0, signal="di_x")
    # Wait with negative seconds: rejected.
    with pytest.raises(ValueError, match=">= 0"):
        Wait(seconds=-0.1)
    # Valid forms.
    assert Wait(seconds=0.5).seconds == 0.5
    assert Wait(signal="di_x").signal == "di_x"
