"""Tests for src.vision.types — round-trip and validator behaviour.

Only the standard library and numpy are required; cv2 is not needed.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.vision.types import CameraExtrinsics, CameraIntrinsics, Detection, GraspPose

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EYE_3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
_VALID_INTRINSICS = dict(fx=600.0, fy=600.0, cx=320.0, cy=240.0, width=640, height=480,
                          dist_coeffs=(0.0,) * 5)


# ---------------------------------------------------------------------------
# CameraIntrinsics
# ---------------------------------------------------------------------------


class TestCameraIntrinsics:
    def test_round_trip(self) -> None:
        ci = CameraIntrinsics(**_VALID_INTRINSICS)
        d = ci.to_dict()
        ci2 = CameraIntrinsics.from_dict(d)
        assert ci == ci2

    def test_type_discriminator_present(self) -> None:
        d = CameraIntrinsics(**_VALID_INTRINSICS).to_dict()
        assert d["__type__"] == "CameraIntrinsics"

    def test_from_dict_rejects_wrong_type(self) -> None:
        d = CameraIntrinsics(**_VALID_INTRINSICS).to_dict()
        d["__type__"] = "CameraExtrinsics"
        with pytest.raises(ValueError, match="CameraIntrinsics"):
            CameraIntrinsics.from_dict(d)

    def test_K_shape(self) -> None:
        ci = CameraIntrinsics(**_VALID_INTRINSICS)
        K = ci.K()
        assert len(K) == 3 and all(len(row) == 3 for row in K)
        assert K[0][0] == 600.0
        assert K[1][1] == 600.0
        assert K[0][2] == 320.0
        assert K[1][2] == 240.0
        assert K[2] == [0.0, 0.0, 1.0]

    def test_K_np_dtype(self) -> None:
        ci = CameraIntrinsics(**_VALID_INTRINSICS)
        K = ci.K_np()
        assert K.dtype == np.float64
        assert K.shape == (3, 3)

    @pytest.mark.parametrize("length", [4, 5, 8, 14])
    def test_valid_dist_coeffs_lengths(self, length: int) -> None:
        CameraIntrinsics(**{**_VALID_INTRINSICS, "dist_coeffs": (0.0,) * length})

    @pytest.mark.parametrize("length", [0, 1, 3, 6, 7, 9, 13, 15])
    def test_invalid_dist_coeffs_length(self, length: int) -> None:
        with pytest.raises(ValueError, match="dist_coeffs"):
            CameraIntrinsics(**{**_VALID_INTRINSICS, "dist_coeffs": (0.0,) * length})


# ---------------------------------------------------------------------------
# CameraExtrinsics
# ---------------------------------------------------------------------------


class TestCameraExtrinsics:
    def _make(self, **kwargs) -> CameraExtrinsics:
        defaults = dict(
            R_cam_in_world=_EYE_3,
            t_cam_in_world=(0.0, 0.0, 1.0),
        )
        defaults.update(kwargs)
        return CameraExtrinsics(**defaults)

    def test_round_trip(self) -> None:
        ex = self._make()
        ex2 = CameraExtrinsics.from_dict(ex.to_dict())
        assert ex == ex2

    def test_type_discriminator(self) -> None:
        assert self._make().to_dict()["__type__"] == "CameraExtrinsics"

    def test_from_dict_wrong_type(self) -> None:
        d = self._make().to_dict()
        d["__type__"] = "GraspPose"
        with pytest.raises(ValueError, match="CameraExtrinsics"):
            CameraExtrinsics.from_dict(d)

    def test_default_reference_frame(self) -> None:
        assert self._make().reference_frame == "world"

    def test_bad_rotation_shape(self) -> None:
        with pytest.raises(ValueError, match="3×3"):
            CameraExtrinsics(
                R_cam_in_world=((1.0, 0.0), (0.0, 1.0)),  # type: ignore[arg-type]
                t_cam_in_world=(0.0, 0.0, 1.0),
            )

    def test_bad_mount(self) -> None:
        with pytest.raises(ValueError, match="mount"):
            self._make(mount="sideways")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# GraspPose
# ---------------------------------------------------------------------------


class TestGraspPose:
    def _make(self, **kwargs) -> GraspPose:
        defaults = dict(
            xyz_m=(0.1, 0.2, 0.0),
            quat_wxyz=(1.0, 0.0, 0.0, 0.0),
            frame="world",
        )
        defaults.update(kwargs)
        return GraspPose(**defaults)

    def test_round_trip(self) -> None:
        gp = self._make()
        gp2 = GraspPose.from_dict(gp.to_dict())
        assert gp == gp2

    def test_type_discriminator(self) -> None:
        assert self._make().to_dict()["__type__"] == "GraspPose"

    def test_from_dict_wrong_type(self) -> None:
        d = self._make().to_dict()
        d["__type__"] = "Detection"
        with pytest.raises(ValueError, match="GraspPose"):
            GraspPose.from_dict(d)

    def test_non_unit_quat_rejected(self) -> None:
        # (0.3, 0.3, 0.3, 0.3) has norm ≈ 0.6, not unit-norm.
        with pytest.raises(ValueError, match="unit-norm"):
            self._make(quat_wxyz=(0.3, 0.3, 0.3, 0.3))

    def test_approach_vector_non_unit_rejected(self) -> None:
        with pytest.raises(ValueError, match="unit-norm"):
            self._make(approach_vector=(1.0, 1.0, 0.0))

    def test_default_approach_vector(self) -> None:
        gp = self._make()
        assert gp.approach_vector == (0.0, 0.0, -1.0)

    def test_valid_non_identity_quat(self) -> None:
        # 90° rotation around z: w = cos(45°), z = sin(45°)
        v = math.sqrt(0.5)
        gp = self._make(quat_wxyz=(v, 0.0, 0.0, v))
        assert abs(math.sqrt(sum(c ** 2 for c in gp.quat_wxyz)) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class TestDetection:
    def _make(self, **kwargs) -> Detection:
        defaults = dict(
            class_name="cube",
            confidence=0.9,
            bbox_xyxy=(10.0, 20.0, 50.0, 60.0),
        )
        defaults.update(kwargs)
        return Detection(**defaults)

    def test_round_trip(self) -> None:
        det = self._make()
        det2 = Detection.from_dict(det.to_dict())
        assert det == det2

    def test_round_trip_with_pose(self) -> None:
        gp = GraspPose(xyz_m=(0.0, 0.0, 0.0), quat_wxyz=(1.0, 0.0, 0.0, 0.0), frame="cam")
        det = self._make(pose_in_camera=gp)
        det2 = Detection.from_dict(det.to_dict())
        assert det2.pose_in_camera == gp

    def test_type_discriminator(self) -> None:
        assert self._make().to_dict()["__type__"] == "Detection"

    def test_from_dict_wrong_type(self) -> None:
        d = self._make().to_dict()
        d["__type__"] = "CameraIntrinsics"
        with pytest.raises(ValueError, match="Detection"):
            Detection.from_dict(d)

    def test_confidence_out_of_range_low(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            self._make(confidence=-0.01)

    def test_confidence_out_of_range_high(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            self._make(confidence=1.01)

    def test_bbox_x_wrong_order(self) -> None:
        with pytest.raises(ValueError, match="x2 > x1"):
            self._make(bbox_xyxy=(50.0, 20.0, 10.0, 60.0))

    def test_bbox_y_wrong_order(self) -> None:
        with pytest.raises(ValueError, match="y2 > y1"):
            self._make(bbox_xyxy=(10.0, 60.0, 50.0, 20.0))

    def test_bbox_equal_x_rejected(self) -> None:
        with pytest.raises(ValueError):
            self._make(bbox_xyxy=(10.0, 20.0, 10.0, 60.0))

    def test_confidence_boundary_zero(self) -> None:
        d = self._make(confidence=0.0)
        assert d.confidence == 0.0

    def test_confidence_boundary_one(self) -> None:
        d = self._make(confidence=1.0)
        assert d.confidence == 1.0

    def test_mask_none_default(self) -> None:
        assert self._make().mask is None
