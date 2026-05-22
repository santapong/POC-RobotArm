"""Tests for solve_hand_eye.

Generates a synthetic ground-truth eye-in-hand transform, simulates 15 robot
poses, and verifies that Park's method recovers the transform within 0.5°
rotation error and 1 mm translation error.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")  # noqa: F841
_ = pytest.importorskip("numpy")  # noqa: F841

from src.vision.hand_eye import solve_hand_eye  # noqa: E402
from src.vision.types import CameraExtrinsics  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _axis_angle_to_R(axis: np.ndarray, angle: float) -> np.ndarray:
    """Rodrigues rotation formula."""
    import cv2 as _cv2

    rvec = axis * angle
    R, _ = _cv2.Rodrigues(rvec)
    return R


def _angle_between_R(R1: np.ndarray, R2: np.ndarray) -> float:
    """Rotation angle between two rotation matrices in degrees."""
    import cv2 as _cv2

    R_rel = R1.T @ R2
    rvec, _ = _cv2.Rodrigues(R_rel)
    return float(np.linalg.norm(rvec)) * 180.0 / math.pi


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------


def _make_eye_in_hand_data(
    R_c2g_true: np.ndarray,
    t_c2g_true: np.ndarray,
    n: int = 15,
    seed: int = 42,
) -> tuple[list, list, list, list]:
    """Return (R_g2b, t_g2b, R_t2c, t_t2c) for an eye-in-hand scenario.

    Camera (c) is mounted on the gripper (g).  A calibration target is fixed
    in the world (base, b) frame.
    """
    rng = np.random.default_rng(seed)
    R_g2b_list, t_g2b_list, R_t2c_list, t_t2c_list = [], [], [], []

    # Fixed target in base frame.
    R_target_base = np.eye(3)
    t_target_base = np.array([0.2, 0.0, 0.0])

    for i in range(n):
        axis = rng.standard_normal(3)
        axis /= np.linalg.norm(axis)
        angle = 0.2 + i * 0.15
        R_g2b = _axis_angle_to_R(axis, angle)
        t_g2b = np.array([0.3 * math.cos(i * 0.8), 0.3 * math.sin(i * 0.8), 0.5])

        # Camera in base frame.
        R_cam_base = R_g2b @ R_c2g_true
        t_cam_base = R_g2b @ t_c2g_true + t_g2b

        # Target in camera frame.
        R_t2c = R_cam_base.T @ R_target_base
        t_t2c = R_cam_base.T @ (t_target_base - t_cam_base)

        R_g2b_list.append(R_g2b)
        t_g2b_list.append(t_g2b)
        R_t2c_list.append(R_t2c)
        t_t2c_list.append(t_t2c)

    return R_g2b_list, t_g2b_list, R_t2c_list, t_t2c_list


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSolveHandEyeEyeInHand:
    """Eye-in-hand: camera on gripper, target fixed."""

    _ROT_TOL_DEG = 0.5
    _TRANS_TOL_MM = 1.0

    def _ground_truth(self) -> tuple[np.ndarray, np.ndarray]:
        R_true = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=np.float64)
        t_true = np.array([0.05, 0.0, 0.1])
        return R_true, t_true

    def _solve(self, method: str = "park") -> CameraExtrinsics:
        R_true, t_true = self._ground_truth()
        R_g2b, t_g2b, R_t2c, t_t2c = _make_eye_in_hand_data(R_true, t_true)
        return solve_hand_eye(R_g2b, t_g2b, R_t2c, t_t2c, method=method, mount="eye_in_hand")  # type: ignore[arg-type]

    def test_park_rotation_within_tolerance(self) -> None:
        R_true, _ = self._ground_truth()
        result = self._solve("park")
        R_got = np.array(result.R_cam_in_world)
        err_deg = _angle_between_R(R_true, R_got)
        assert err_deg < self._ROT_TOL_DEG, f"Rotation error {err_deg:.4f}° >= {self._ROT_TOL_DEG}°"

    def test_park_translation_within_tolerance(self) -> None:
        _, t_true = self._ground_truth()
        result = self._solve("park")
        t_got = np.array(result.t_cam_in_world)
        err_mm = float(np.linalg.norm(t_got - t_true)) * 1000.0
        assert err_mm < self._TRANS_TOL_MM, f"Translation error {err_mm:.4f} mm >= {self._TRANS_TOL_MM} mm"

    def test_returns_camera_extrinsics(self) -> None:
        assert isinstance(self._solve(), CameraExtrinsics)

    def test_mount_recorded(self) -> None:
        assert self._solve().mount == "eye_in_hand"

    def test_reference_frame_default(self) -> None:
        assert self._solve().reference_frame == "base"

    def test_reference_frame_custom(self) -> None:
        R_true, t_true = self._ground_truth()
        R_g2b, t_g2b, R_t2c, t_t2c = _make_eye_in_hand_data(R_true, t_true)
        result = solve_hand_eye(R_g2b, t_g2b, R_t2c, t_t2c, mount="eye_in_hand",
                                reference_frame="world")
        assert result.reference_frame == "world"


class TestSolveHandEyeEyeToHand:
    """Eye-to-hand: camera fixed, target attached to gripper."""

    _ROT_TOL_DEG = 0.5
    _TRANS_TOL_MM = 1.0

    def _make_eye_to_hand_data(
        self, R_cam_true: np.ndarray, t_cam_true: np.ndarray, n: int = 15
    ) -> tuple[list, list, list, list]:
        """Target is attached to the gripper; camera is fixed."""
        rng = np.random.default_rng(7)
        R_g2b_list, t_g2b_list, R_t2c_list, t_t2c_list = [], [], [], []
        R_cam_inv = R_cam_true.T

        # True board-in-gripper transform (board attached to gripper).
        R_board_grip = np.eye(3)
        t_board_grip = np.array([0.0, 0.0, 0.05])

        for i in range(n):
            axis = rng.standard_normal(3)
            axis /= np.linalg.norm(axis)
            angle = 0.2 + i * 0.15
            R_g2b = _axis_angle_to_R(axis, angle)
            t_g2b = np.array([0.3 * math.cos(i * 0.8), 0.3 * math.sin(i * 0.8), 0.6])

            R_board_base = R_g2b @ R_board_grip
            t_board_base = R_g2b @ t_board_grip + t_g2b
            R_t2c = R_cam_inv @ R_board_base
            t_t2c = R_cam_inv @ (t_board_base - t_cam_true)

            R_g2b_list.append(R_g2b)
            t_g2b_list.append(t_g2b)
            R_t2c_list.append(R_t2c)
            t_t2c_list.append(t_t2c)

        return R_g2b_list, t_g2b_list, R_t2c_list, t_t2c_list

    def _ground_truth(self) -> tuple[np.ndarray, np.ndarray]:
        R_true = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.float64)
        t_true = np.array([0.0, 0.0, 1.0])
        return R_true, t_true

    def test_park_rotation_within_tolerance(self) -> None:
        R_true, t_true = self._ground_truth()
        R_g2b, t_g2b, R_t2c, t_t2c = self._make_eye_to_hand_data(R_true, t_true)
        result = solve_hand_eye(R_g2b, t_g2b, R_t2c, t_t2c, method="park",
                                mount="eye_to_hand")
        R_got = np.array(result.R_cam_in_world)
        err_deg = _angle_between_R(R_true, R_got)
        assert err_deg < self._ROT_TOL_DEG, f"Rotation error {err_deg:.4f}°"

    def test_park_translation_within_tolerance(self) -> None:
        R_true, t_true = self._ground_truth()
        R_g2b, t_g2b, R_t2c, t_t2c = self._make_eye_to_hand_data(R_true, t_true)
        result = solve_hand_eye(R_g2b, t_g2b, R_t2c, t_t2c, method="park",
                                mount="eye_to_hand")
        t_got = np.array(result.t_cam_in_world)
        err_mm = float(np.linalg.norm(t_got - t_true)) * 1000.0
        assert err_mm < self._TRANS_TOL_MM, f"Translation error {err_mm:.4f} mm"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSolveHandEyeValidation:
    def _minimal_valid(self) -> tuple:
        R = np.eye(3)
        t = np.zeros(3)
        return ([R] * 3, [t] * 3, [R] * 3, [t] * 3)

    def test_too_few_pairs_raises(self) -> None:
        R, t = np.eye(3), np.zeros(3)
        with pytest.raises(ValueError, match="3"):
            solve_hand_eye([R] * 2, [t] * 2, [R] * 2, [t] * 2)

    def test_mismatched_lengths_raises(self) -> None:
        R, t = np.eye(3), np.zeros(3)
        with pytest.raises(ValueError, match="same length"):
            solve_hand_eye([R] * 5, [t] * 4, [R] * 5, [t] * 5)

    def test_unknown_method_raises(self) -> None:
        R_g, t_g, R_t, t_t = self._minimal_valid()
        with pytest.raises(ValueError, match="method"):
            solve_hand_eye(R_g, t_g, R_t, t_t, method="bogus")  # type: ignore[arg-type]

    def test_all_methods_accepted(self) -> None:
        """All five method strings are mapped and don't raise on syntax alone."""
        R_true = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=np.float64)
        t_true = np.array([0.05, 0.0, 0.1])
        R_g2b, t_g2b, R_t2c, t_t2c = _make_eye_in_hand_data(R_true, t_true, n=10)
        for m in ("tsai", "park", "horaud", "andreff", "daniilidis"):
            result = solve_hand_eye(R_g2b, t_g2b, R_t2c, t_t2c, method=m,  # type: ignore[arg-type]
                                    mount="eye_in_hand")
            assert isinstance(result, CameraExtrinsics)
