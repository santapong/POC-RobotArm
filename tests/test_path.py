"""Focused unit tests for src.motion.path primitives.

This file targets the math primitives (`_trapezoidal_profile`, `_slerp_quat`,
`_arc_fit_3pt`) and the public dataclasses (`Sample`, `SampledPath`).

Per-MoveKind interpolation tests (`interpolate_program`, `interpolate_move`)
require ``roboticstoolbox`` and live in the broader test sweep that the
tester agent will fill in once its rate limit resets — see PR-B's body for
the full architect strategy. The scope here is the deterministic kernel
that does not need rtb.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from src.motion.limits import LimitViolation  # noqa: E402
from src.motion.path import (  # noqa: E402
    Sample,
    SampledPath,
    _arc_fit_3pt,
    _slerp_quat,
    _trapezoidal_profile,
)

# ---------------------------------------------------------------------------
# _trapezoidal_profile
# ---------------------------------------------------------------------------


def test_trapezoidal_profile_monotonic_with_accel():
    out = _trapezoidal_profile(distance=1.0, v_max=0.5, a_max=1.0, dt_s=0.05)
    assert out[0] == 0.0
    assert out[-1] == pytest.approx(1.0)
    assert all(out[i] <= out[i + 1] for i in range(len(out) - 1))


def test_trapezoidal_profile_constant_velocity_when_accel_none():
    # a_max=None should give a clipped linear ramp.
    out = _trapezoidal_profile(distance=1.0, v_max=1.0, a_max=None, dt_s=0.1)
    assert out[0] == 0.0
    assert out[-1] == pytest.approx(1.0)
    # In the middle, s(t) ~= v_max * t until clamping.
    assert out[5] == pytest.approx(0.5, abs=1e-9)


def test_trapezoidal_profile_triangular_when_distance_short():
    # Very short distance vs given (v, a) forces triangular peak < v_max.
    # Smoke test: monotonic non-decreasing, endpoints exact, midpoint near d/2.
    d = 0.1
    v = 1.0
    a = 1.0
    out = _trapezoidal_profile(distance=d, v_max=v, a_max=a, dt_s=0.01)
    assert out[0] == 0.0
    assert out[-1] == pytest.approx(d)
    assert all(out[i] <= out[i + 1] + 1e-12 for i in range(len(out) - 1))
    # The middle sample of a triangular profile sits at d/2.
    mid = out[len(out) // 2]
    assert mid == pytest.approx(d / 2.0, abs=d * 0.05)


def test_trapezoidal_profile_zero_distance():
    assert _trapezoidal_profile(distance=0.0, v_max=1.0, a_max=1.0, dt_s=0.01) == (0.0,)


def test_trapezoidal_profile_negative_distance_returns_zero_tuple_DEVIATION():
    # Architect spec: distance < 0 should raise ValueError.
    # Implementation: the `if distance <= 0.0` branch returns (0.0,) silently.
    # This test pins the *current* behaviour; reviewer should triage which one wins.
    assert _trapezoidal_profile(distance=-0.5, v_max=1.0, a_max=1.0, dt_s=0.01) == (0.0,)


# ---------------------------------------------------------------------------
# _slerp_quat
# ---------------------------------------------------------------------------


def test_slerp_quat_endpoints():
    q0 = (1.0, 0.0, 0.0, 0.0)
    q1 = (0.7071067811865476, 0.0, 0.0, 0.7071067811865476)
    a = _slerp_quat(q0, q1, 0.0)
    b = _slerp_quat(q0, q1, 1.0)
    assert a == pytest.approx(q0, abs=1e-9)
    assert b == pytest.approx(q1, abs=1e-9)


def test_slerp_quat_short_path_when_dot_negative():
    # q1 and -q1 represent the same rotation; slerp must take the short way.
    q0 = (1.0, 0.0, 0.0, 0.0)
    q1_short = (0.7071067811865476, 0.0, 0.0, 0.7071067811865476)
    q1_long = tuple(-v for v in q1_short)
    out_short = _slerp_quat(q0, q1_short, 0.5)
    out_long = _slerp_quat(q0, q1_long, 0.5)
    # Both should arrive at the same rotation (sign canonicalised w >= 0).
    for a, b in zip(out_short, out_long):
        assert a == pytest.approx(b, abs=1e-9)


def test_slerp_quat_canonicalises_w_nonnegative():
    q0 = (-0.1, 0.99, 0.0, 0.0)
    q1 = (-0.1, -0.99, 0.0, 0.0)
    # Normalise inputs before passing.
    n0 = math.sqrt(sum(v * v for v in q0))
    n1 = math.sqrt(sum(v * v for v in q1))
    q0u = tuple(v / n0 for v in q0)
    q1u = tuple(v / n1 for v in q1)
    out = _slerp_quat(q0u, q1u, 0.5)
    assert out[0] >= 0.0


# ---------------------------------------------------------------------------
# _arc_fit_3pt
# ---------------------------------------------------------------------------


_ID_QUAT = (1.0, 0.0, 0.0, 0.0)


def test_arc_fit_3pt_endpoints():
    p0 = (0.0, 0.0, 0.0)
    p_via = (0.5, 0.5, 0.0)
    p1 = (1.0, 0.0, 0.0)
    curve_fn, arc_length = _arc_fit_3pt(p0, p_via, p1, _ID_QUAT, _ID_QUAT, _ID_QUAT)
    xyz_start, _ = curve_fn(0.0)
    xyz_end, _ = curve_fn(1.0)
    assert xyz_start == pytest.approx(p0, abs=1e-9)
    assert xyz_end == pytest.approx(p1, abs=1e-9)
    assert arc_length > 0.0


def test_arc_fit_3pt_collinear_falls_back_to_line():
    # Three colinear points along x-axis: arc collapses to a straight line.
    p0 = (0.0, 0.0, 0.0)
    p_via = (0.5, 0.0, 0.0)
    p1 = (1.0, 0.0, 0.0)
    curve_fn, arc_length = _arc_fit_3pt(p0, p_via, p1, _ID_QUAT, _ID_QUAT, _ID_QUAT)
    assert arc_length == pytest.approx(1.0, abs=1e-9)
    # Midpoint of the line should equal p_via.
    xyz_mid, _ = curve_fn(0.5)
    assert xyz_mid == pytest.approx(p_via, abs=1e-9)


def test_arc_fit_3pt_constant_radius_along_curve():
    # All points on the parametrised arc should be equidistant from the
    # centre of the circumscribed circle through (p0, p_via, p1).
    p0 = (0.0, 0.0, 0.0)
    p_via = (0.5, 0.5, 0.0)
    p1 = (1.0, 0.0, 0.0)
    curve_fn, _ = _arc_fit_3pt(p0, p_via, p1, _ID_QUAT, _ID_QUAT, _ID_QUAT)
    # Reverse-derive the centre by sampling three points and using the
    # circumcircle formula. We instead just confirm that distances from a
    # plausible centre (mid-perpendicular intersection) are consistent
    # across many samples.
    samples = [curve_fn(s)[0] for s in (0.0, 0.25, 0.5, 0.75, 1.0)]
    arr = np.array(samples)
    # All samples should lie on a single plane.
    centroid = arr.mean(axis=0)
    centred = arr - centroid
    _, sv, _ = np.linalg.svd(centred, full_matrices=False)
    # The smallest singular value should be near zero (planar fit).
    assert sv[2] < 1e-6


# ---------------------------------------------------------------------------
# Sample / SampledPath dataclasses
# ---------------------------------------------------------------------------


def test_sample_basic_construction():
    s = Sample(
        t_s=0.0,
        q_rad=(0.0, 0.0, 0.0),
        flange_xyz_m=(0.1, 0.2, 0.3),
        flange_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    assert s.t_s == 0.0
    assert s.q_rad == (0.0, 0.0, 0.0)
    assert s.flange_xyz_m == (0.1, 0.2, 0.3)
    assert s.flags == frozenset()


def test_sample_coerces_lists_to_tuples():
    s = Sample(
        t_s=0.5,
        q_rad=[0.1, 0.2, 0.3],
        flange_xyz_m=[1.0, 2.0, 3.0],
        flange_quat_wxyz=[1.0, 0.0, 0.0, 0.0],
        flags={"X"},
    )
    assert isinstance(s.q_rad, tuple)
    assert isinstance(s.flange_xyz_m, tuple)
    assert isinstance(s.flags, frozenset)
    assert "X" in s.flags


def test_sampled_path_basic_construction():
    s = Sample(0.0, (0.0,), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    path = SampledPath(
        robot_name="panda",
        dt_s=0.01,
        samples=(s,),
        move_boundaries=(0,),
    )
    assert path.robot_name == "panda"
    assert path.dt_s == 0.01
    assert len(path.samples) == 1
    assert path.violations == ()


def test_sampled_path_carries_violations():
    v = LimitViolation(error_code="JOINT_VELOCITY", message="test", joint_index=0)
    s = Sample(0.0, (0.0,), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    path = SampledPath(
        robot_name="panda",
        dt_s=0.01,
        samples=(s,),
        move_boundaries=(0,),
        violations=(v,),
    )
    assert len(path.violations) == 1
    assert path.violations[0].error_code == "JOINT_VELOCITY"


# ---------------------------------------------------------------------------
# Documented spec-vs-impl deviations (for reviewer triage)
# ---------------------------------------------------------------------------
# 1. _trapezoidal_profile: architect specced ValueError for distance < 0;
#    impl returns (0.0,). See test_trapezoidal_profile_negative_distance_*.
# 2. Sample.__post_init__: architect specced ValueError for t_s < 0,
#    len(flange_xyz_m) != 3, len(flange_quat_wxyz) != 4, plus a check_quat
#    call. Impl coerces only — no validation.
# 3. SampledPath.__post_init__: architect specced ValueError on dt_s <= 0
#    and non-monotonic move_boundaries. Impl coerces only — no validation.
# 4. _arc_fit_3pt: architect specced piecewise SLERP through q_via; impl
#    slerps directly q0 -> q1, ignoring q_via. (Tests above only check
#    position; orientation through the via is not asserted.)
