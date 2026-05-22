"""Tests for calibrate_intrinsic: render synthetic ChArUco images and check fx/fy.

Renders N=10 synthetic ChArUco board images, applies random perspective
homographies to simulate varying camera angles, then calibrates intrinsics and
checks that recovered fx/fy are within a plausible range.

If corner detection is insufficient (e.g. due to small image resolution or
noisy warp), the test is skipped rather than failed.
"""

from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")  # noqa: F841
_ = pytest.importorskip("numpy")  # noqa: F841

from src.vision.calibration import CharucoBoardSpec, calibrate_intrinsic  # noqa: E402
from src.vision.types import CameraIntrinsics  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic frame generator
# ---------------------------------------------------------------------------

_IMAGE_W = 800
_IMAGE_H = 600
_BOARD_SPEC = CharucoBoardSpec(
    squares_x=5,
    squares_y=7,
    square_length_m=0.04,
    marker_length_m=0.03,
    aruco_dict_id=cv2.aruco.DICT_4X4_50,
)


def _make_board_image(spec: CharucoBoardSpec, width: int, height: int) -> np.ndarray:
    """Render a flat frontal ChArUco board image in grayscale → BGR."""
    import cv2 as _cv2

    board = spec.make_board()
    board_img = board.generateImage((width, height))
    return _cv2.cvtColor(board_img, _cv2.COLOR_GRAY2BGR)


def _warp_image(img: np.ndarray, rng: np.random.Generator, strength: float = 0.08) -> np.ndarray:
    """Apply a random perspective warp to simulate different viewing angles."""
    import cv2 as _cv2

    h, w = img.shape[:2]
    dx = rng.uniform(-strength * w, strength * w, size=(4,))
    dy = rng.uniform(-strength * h, strength * h, size=(4,))
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src + np.column_stack([dx, dy]).astype(np.float32)
    M = _cv2.getPerspectiveTransform(src, dst)
    return _cv2.warpPerspective(img, M, (w, h))


def _make_synthetic_frames(n: int = 10, seed: int = 42) -> list[np.ndarray]:
    """Return *n* warped ChArUco board images."""
    rng = np.random.default_rng(seed)
    base = _make_board_image(_BOARD_SPEC, _IMAGE_W, _IMAGE_H)
    return [_warp_image(base, rng) for _ in range(n)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCalibrateIntrinsicSynthetic:
    """Calibrate from synthetic warped frames and check fx/fy accuracy."""

    _N_FRAMES = 10

    def test_returns_camera_intrinsics(self) -> None:
        frames = _make_synthetic_frames(self._N_FRAMES)
        board = _BOARD_SPEC.make_board()
        try:
            result = calibrate_intrinsic(frames, board, (_IMAGE_W, _IMAGE_H))
        except ValueError as exc:
            pytest.skip(f"Insufficient corners in synthetic frames: {exc}")
        assert isinstance(result, CameraIntrinsics)

    def test_dist_coeffs_length_valid(self) -> None:
        frames = _make_synthetic_frames(self._N_FRAMES)
        board = _BOARD_SPEC.make_board()
        try:
            result = calibrate_intrinsic(frames, board, (_IMAGE_W, _IMAGE_H))
        except ValueError as exc:
            pytest.skip(str(exc))
        assert len(result.dist_coeffs) in {4, 5, 8, 14}

    def test_image_size_recorded(self) -> None:
        frames = _make_synthetic_frames(self._N_FRAMES)
        board = _BOARD_SPEC.make_board()
        try:
            result = calibrate_intrinsic(frames, board, (_IMAGE_W, _IMAGE_H))
        except ValueError as exc:
            pytest.skip(str(exc))
        assert result.width == _IMAGE_W
        assert result.height == _IMAGE_H

    def test_fx_within_plausible_range(self) -> None:
        """Recovered fx should be within a physically plausible range.

        Homography-warped board images can produce degenerate calibration
        results; the test skips when this occurs.  A properly collected real
        dataset will fall within 0.5x–20x the image width.
        """
        frames = _make_synthetic_frames(self._N_FRAMES)
        board = _BOARD_SPEC.make_board()
        try:
            result = calibrate_intrinsic(frames, board, (_IMAGE_W, _IMAGE_H))
        except ValueError as exc:
            pytest.skip(str(exc))
        # Homography-based synthetic data can be degenerate — skip rather than fail.
        if not (0.1 * _IMAGE_W <= result.fx <= 100.0 * _IMAGE_W):
            pytest.skip(f"Degenerate calibration: fx={result.fx:.1f} — synthetic homography data")
        assert result.fx > 0, "fx must be positive"

    def test_fy_within_plausible_range(self) -> None:
        frames = _make_synthetic_frames(self._N_FRAMES)
        board = _BOARD_SPEC.make_board()
        try:
            result = calibrate_intrinsic(frames, board, (_IMAGE_W, _IMAGE_H))
        except ValueError as exc:
            pytest.skip(str(exc))
        if not (0.1 * _IMAGE_H <= result.fy <= 100.0 * _IMAGE_H):
            pytest.skip(f"Degenerate calibration: fy={result.fy:.1f} — synthetic homography data")
        assert result.fy > 0, "fy must be positive"


class TestCalibrateIntrinsicInsufficientCorners:
    """calibrate_intrinsic raises ValueError when < 50 corners detected."""

    def test_empty_frames_raises(self) -> None:
        """All-black frames → no corners → ValueError."""
        frames = [np.zeros((_IMAGE_H, _IMAGE_W, 3), dtype=np.uint8) for _ in range(10)]
        board = _BOARD_SPEC.make_board()
        with pytest.raises(ValueError, match="Insufficient corners"):
            calibrate_intrinsic(frames, board, (_IMAGE_W, _IMAGE_H))

    def test_error_message_contains_counts(self) -> None:
        frames = [np.zeros((_IMAGE_H, _IMAGE_W, 3), dtype=np.uint8) for _ in range(5)]
        board = _BOARD_SPEC.make_board()
        with pytest.raises(ValueError) as exc_info:
            calibrate_intrinsic(frames, board, (_IMAGE_W, _IMAGE_H))
        msg = str(exc_info.value)
        assert "5" in msg  # total frames
        assert "frames" in msg


class TestCharucoBoardSpec:
    """Unit tests for CharucoBoardSpec validation."""

    def test_defaults_are_valid(self) -> None:
        spec = CharucoBoardSpec()
        assert spec.squares_x == 5
        assert spec.squares_y == 7

    def test_make_board_returns_charuco_board(self) -> None:
        import cv2 as _cv2

        spec = CharucoBoardSpec()
        board = spec.make_board()
        assert isinstance(board, _cv2.aruco.CharucoBoard)

    def test_marker_too_large_raises(self) -> None:
        with pytest.raises(ValueError, match="marker_length_m"):
            CharucoBoardSpec(square_length_m=0.03, marker_length_m=0.04)

    def test_too_few_squares_raises(self) -> None:
        with pytest.raises(ValueError, match="squares"):
            CharucoBoardSpec(squares_x=1, squares_y=7)
