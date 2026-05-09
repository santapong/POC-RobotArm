"""Tests for LimitViolation, LimitsExceeded, validate_move, and the LLM tools JSON shape."""

from __future__ import annotations

import json

import numpy as np
import pytest

from src.motion.ir import JointTarget, MoveKind, PoseTarget
from src.motion.limits import (
    LimitsExceeded,
    LimitViolation,
    assert_no_violations,
    validate_move,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ID_QUAT = (1.0, 0.0, 0.0, 0.0)


def _joint_target(q=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)) -> JointTarget:
    return JointTarget(q_rad=q)


def _pose_target(xyz=(0.5, 0.0, 0.4)) -> PoseTarget:
    return PoseTarget(xyz_m=xyz, quat_wxyz=_ID_QUAT)


def _qlim_6(lo=-3.14, hi=3.14):
    return [(lo, hi)] * 6


def _violation(**kw) -> LimitViolation:
    defaults = {"code": "JOINT_POSITION", "message": "test violation"}
    defaults.update(kw)
    return LimitViolation(**defaults)


# ---------------------------------------------------------------------------
# validate_move — happy path
# ---------------------------------------------------------------------------


def test_validate_move_clean_returns_empty():
    target = _joint_target()
    violations = validate_move(
        move_kind=MoveKind.MOVE_ABS_J.value,
        target=target,
        robot_qlim=_qlim_6(-3.14, 3.14),
    )
    assert violations == []


# ---------------------------------------------------------------------------
# validate_move — joint position checks
# ---------------------------------------------------------------------------


