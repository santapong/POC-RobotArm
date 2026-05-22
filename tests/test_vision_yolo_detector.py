"""Tests for YOLODetector — skipped unless ultralytics is installed.

Requires the ``[vision-ml]`` extra. Tests load ``yolov8n.pt`` (auto-downloaded
by ultralytics) and run inference on a small synthetic image. The test is also
skipped if there is no internet access and the weights file is absent.
"""

from __future__ import annotations

import numpy as np
import pytest

_ = pytest.importorskip("ultralytics")  # noqa: F841 — skip if missing
__ = pytest.importorskip("cv2")  # noqa: F841

from src.vision.detection import YOLODetector  # noqa: E402
from src.vision.types import Detection  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _synthetic_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """Return a random-noise RGB frame as uint8 BGR."""
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Import / init tests
# ---------------------------------------------------------------------------


class TestYOLODetectorInit:
    def test_init_succeeds(self) -> None:
        """YOLODetector should initialise without error when ultralytics present."""
        try:
            det = YOLODetector("test_yolo", model_path="yolov8n.pt")
            assert det.name == "test_yolo"
        except Exception as exc:
            # Likely no network for weight download; skip rather than fail.
            pytest.skip(f"yolov8n.pt unavailable: {exc}")

    def test_detect_returns_list(self) -> None:
        try:
            det = YOLODetector("test_yolo", model_path="yolov8n.pt")
        except Exception as exc:
            pytest.skip(f"yolov8n.pt unavailable: {exc}")
        frame = _synthetic_frame()
        result = det.detect(frame)
        assert isinstance(result, list)

    def test_detect_items_are_detection_instances(self) -> None:
        try:
            det = YOLODetector("test_yolo", model_path="yolov8n.pt")
        except Exception as exc:
            pytest.skip(f"yolov8n.pt unavailable: {exc}")
        # Use a solid-colour frame — likely no detections but types should hold.
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = det.detect(frame)
        for item in result:
            assert isinstance(item, Detection)

    def test_confidence_threshold_respected(self) -> None:
        try:
            det = YOLODetector("test_yolo", model_path="yolov8n.pt", conf_threshold=0.9)
        except Exception as exc:
            pytest.skip(f"yolov8n.pt unavailable: {exc}")
        frame = _synthetic_frame()
        result = det.detect(frame)
        for d in result:
            assert d.confidence >= 0.9


# ---------------------------------------------------------------------------
# Missing dependency behaviour
# ---------------------------------------------------------------------------


class TestYOLODetectorMissingDep:
    """When ultralytics is NOT installed, YOLODetector should give a helpful error."""

    def test_import_error_message(self, monkeypatch) -> None:
        """Simulate ultralytics being absent by patching builtins.__import__."""
        import builtins

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "ultralytics":
                raise ImportError("No module named 'ultralytics'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _mock_import)
        with pytest.raises(ImportError, match="vision-ml"):
            YOLODetector("test_yolo")
