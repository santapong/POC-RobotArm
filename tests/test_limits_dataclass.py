"""Tests for JointLimits, RobotURDFSpec.limits, and SpeedData accel fields."""

from __future__ import annotations

import json

import pytest

from src.motion.ir import SpeedData, _decode, _encode
from src.robots.catalog import CATALOG, RobotURDFSpec
from src.robots.limits import JointLimits

# ---------------------------------------------------------------------------
# JointLimits validation
# ---------------------------------------------------------------------------


def test_jointlimits_rejects_empty_qd():
    with pytest.raises(ValueError, match="must not be empty"):
        JointLimits(())


def test_jointlimits_rejects_nonpositive_qd():
    with pytest.raises(ValueError, match=r"qd_max_rad_s\[1\]"):
        JointLimits((1.0, 0.0))


def test_jointlimits_rejects_qdd_length_mismatch():
    with pytest.raises(ValueError, match="length must match"):
        JointLimits(qd_max_rad_s=(1.0, 2.0), qdd_max_rad_s2=(5.0,))


def test_jointlimits_rejects_nonpositive_qdd():
    with pytest.raises(ValueError, match=r"qdd_max_rad_s2\[1\]"):
        JointLimits(qd_max_rad_s=(1.0, 2.0), qdd_max_rad_s2=(5.0, -1.0))


def test_jointlimits_qdd_optional():
    lim = JointLimits(qd_max_rad_s=(1.0, 2.0), qdd_max_rad_s2=None)
    assert lim.qdd_max_rad_s2 is None
    # Frozen dataclass must be hashable.
    h = hash(lim)
    assert isinstance(h, int)


# ---------------------------------------------------------------------------
# RobotURDFSpec.limits
# ---------------------------------------------------------------------------


def test_robot_urdfspec_default_limits_none():
    spec = RobotURDFSpec("x", "x.urdf")
    assert spec.limits is None


def test_robot_urdfspec_accepts_limits_keyword():
    lim = JointLimits((1.0,))
    spec = RobotURDFSpec("r", "r.urdf", limits=lim)
    assert spec.limits == lim
    # Build a sibling and confirm equality round-trips.
    spec2 = RobotURDFSpec("r", "r.urdf", limits=JointLimits((1.0,)))
    assert spec.limits == spec2.limits


def test_catalog_real_robots_have_limits():
    # Architect's contract: panda, ur5, abb_irb1200 must have limits with len == dof.
    # iiwa is also in the catalog with limits; we assert all that exist.
    required = {"panda", "ur5", "abb_irb1200"}
    for robot_name in required:
        assert robot_name in CATALOG, f"{robot_name!r} missing from CATALOG"
        spec = CATALOG[robot_name]
        assert spec.limits is not None, f"{robot_name}.limits is None"
        assert len(spec.limits.qd_max_rad_s) == spec.dof, (
            f"{robot_name}: qd_max_rad_s length {len(spec.limits.qd_max_rad_s)} "
            f"!= dof {spec.dof}"
        )


# ---------------------------------------------------------------------------
# SpeedData accel round-trips via _encode / _decode (same path as to_dict/from_dict)
# ---------------------------------------------------------------------------


def _roundtrip_speed(sd: SpeedData) -> SpeedData:
    """Encode → JSON string → decode back to SpeedData."""
    encoded = _encode(sd)
    s = json.dumps(encoded)
    decoded = _decode(json.loads(s))
    assert isinstance(decoded, SpeedData)
    return decoded


def test_speeddata_accel_optional_round_trip():
    sd = SpeedData(100.0)
    assert sd.a_tcp_mm_s2 is None
    assert sd.a_ori_deg_s2 is None
    rt = _roundtrip_speed(sd)
    assert rt == sd
    assert rt.a_tcp_mm_s2 is None
    assert rt.a_ori_deg_s2 is None


def test_speeddata_accel_explicit_round_trip():
    sd = SpeedData(100.0, a_tcp_mm_s2=2000.0, a_ori_deg_s2=4000.0)
    rt = _roundtrip_speed(sd)
    assert rt == sd
    assert rt.a_tcp_mm_s2 == 2000.0
    assert rt.a_ori_deg_s2 == 4000.0


def test_speeddata_accel_legacy_json_loads():
    # Pre-PR JSON: only the original fields present, no accel keys.
    # Mimic the __type__ discriminator that _encode emits.
    legacy_dict = {
        "__type__": "SpeedData",
        "v_tcp_mm_s": 100.0,
        "v_ori_deg_s": 500.0,
        "v_lin_ext_mm_s": 5000.0,
        "v_rot_ext_deg_s": 1000.0,
        # a_tcp_mm_s2 and a_ori_deg_s2 deliberately absent
    }
    decoded = _decode(legacy_dict)
    assert isinstance(decoded, SpeedData)
    assert decoded.a_tcp_mm_s2 is None
    assert decoded.a_ori_deg_s2 is None
    assert decoded.v_tcp_mm_s == 100.0


def test_speeddata_rejects_nonpositive_accel():
    with pytest.raises(ValueError, match="a_tcp_mm_s2"):
        SpeedData(100.0, a_tcp_mm_s2=0.0)
    with pytest.raises(ValueError, match="a_ori_deg_s2"):
        SpeedData(100.0, a_ori_deg_s2=-1.0)
