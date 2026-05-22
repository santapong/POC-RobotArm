"""Tests for ColorDetector: synthetic red square → bbox ±2 px.

A red square is painted directly onto a numpy array using BGR values that
map to the default HSV red range; no image files are needed.
"""

from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")  # noqa: F841
_ = pytest.importorskip("numpy")  # noqa: F841 — ensure numpy available before imports below

from src.vision.detection import ColorDetector  # noqa: E402
from src.vision.types import Detection  # noqa: E402


def _make_red_frame(
    width: int = 640,
    height: int = 480,
    x1: int = 200,
    y1: int = 150,
    x2: int = 440,
    y2: int = 330,
) -> np.ndarray:
    """Return a BGR frame with a pure red rectangle and black background."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    # Pure red in BGR: (0, 0, 255) → HSV ≈ (0°, 100%, 100%) → H=0 in OpenCV [0,179]
    frame[y1:y2, x1:x2] = (0, 0, 255)
    return frame


class TestColorDetectorBasic:
    def test_detects_red_square(self) -> None:
        detector = ColorDetector("test_red")
        frame = _make_red_frame()
        dets = detector.detect(frame)
        assert len(dets) >= 1, "Expected at least one detection"

    def test_detection_type(self) -> None:
        detector = ColorDetector("test_red")
        dets = detector.detect(_make_red_frame())
        assert all(isinstance(d, Detection) for d in dets)

    def test_class_name(self) -> None:
        detector = ColorDetector("test_red", class_name="my_cube")
        dets = detector.detect(_make_red_frame())
        assert dets[0].class_name == "my_cube"

    def test_confidence_in_range(self) -> None:
        detector = ColorDetector("test_red")
        for det in detector.detect(_make_red_frame()):
            assert 0.0 <= det.confidence <= 1.0


class TestColorDetectorBboxAccuracy:
    """Detected bounding box should be within ±2 pixels of the true square."""

    _TOL = 2  # pixels

    def test_bbox_x1_within_tolerance(self) -> None:
        x1_true, y1_true, x2_true, y2_true = 200, 150, 440, 330
        frame = _make_red_frame(x1=x1_true, y1=y1_true, x2=x2_true, y2=y2_true)
        dets = ColorDetector("test_red").detect(frame)
        assert len(dets) >= 1
        det = dets[0]
        assert abs(det.bbox_xyxy[0] - x1_true) <= self._TOL, (
            f"x1 expected ≈{x1_true}, got {det.bbox_xyxy[0]}"
        )

    def test_bbox_y1_within_tolerance(self) -> None:
        x1_true, y1_true, x2_true, y2_true = 200, 150, 440, 330
        frame = _make_red_frame(x1=x1_true, y1=y1_true, x2=x2_true, y2=y2_true)
        dets = ColorDetector("test_red").detect(frame)
        det = dets[0]
        assert abs(det.bbox_xyxy[1] - y1_true) <= self._TOL

    def test_bbox_x2_within_tolerance(self) -> None:
        x1_true, y1_true, x2_true, y2_true = 200, 150, 440, 330
        frame = _make_red_frame(x1=x1_true, y1=y1_true, x2=x2_true, y2=y2_true)
        dets = ColorDetector("test_red").detect(frame)
        det = dets[0]
        assert abs(det.bbox_xyxy[2] - x2_true) <= self._TOL

    def test_bbox_y2_within_tolerance(self) -> None:
        x1_true, y1_true, x2_true, y2_true = 200, 150, 440, 330
        frame = _make_red_frame(x1=x1_true, y1=y1_true, x2=x2_true, y2=y2_true)
        dets = ColorDetector("test_red").detect(frame)
        det = dets[0]
        assert abs(det.bbox_xyxy[3] - y2_true) <= self._TOL

    def test_no_detection_on_black_frame(self) -> None:
        detector = ColorDetector("test_red")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        dets = detector.detect(frame)
        assert dets == []

    def test_no_detection_on_blue_frame(self) -> None:
        detector = ColorDetector("test_red")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :, 0] = 255  # pure blue
        dets = detector.detect(frame)
        assert dets == []

    def test_min_area_filter(self) -> None:
        """A tiny red patch below min_area_px should not be returned."""
        detector = ColorDetector("test_red", min_area_px=5000)
        # Small 10×10 red patch — area = 100 < 5000
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[100:110, 100:110] = (0, 0, 255)
        dets = detector.detect(frame)
        assert dets == []


class TestColorDetectorDualRange:
    """Second HSV range (red wraparound) is OR-ed into the mask."""

    def test_high_hue_red_detected(self) -> None:
        """Pixels with H ≈ 175 (near 180) are caught by the wraparound range."""
        import cv2 as _cv2

        # H=175 in OpenCV = 350°/2 = pixel hue 175
        # Create an HSV image and convert to BGR
        hsv_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        hsv_frame[100:300, 100:400] = (175, 200, 200)  # high-hue red
        bgr_frame = _cv2.cvtColor(hsv_frame, _cv2.COLOR_HSV2BGR)

        detector = ColorDetector("test_red")
        dets = detector.detect(bgr_frame)
        assert len(dets) >= 1

    def test_no_second_range(self) -> None:
        """With hsv_lower2=None, only the primary range is used."""
        import cv2 as _cv2

        detector = ColorDetector("test_red", hsv_lower2=None, hsv_upper2=None)
        # High-hue red pixel: should NOT be detected without the second range.
        hsv_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        hsv_frame[100:300, 100:400] = (175, 200, 200)
        bgr_frame = _cv2.cvtColor(hsv_frame, _cv2.COLOR_HSV2BGR)
        dets = detector.detect(bgr_frame)
        # Should not detect (hue 175 is outside 0-10 range)
        assert len(dets) == 0