def test_validate_move_joint_position_below_min():
    q = (-4.0,) + (0.0,) * 5  # q[0] below -3.14
    target = _joint_target(q)
    violations = validate_move(
        move_kind=MoveKind.MOVE_ABS_J.value,
        target=target,
        robot_qlim=_qlim_6(-3.14, 3.14),
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.code == "JOINT_POSITION"
    assert v.joint_index == 0
    assert v.value == pytest.approx(-4.0)
    assert v.limit == pytest.approx(-3.14)  # lower limit


def test_validate_move_joint_position_above_max():
    q = (0.0,) * 5 + (4.0,)  # q[5] above 3.14
    target = _joint_target(q)
    violations = validate_move(
        move_kind=MoveKind.MOVE_ABS_J.value,
        target=target,
        robot_qlim=_qlim_6(-3.14, 3.14),
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.code == "JOINT_POSITION"
    assert v.joint_index == 5
    assert v.value == pytest.approx(4.0)
    assert v.limit == pytest.approx(3.14)  # upper limit


def test_validate_move_joint_count_mismatch():
    target = _joint_target((0.0,) * 5)  # 5 joints
    qlim = _qlim_6()  # 6 joints
    violations = validate_move(
        move_kind=MoveKind.MOVE_ABS_J.value,
        target=target,
        robot_qlim=qlim,
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.code == "JOINT_POSITION"
    assert v.joint_index is None


# ---------------------------------------------------------------------------
# validate_move — singularity
# ---------------------------------------------------------------------------


def test_validate_move_singularity_with_jacobian_fn():
    """Near-singular Jacobian → one SINGULARITY violation with yoshikawa as requested."""
    J_near_singular = np.eye(6) * 1e-3  # yoshikawa = (1e-3)^6 << 0.01

    def jac_fn(q):
        return J_near_singular

    target = _joint_target()
    violations = validate_move(
        move_kind=MoveKind.MOVE_ABS_J.value,
        target=target,
        robot_qlim=None,
        jacobian_fn=jac_fn,
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.code == "SINGULARITY"
    assert v.joint_index is None
    # requested value == yoshikawa index
    assert v.value is not None
    assert v.value < 0.01
    # allowed == the threshold
    assert v.limit == pytest.approx(0.01)


def test_validate_move_no_singularity_when_jacobian_fn_none():
    """Without a jacobian_fn, singularity is never checked."""
    target = _joint_target()
    violations = validate_move(
        move_kind=MoveKind.MOVE_ABS_J.value,
        target=target,
        robot_qlim=None,
        jacobian_fn=None,
    )
    assert violations == []


def test_validate_move_move_l_skips_joint_position():
    """MOVE_L with a PoseTarget never emits JOINT_POSITION (PR-A)."""
    target = _pose_target()
    violations = validate_move(
        move_kind=MoveKind.MOVE_L.value,
        target=target,
        robot_qlim=_qlim_6(-0.001, 0.001),  # very tight limits — but ignored for MOVE_L
    )
    joint_pos_violations = [v for v in violations if v.code == "JOINT_POSITION"]
    assert joint_pos_violations == []


# ---------------------------------------------------------------------------
# assert_no_violations
# ---------------------------------------------------------------------------


def test_assert_no_violations_raises_on_nonempty():
    v = _violation(message="too far")
    with pytest.raises(LimitsExceeded) as exc_info:
        assert_no_violations([v])
    exc = exc_info.value
    assert exc.violations == [v]


def test_assert_no_violations_silent_on_empty():
    result = assert_no_violations([])
    assert result is None


# ---------------------------------------------------------------------------
# LimitViolation validation
# ---------------------------------------------------------------------------


def test_limit_violation_invalid_code_rejected():
    with pytest.raises(ValueError):
        LimitViolation(code="BAD", message="x")


def test_limit_violation_invalid_axis_rejected():
    with pytest.raises(ValueError):
        LimitViolation(code="JOINT_POSITION", message="x", axis="diagonal")


def test_limit_violation_to_dict_shape():
    v = LimitViolation(
        code="JOINT_POSITION",
        message="out of range",
        joint_index=2,
        axis=None,
        value=3.5,
        limit=3.14,
    )
    d = v.to_dict()
    expected_keys = {"code", "message", "joint_index", "axis", "value", "limit"}
    assert set(d.keys()) == expected_keys
    # Optional fields that are None must still be present (not stripped).
    # axis is None here:
    assert "axis" in d
    assert d["axis"] is None


# ---------------------------------------------------------------------------
# LimitsExceeded
# ---------------------------------------------------------------------------


def test_limits_exceeded_str_includes_messages():
    v1 = _violation(message="joint 0 out of bounds")
    v2 = _violation(message="singularity detected", code="SINGULARITY")
    exc = LimitsExceeded([v1, v2])
    s = str(exc)
    assert "joint 0 out of bounds" in s
    assert "singularity detected" in s


# ---------------------------------------------------------------------------
# LLM tools — LIMIT_VIOLATION JSON shape
# ---------------------------------------------------------------------------


def test_llm_tools_limit_violation_json_shape():
    """Construct the JSON response that tools.py builds for a LimitsExceeded.

    We call _sim_err directly (it is importable) and verify the shape matches
    what the execute_tool except-branch emits, without monkeypatching the
    dispatcher.
    """
    from src.llm.tools import _sim_err  # type: ignore[attr-defined]

    v1 = LimitViolation(
        code="JOINT_POSITION",
        message="joint 0 too high",
        joint_index=0,
        value=4.0,
        limit=3.14,
    )
    v2 = LimitViolation(
        code="SINGULARITY",
        message="near singular",
        joint_index=None,
        value=1e-7,
        limit=0.01,
    )
    exc = LimitsExceeded([v1, v2])

    raw = _sim_err(
        "LIMIT_VIOLATION",
        str(exc),
        violations=[v.to_dict() for v in exc.violations],
    )
    payload = json.loads(raw)

    assert payload["ok"] is False
    assert payload["error_code"] == "LIMIT_VIOLATION"
    assert "violations" in payload
    assert len(payload["violations"]) == 2
    # First violation must match v1.to_dict() exactly.
    assert payload["violations"][0] == v1.to_dict()
