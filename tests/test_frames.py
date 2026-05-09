"""Tests for TCP/RTCP frame helpers in src.motion.frames."""

from __future__ import annotations

import pytest

pytest.importorskip("spatialmath")
pytest.importorskip("numpy")


from src.motion.frames import (  # noqa: E402
    FrameMode,
    derive_frame_mode,
    forward_resolve,
    resolve_frame_to_root,
    resolve_pose_to_base,
)
from src.motion.ir import PoseTarget, ToolData, WObjData  # noqa: E402
from src.station.scene import Frame, Station  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ID_QUAT = (1.0, 0.0, 0.0, 0.0)
_ZERO_XYZ = (0.0, 0.0, 0.0)


def _tool(tcp_xyz=(0.0, 0.0, 0.0), robhold: bool = True) -> ToolData:
    return ToolData(
        name="tool",
        mass_kg=0.5,
        tcp_xyz_m=tcp_xyz,
        tcp_quat_wxyz=_ID_QUAT,
        robhold=robhold,
    )


def _wobj(user_xyz=(0.0, 0.0, 0.0), robhold: bool = False) -> WObjData:
    return WObjData(
        name="wobj",
        base_xyz_m=_ZERO_XYZ,
        base_quat_wxyz=_ID_QUAT,
        user_xyz_m=user_xyz,
        user_quat_wxyz=_ID_QUAT,
        robhold=robhold,
    )


def _pose(xyz=(0.0, 0.0, 0.0)) -> PoseTarget:
    return PoseTarget(xyz_m=xyz, quat_wxyz=_ID_QUAT)


def _assert_pose_close(a: PoseTarget, b: PoseTarget, tol: float = 1e-9) -> None:
    for va, vb in zip(a.xyz_m, b.xyz_m):
        assert abs(va - vb) <= tol, f"xyz mismatch: {a.xyz_m} vs {b.xyz_m}"
    # Quaternions may differ by sign (w >= 0 canonical).
    for qa, qb in zip(a.quat_wxyz, b.quat_wxyz):
        assert abs(qa - qb) <= tol, f"quat mismatch: {a.quat_wxyz} vs {b.quat_wxyz}"


# ---------------------------------------------------------------------------
# derive_frame_mode
# ---------------------------------------------------------------------------


def test_frame_mode_tcp_combo():
    tool = _tool(robhold=True)
    wobj = _wobj(robhold=False)
    assert derive_frame_mode(tool, wobj) == FrameMode.TCP


def test_frame_mode_rtcp_combo():
    tool = _tool(robhold=False)
    wobj = _wobj(robhold=True)
    assert derive_frame_mode(tool, wobj) == FrameMode.RTCP


def test_frame_mode_invalid_both_true():
    tool = _tool(robhold=True)
    wobj = _wobj(robhold=True)
    with pytest.raises(ValueError):
        derive_frame_mode(tool, wobj)


def test_frame_mode_invalid_both_false():
    tool = _tool(robhold=False)
    wobj = _wobj(robhold=False)
    with pytest.raises(ValueError):
        derive_frame_mode(tool, wobj)


# ---------------------------------------------------------------------------
# resolve_pose_to_base — TCP mode
# ---------------------------------------------------------------------------


def test_resolve_pose_to_base_tcp_identity_no_op():
    """All identity frames + non-trivial xyz → flange xyz == pose xyz."""
    pose = _pose((0.5, 0.0, 0.0))
    tool = _tool()      # tcp offset zero, robhold=True
    wobj = _wobj()      # user offset zero, robhold=False
    result = resolve_pose_to_base(pose, wobj, tool)
    assert abs(result.xyz_m[0] - 0.5) <= 1e-9
    assert abs(result.xyz_m[1] - 0.0) <= 1e-9
    assert abs(result.xyz_m[2] - 0.0) <= 1e-9
    # Identity quaternion (w=1, x=y=z=0)
    assert abs(result.quat_wxyz[0] - 1.0) <= 1e-9
    assert abs(result.quat_wxyz[1]) <= 1e-9
    assert abs(result.quat_wxyz[2]) <= 1e-9
    assert abs(result.quat_wxyz[3]) <= 1e-9


