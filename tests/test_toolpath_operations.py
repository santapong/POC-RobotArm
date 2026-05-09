"""Tests for src.toolpath.operations — waypoint generators."""

from __future__ import annotations

import math

import pytest

# Skip the whole module if numpy/trimesh aren't available.
pytest.importorskip("numpy")
pytest.importorskip("trimesh")

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from src.motion.ir import PoseTarget  # noqa: E402
from src.toolpath.operations import (  # noqa: E402
    _quat_from_tool_z,
    _rotmat_to_quat_wxyz,
    curve_on_surface,
    polyline_follow,
    surface_raster,
)

# ---------------------------------------------------------------------------
# polyline_follow
# ---------------------------------------------------------------------------


def test_polyline_follow_count_and_xyz() -> None:
    pts = [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.1, 0.1, 0.0)]
    targets = polyline_follow(pts)
    assert len(targets) == 3
    for got, want in zip(targets, pts):
        assert isinstance(got, PoseTarget)
        assert got.xyz_m == tuple(float(c) for c in want)
        # Default approach is unit-norm.
        n = math.sqrt(sum(c * c for c in got.quat_wxyz))
        assert math.isclose(n, 1.0, abs_tol=1e-9)


def test_polyline_follow_custom_quat() -> None:
    pts = [(0.0, 0.0, 0.0)]
    quat = (1.0, 0.0, 0.0, 0.0)
    targets = polyline_follow(pts, approach_quat_wxyz=quat)
    assert targets[0].quat_wxyz == quat


def test_polyline_follow_invalid_point_length() -> None:
    with pytest.raises(ValueError):
        polyline_follow([(0.0, 0.0)])  # 2D — invalid


# ---------------------------------------------------------------------------
# Quaternion helpers
# ---------------------------------------------------------------------------


def test_rotmat_round_trip_identity() -> None:
    R = np.eye(3)
    q = _rotmat_to_quat_wxyz(R)
    assert q == pytest.approx((1.0, 0.0, 0.0, 0.0), abs=1e-9)


def test_quat_from_tool_z_aligns_z_axis() -> None:
    # Tool-Z points along world -Z (i.e. tool faces "down").
    q = _quat_from_tool_z((0.0, 0.0, -1.0))
    # Reconstruct rotation matrix and check column 2 == [0,0,-1].
    w, x, y, z = q
    R = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    assert R[:, 2] == pytest.approx([0.0, 0.0, -1.0], abs=1e-9)


# ---------------------------------------------------------------------------
# surface_raster
# ---------------------------------------------------------------------------


def _make_box(translate=(0.5, 0.0, 0.1), extents=(0.2, 0.1, 0.05)) -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=extents)
    box.apply_translation(list(translate))
    return box


def test_surface_raster_produces_waypoints_on_top_face() -> None:
    box = _make_box()
    # Slice the top face (z = 0.125) with planes parallel to YZ.
    waypoints = surface_raster(
        box,
        plane_normal=(0.0, 1.0, 0.0),
        plane_origin=(0.0, -0.05, 0.0),
        step_m=0.025,
    )
    assert len(waypoints) > 0
    # Every Z component should lie within the box's Z extent.
    z_min, z_max = box.bounds[0, 2], box.bounds[1, 2]
    for wp in waypoints:
        assert z_min - 1e-6 <= wp.xyz_m[2] <= z_max + 1e-6


def test_surface_raster_zero_step_raises() -> None:
    box = _make_box()
    with pytest.raises(ValueError):
        surface_raster(box, plane_normal=(0, 1, 0), plane_origin=(0, 0, 0), step_m=0.0)


def test_surface_raster_zero_normal_raises() -> None:
    box = _make_box()
    with pytest.raises(ValueError):
        surface_raster(box, plane_normal=(0, 0, 0), plane_origin=(0, 0, 0), step_m=0.01)


def test_surface_raster_normal_offset_moves_outward() -> None:
    box = _make_box()
    base = surface_raster(
        box, plane_normal=(0, 1, 0), plane_origin=(0, -0.05, 0), step_m=0.05,
    )
    offset = surface_raster(
        box,
        plane_normal=(0, 1, 0),
        plane_origin=(0, -0.05, 0),
        step_m=0.05,
        normal_offset_m=0.01,
    )
    assert len(base) == len(offset)
    # At least some waypoints must have moved by ~10 mm from base — the
    # exact direction depends on which face is "closest" at corners, but
    # the displacement magnitude must equal the offset for non-corner
    # samples (where the closest face is unambiguous).
    moved = 0
    for b, o in zip(base, offset):
        d = math.sqrt(sum((bo - bb) ** 2 for bo, bb in zip(o.xyz_m, b.xyz_m)))
        if d > 1e-6:
            moved += 1
            assert d == pytest.approx(0.01, abs=1e-6)
    assert moved > 0, "normal_offset_m had no effect on any waypoint"


# ---------------------------------------------------------------------------
# curve_on_surface
# ---------------------------------------------------------------------------


def test_curve_on_surface_alignment_on_top_face() -> None:
    box = _make_box()
    # Find the four top-face vertices (z near max).
    z_max = float(box.vertices[:, 2].max())
    top_idx = [i for i, v in enumerate(box.vertices) if abs(v[2] - z_max) < 1e-6]
    assert len(top_idx) >= 3
    # Make a closed loop along the top edges.
    chain = top_idx + [top_idx[0]]

    samples = 8
    targets = curve_on_surface(box, chain, samples=samples)
    assert len(targets) == samples
    # Every waypoint should sit on or near the top face (z ~ z_max) and have
    # a tool-Z aligned with -outward_normal. The outward normal for a top-face
    # point is +Z; tool-Z = -[0,0,1] = [0,0,-1].
    for tgt in targets:
        # Reconstruct rotation, check column 2 (tool-Z).
        w, x, y, z = tgt.quat_wxyz
        R = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        # Top-face normal points +Z, so tool-Z should point -Z.
        # Allow some tolerance because edge waypoints may be near a corner.
        assert R[2, 2] <= 0.1, f"tool-Z not pointing into surface: {R[:, 2]}"


def test_curve_on_surface_invalid_indices() -> None:
    box = _make_box()
    with pytest.raises(ValueError):
        curve_on_surface(box, [0, 9999], samples=4)


def test_curve_on_surface_too_few_samples() -> None:
    box = _make_box()
    with pytest.raises(ValueError):
        curve_on_surface(box, [0, 1, 2], samples=1)


def test_curve_on_surface_too_few_vertices() -> None:
    box = _make_box()
    with pytest.raises(ValueError):
        curve_on_surface(box, [0], samples=4)
