"""Tests for pixel_to_world: pinhole back-projection math.

Key scenario: camera at (0, 0, 1 m) looking straight down, identity
distortion, bbox centred at the image principal point → ground-plane hit
point ≈ (0, 0, 0).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")  # noqa: F841
_ = pytest.importorskip("numpy")  # noqa: F841 — guard before further imports

from src.vision.grasp import pixel_to_world  # noqa: E402
from src.vision.types import (  # noqa: E402
    CameraExtrinsics,
    CameraIntrinsics,
    Detection,
    GraspPose,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_W, _H = 640, 480
_FX = _FY = 640.0
_CX, _CY = 320.0, 240.0

# Camera looking straight down: camera +z axis points in world −z direction.
# R_cam_in_world s.t. R @ [0,0,1] = [0,0,-1]  =>  flip y and z:
# [[1,0,0],[0,-1,0],[0,0,-1]]
_R_DOWN = ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))
_T_UP = (0.0, 0.0, 1.0)  # camera 1 m above the origin


def _intrinsics(**overrides) -> CameraIntrinsics:
    kwargs: dict = dict(fx=_FX, fy=_FY, cx=_CX, cy=_CY, width=_W, height=_H,
                        dist_coeffs=(0.0,) * 5)
    kwargs.update(overrides)
    return CameraIntrinsics(**kwargs)


def _extrinsics(**overrides) -> CameraExtrinsics:
    kwargs: dict = dict(R_cam_in_world=_R_DOWN, t_cam_in_world=_T_UP)
    kwargs.update(overrides)
    return CameraExtrinsics(**kwargs)


def _det(x1: float, y1: float, x2: float, y2: float) -> Detection:
    return Detection(class_name="cube", confidence=0.9,
                     bbox_xyxy=(x1, y1, x2, y2))


# ---------------------------------------------------------------------------
# Core scenario: centred bbox hits (0, 0, 0)
# ---------------------------------------------------------------------------


class TestPixelToWorldCentreHitsOrigin:
    """Bbox centred at principal point → xyz ≈ (0, 0, 0)."""

    _TOL = 1e-6

    def _run(self, half: float = 20.0) -> GraspPose:
        det = _det(_CX - half, _CY - half, _CX + half, _CY + half)
        return pixel_to_world(det, _intrinsics(), _extrinsics())

    def test_x_near_zero(self) -> None:
        gp = self._run()
        assert abs(gp.xyz_m[0]) < self._TOL

    def test_y_near_zero(self) -> None:
        gp = self._run()
        assert abs(gp.xyz_m[1]) < self._TOL

    def test_z_near_plane(self) -> None:
        gp = self._run()
        assert abs(gp.xyz_m[2] - 0.0) < self._TOL

    def test_frame_matches_reference_frame(self) -> None:
        gp = self._run()
        assert gp.frame == "world"  # default reference_frame

    def test_return_type(self) -> None:
        assert isinstance(self._run(), GraspPose)


# ---------------------------------------------------------------------------
# Offset bbox
# ---------------------------------------------------------------------------


class TestPixelToWorldOffsetBbox:
    """Shift the centroid by Δu pixels → shift in world by Δx = Δu/fx * z."""

    _Z = 1.0  # camera height
    _TOL = 1e-4

    def test_positive_x_offset(self) -> None:
        delta_u = 64.0  # pixels to the right
        # expected world x = delta_u / fx * z (camera down, x unchanged)
        expected_x = delta_u / _FX * self._Z
        cx = _CX + delta_u
        det = _det(cx - 10, _CY - 10, cx + 10, _CY + 10)
        gp = pixel_to_world(det, _intrinsics(), _extrinsics())
        assert abs(gp.xyz_m[0] - expected_x) < self._TOL

    def test_positive_v_offset(self) -> None:
        """Positive v (downward in image) → negative world y (camera flips y)."""
        delta_v = 48.0
        # Camera y-axis in world = R @ [0,1,0] = [0,-1,0] (flipped).
        # So v increases downward in image → world y decreases.
        expected_y = -(delta_v / _FY * self._Z)
        cy = _CY + delta_v
        det = _det(_CX - 10, cy - 10, _CX + 10, cy + 10)
        gp = pixel_to_world(det, _intrinsics(), _extrinsics())
        assert abs(gp.xyz_m[1] - expected_y) < self._TOL


# ---------------------------------------------------------------------------
# Plane height
# ---------------------------------------------------------------------------


class TestPixelToWorldPlaneHeight:
    def test_plane_at_nonzero_z(self) -> None:
        """plane_z_m=0.5 → hit point z ≈ 0.5."""
        det = _det(_CX - 10, _CY - 10, _CX + 10, _CY + 10)
        gp = pixel_to_world(det, _intrinsics(), _extrinsics(), plane_z_m=0.5)
        assert abs(gp.xyz_m[2] - 0.5) < 1e-6


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestPixelToWorldErrors:
    def test_parallel_ray_raises(self) -> None:
        """Camera looking horizontally → ray parallel to ground plane."""
        # Camera looking in +x direction: R_cam_in_world s.t. camera +z → world +x
        R_side = ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
        extrinsics = CameraExtrinsics(
            R_cam_in_world=R_side,
            t_cam_in_world=(0.0, 0.0, 0.5),
        )
        det = _det(_CX - 10, _CY - 10, _CX + 10, _CY + 10)
        with pytest.raises(ValueError, match="parallel"):
            pixel_to_world(det, _intrinsics(), extrinsics, plane_z_m=0.0)


# ---------------------------------------------------------------------------
# Approach axis
# ---------------------------------------------------------------------------


class TestPixelToWorldApproachAxis:
    def test_approach_minus_z(self) -> None:
        det = _det(_CX - 10, _CY - 10, _CX + 10, _CY + 10)
        gp = pixel_to_world(det, _intrinsics(), _extrinsics(), approach_axis="-z")
        assert gp.approach_vector == (0.0, 0.0, -1.0)

    def test_approach_plus_z(self) -> None:
        det = _det(_CX - 10, _CY - 10, _CX + 10, _CY + 10)
        gp = pixel_to_world(det, _intrinsics(), _extrinsics(), approach_axis="+z")
        assert gp.approach_vector == (0.0, 0.0, 1.0)

    def test_quat_is_unit_norm(self) -> None:
        det = _det(_CX - 10, _CY - 10, _CX + 10, _CY + 10)
        gp = pixel_to_world(det, _intrinsics(), _extrinsics())
        norm = math.sqrt(sum(c ** 2 for c in gp.quat_wxyz))
        assert abs(norm - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Square bbox fallback orientation
# ---------------------------------------------------------------------------


class TestPixelToWorldSquareBbox:
    def test_square_bbox_identity_yaw(self) -> None:
        """Square bbox (w == h) → approach_minus_z quaternion only, no yaw."""
        # For "-z" approach: q = (0, 1, 0, 0)  (180° around x)
        # Square bbox → no yaw component
        det = _det(100.0, 100.0, 200.0, 200.0)  # 100×100 square
        gp = pixel_to_world(det, _intrinsics(), _extrinsics(), approach_axis="-z")
        w, x, y, z = gp.quat_wxyz
        # Expected: (0, 1, 0, 0) — 180° around x, no z-rotation
        assert abs(w) < 1e-9
        assert abs(abs(x) - 1.0) < 1e-9
        assert abs(y) < 1e-9
        assert abs(z) < 1e-9


# Silence the numpy import that ruff would flag — np is used in type hints only.
_ = np