def test_resolve_pose_to_base_tcp_translation():
    """wobj user offset +0.1 X, tool tcp offset +0.1 Z, pose at origin.

    TCP formula: T_user * T_obj * T_pose * T_tool^{-1}
    All rotations identity:
      T_user.t = (0.1, 0, 0)
      T_obj.t  = (0,   0, 0)
      T_pose.t = (0,   0, 0)
      T_tool.t = (0,   0, 0.1)

    flange = T_user * T_obj * T_pose * T_tool^{-1}
    T_tool^{-1}.t = (0, 0, -0.1) (pure translation with identity R)
    compose: (0.1, 0, 0) + (0, 0, 0) + (0, 0, 0) + (0, 0, -0.1) = (0.1, 0, -0.1)
    """
    tool = _tool(tcp_xyz=(0.0, 0.0, 0.1), robhold=True)
    wobj = _wobj(user_xyz=(0.1, 0.0, 0.0), robhold=False)
    pose = _pose(_ZERO_XYZ)
    result = resolve_pose_to_base(pose, wobj, tool)
    assert abs(result.xyz_m[0] - 0.1) <= 1e-9, result.xyz_m
    assert abs(result.xyz_m[1] - 0.0) <= 1e-9, result.xyz_m
    assert abs(result.xyz_m[2] - (-0.1)) <= 1e-9, result.xyz_m


def test_resolve_pose_to_base_rtcp_translation():
    """RTCP: tool.robhold=False, wobj.robhold=True.

    Formula: T_user^{-1} * T_obj^{-1} * T_tool * T_pose
    user_xyz = (0.2, 0, 0), tool_xyz = (0.5, 0, 0), pose_xyz = (0.1, 0, 0)
    All rotations identity:
      T_user^{-1}.t = (-0.2, 0, 0)
      T_obj^{-1}.t  = (0,    0, 0)   (base_xyz is zero)
      T_tool.t      = (0.5,  0, 0)
      T_pose.t      = (0.1,  0, 0)
    Compose (all R=I): -0.2 + 0 + 0.5 + 0.1 = 0.4
    """
    tool = _tool(tcp_xyz=(0.5, 0.0, 0.0), robhold=False)
    wobj = _wobj(user_xyz=(0.2, 0.0, 0.0), robhold=True)
    pose = _pose((0.1, 0.0, 0.0))
    result = resolve_pose_to_base(pose, wobj, tool, mode=FrameMode.RTCP)
    assert abs(result.xyz_m[0] - 0.4) <= 1e-9, result.xyz_m
    assert abs(result.xyz_m[1] - 0.0) <= 1e-9, result.xyz_m
    assert abs(result.xyz_m[2] - 0.0) <= 1e-9, result.xyz_m


# ---------------------------------------------------------------------------
# forward_resolve round-trips
# ---------------------------------------------------------------------------


def test_resolve_pose_round_trip_tcp():
    """forward_resolve(resolve_pose_to_base(pose)) == pose in TCP mode."""
    tool = _tool(tcp_xyz=(0.05, 0.0, 0.1), robhold=True)
    wobj = _wobj(user_xyz=(0.2, 0.1, 0.0), robhold=False)
    pose = _pose((0.3, -0.1, 0.5))
    flange = resolve_pose_to_base(pose, wobj, tool)
    recovered = forward_resolve(flange, wobj, tool)
    _assert_pose_close(recovered, pose)


def test_resolve_pose_round_trip_rtcp():
    """forward_resolve(resolve_pose_to_base(pose)) == pose in RTCP mode."""
    tool = _tool(tcp_xyz=(0.1, 0.0, 0.2), robhold=False)
    wobj = _wobj(user_xyz=(0.3, 0.0, 0.1), robhold=True)
    pose = _pose((0.05, 0.15, -0.1))
    flange = resolve_pose_to_base(pose, wobj, tool, mode=FrameMode.RTCP)
    recovered = forward_resolve(flange, wobj, tool, mode=FrameMode.RTCP)
    _assert_pose_close(recovered, pose)


