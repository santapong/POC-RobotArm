"""Object detection pipeline.

Provides a ``Detector`` ABC and two concrete detectors:

- ``ColorDetector`` — HSV thresholding with dual-range support (red wraparound),
  morphological filtering, and contour-based bounding boxes.
- ``YOLODetector`` — wraps ``ultralytics`` YOLO; requires the ``[vision-ml]``
  extra. The import is deferred to ``__init__`` so this module is importable
  without ultralytics installed.

Notes
-----
- All ``cv2`` calls happen on the calling thread; the vision runtime is
  responsible for dispatching to a thread-pool executor if needed.
- ``ColorDetector`` confidence is ``contour_area / frame_area``, clipped to
  ``[0, 1]``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import cv2
import numpy as np

from src.vision.types import Detection

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class Detector(ABC):
    """Abstract detector interface.

    Subclasses must implement :meth:`detect`, which accepts an ``H×W×3``
    uint8 BGR frame and returns a (possibly empty) list of :class:`Detection`.
    """

    def __init__(self, name: str) -> None:
        self.name: str = name

    @abstractmethod
    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Run detection and return results for *frame_bgr*."""
        ...

    def close(self) -> None:
        """Release any model resources (no-op for most detectors)."""


# ---------------------------------------------------------------------------
# ColorDetector
# ---------------------------------------------------------------------------


class ColorDetector(Detector):
    """HSV colour-blob detector.

    Converts BGR→HSV, applies a primary ``[hsv_lower, hsv_upper]`` threshold
    plus an optional second range (default: red hue wraparound), runs
    morphological open→close with a 5×5 kernel, finds external contours, and
    filters by ``min_area_px``. Each surviving contour produces one
    :class:`Detection` whose confidence equals the contour area divided by the
    frame area, clipped to ``[0, 1]``.

    Parameters
    ----------
    name:
        Logical detector name used by the vision runtime.
    hsv_lower, hsv_upper:
        Primary HSV threshold range (OpenCV scale: H in [0,179], S/V in [0,255]).
    hsv_lower2, hsv_upper2:
        Second threshold range OR-ed into the mask. Set both to ``None`` to
        disable the second range.
    min_area_px:
        Contours with pixel area below this value are ignored.
    class_name:
        Class label assigned to every detection produced by this detector.
    """

    _KERNEL_SIZE: int = 5

    def __init__(
        self,
        name: str,
        hsv_lower: tuple[int, int, int] = (0, 120, 70),
        hsv_upper: tuple[int, int, int] = (10, 255, 255),
        hsv_lower2: Optional[tuple[int, int, int]] = (170, 120, 70),
        hsv_upper2: Optional[tuple[int, int, int]] = (180, 255, 255),
        min_area_px: float = 200.0,
        class_name: str = "red_cube",
    ) -> None:
        super().__init__(name)
        self._lower1 = np.array(hsv_lower, dtype=np.uint8)
        self._upper1 = np.array(hsv_upper, dtype=np.uint8)
        self._lower2: Optional[np.ndarray] = (
            np.array(hsv_lower2, dtype=np.uint8) if hsv_lower2 is not None else None
        )
        self._upper2: Optional[np.ndarray] = (
            np.array(hsv_upper2, dtype=np.uint8) if hsv_upper2 is not None else None
        )
        self._min_area = float(min_area_px)
        self._class_name = class_name
        kernel_sz = self._KERNEL_SIZE
        self._kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (kernel_sz, kernel_sz)
        )

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Detect colour blobs in *frame_bgr*.

        Parameters
        ----------
        frame_bgr:
            ``H×W×3`` uint8 BGR image.

        Returns
        -------
        list[Detection]
            One entry per contour that passes the area filter, ordered by
            descending area.
        """
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._lower1, self._upper1)
        if self._lower2 is not None and self._upper2 is not None:
            mask2 = cv2.inRange(hsv, self._lower2, self._upper2)
            mask = cv2.bitwise_or(mask, mask2)

        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h, w = frame_bgr.shape[:2]
        frame_area = float(h * w)

        detections: list[Detection] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            x1, y1, x2, y2 = float(x), float(y), float(x + bw), float(y + bh)
            # Confidence: fraction of frame area this contour occupies.
            confidence = min(area / frame_area, 1.0)
            detections.append(
                Detection(
                    class_name=self._class_name,
                    confidence=confidence,
                    bbox_xyxy=(x1, y1, x2, y2),
                )
            )

        detections.sort(key=lambda d: d.bbox_xyxy[2] - d.bbox_xyxy[0], reverse=True)
        return detections


# ---------------------------------------------------------------------------
# YOLODetector
# ---------------------------------------------------------------------------


class YOLODetector(Detector):
    """YOLO object detector backed by the ``ultralytics`` library.

    The ``ultralytics`` package is imported lazily inside ``__init__`` so that
    the rest of the vision library remains importable without it. If the import
    fails a descriptive ``ImportError`` is raised pointing to the correct extra.

    Parameters
    ----------
    name:
        Logical detector name.
    model_path:
        Path to a YOLO model weights file (e.g. ``"yolov8n.pt"``). If the
        file does not exist locally, ultralytics will attempt to download it.
    conf_threshold:
        Minimum confidence score for a detection to be included.
    class_filter:
        If provided, only detections whose class name is in this list are
        returned. ``None`` means all classes are returned.
    """

    def __init__(
        self,
        name: str,
        model_path: str = "yolov8n.pt",
        conf_threshold: float = 0.25,
        class_filter: Optional[list[str]] = None,
    ) -> None:
        super().__init__(name)
        try:
            from ultralytics import YOLO  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "ultralytics required — install [vision-ml] extra"
            ) from exc
        self._model = YOLO(model_path)
        self._conf = conf_threshold
        self._class_filter: Optional[set[str]] = (
            set(class_filter) if class_filter is not None else None
        )

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Run YOLO inference on *frame_bgr* and return detections.

        Parameters
        ----------
        frame_bgr:
            ``H×W×3`` uint8 BGR image.

        Returns
        -------
        list[Detection]
            Detections above ``conf_threshold``, optionally filtered by class.
        """
        results = self._model(frame_bgr, conf=self._conf, verbose=False)
        detections: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                cls_name = result.names[cls_id]
                if self._class_filter is not None and cls_name not in self._class_filter:
                    continue
                conf = float(box.conf[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                # Guard against degenerate boxes (can occur near image border).
                if x2 <= x1 or y2 <= y1:
                    continue
                detections.append(
                    Detection(
                        class_name=cls_name,
                        confidence=conf,
                        bbox_xyxy=(x1, y1, x2, y2),
                    )
                )
        return detections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "ColorDetector",
    "Detector",
    "YOLODetector",
]