def test_resolve_pose_to_base_explicit_mode_override():
    """Passing mode=FrameMode.TCP explicitly matches auto-derive for TCP-shaped robhold flags."""
    tool = _tool(robhold=True)
    wobj = _wobj(robhold=False)
    pose = _pose((0.4, 0.1, 0.2))
    auto_result = resolve_pose_to_base(pose, wobj, tool)
    explicit_result = resolve_pose_to_base(pose, wobj, tool, mode=FrameMode.TCP)
    _assert_pose_close(auto_result, explicit_result)


# ---------------------------------------------------------------------------
# resolve_frame_to_root
# ---------------------------------------------------------------------------


def _make_frame(name: str, xyz=(0.0, 0.0, 0.0), parent=None) -> Frame:
    return Frame(name=name, xyz_m=xyz, quat_wxyz=_ID_QUAT, parent=parent)


def test_resolve_frame_to_root_chain():
    """Three frames A→B→C: world pose of C = A.xyz + B.xyz + C.xyz (all rot identity)."""
    fA = _make_frame("A", xyz=(1.0, 0.0, 0.0), parent=None)
    fB = _make_frame("B", xyz=(0.0, 2.0, 0.0), parent="A")
    fC = _make_frame("C", xyz=(0.0, 0.0, 3.0), parent="B")
    scene = Station(name="s", frames=(fA, fB, fC))
    xyz, quat = resolve_frame_to_root(scene, "C")
    assert abs(xyz[0] - 1.0) <= 1e-9
    assert abs(xyz[1] - 2.0) <= 1e-9
    assert abs(xyz[2] - 3.0) <= 1e-9
    # Identity rotation should survive.
    assert abs(quat[0] - 1.0) <= 1e-9


def test_resolve_frame_to_root_root_only():
    """A frame with parent=None returns its own xyz and quat."""
    fA = _make_frame("A", xyz=(0.5, 0.25, 0.1), parent=None)
    scene = Station(name="s", frames=(fA,))
    xyz, quat = resolve_frame_to_root(scene, "A")
    assert abs(xyz[0] - 0.5) <= 1e-9
    assert abs(xyz[1] - 0.25) <= 1e-9
    assert abs(xyz[2] - 0.1) <= 1e-9


def test_resolve_frame_to_root_unknown_name():
    fA = _make_frame("A")
    scene = Station(name="s", frames=(fA,))
    with pytest.raises(ValueError, match="unknown frame"):
        resolve_frame_to_root(scene, "NONEXISTENT")


def test_resolve_frame_to_root_unknown_parent():
    # Station.__post_init__ validates parents, so we must bypass it.
    # We build a duck-typed object that exposes `frames` as a tuple
    # but skips Station's referential-integrity check.
    # Choice: use a SimpleNamespace to duck-type a Station.
    import types

    bad_frame = Frame(name="B", xyz_m=(0.0, 0.0, 0.0), quat_wxyz=_ID_QUAT, parent="MISSING")
    fake_scene = types.SimpleNamespace(frames=(bad_frame,))
    with pytest.raises(ValueError, match="unknown parent"):
        resolve_frame_to_root(fake_scene, "B")


def test_resolve_frame_to_root_cycle():
    # Station.__post_init__ does NOT detect cycles (it only checks each frame's
    # parent exists), so we can construct a cyclic scene via duck-typing and
    # expect resolve_frame_to_root to catch it.
    import types

    fA = Frame(name="A", xyz_m=_ZERO_XYZ, quat_wxyz=_ID_QUAT, parent="B")
    fB = Frame(name="B", xyz_m=_ZERO_XYZ, quat_wxyz=_ID_QUAT, parent="A")
    fake_scene = types.SimpleNamespace(frames=(fA, fB))
    with pytest.raises(ValueError, match="cycle"):
        resolve_frame_to_root(fake_scene, "A")


def test_optimizer_imports_after_extraction():
    """Importing optimize_joints from toolpath.optimizer must succeed."""
    from src.toolpath.optimizer import optimize_joints  # noqa: F401

    assert callable(optimize_joints)
