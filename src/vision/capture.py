"""Camera capture abstractions.

Provides a ``Camera`` ABC with two concrete implementations:

- ``RealCamera`` wraps ``cv2.VideoCapture`` for USB / V4L2 webcams.
- ``FakeCamera`` cycles through pre-loaded image files (or generates a solid
  colour test pattern when no paths are provided).

Notes
-----
- ``cv2`` is imported at module level; the ``[vision]`` extra must be installed
  before any class in this module is instantiated.
- ``FakeCamera`` with a single path returns the same frame on every call —
  useful for deterministic unit tests.
- ``FakeCamera`` with ``loop=False`` raises ``StopIteration`` after the last
  image (frame exhaustion is a deliberate design signal, not an error to swallow).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class Camera(ABC):
    """Abstract camera interface.

    Subclasses must implement :meth:`read` (returns a BGR uint8 frame) and
    :meth:`close`. Callers should treat cameras as context managers or call
    :meth:`close` explicitly when done.
    """

    def __init__(self, name: str, width: int, height: int) -> None:
        self.name: str = name
        self.width: int = width
        self.height: int = height

    @abstractmethod
    def read(self) -> np.ndarray:
        """Return the next frame as an ``H×W×3`` uint8 BGR array."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the camera."""
        ...

    def is_open(self) -> bool:
        """Return ``True`` if the camera is still able to produce frames."""
        return True

    def __enter__(self) -> Camera:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# RealCamera
# ---------------------------------------------------------------------------


class RealCamera(Camera):
    """Live capture from a USB / V4L2 webcam via ``cv2.VideoCapture``.

    Parameters
    ----------
    name:
        Logical name for this camera (used by the vision runtime).
    source:
        Integer device index (e.g. ``0``) or a URL / GStreamer pipeline string.
    width, height:
        Requested frame dimensions; the driver may round to a supported size.
    """

    def __init__(
        self,
        name: str,
        source: int | str,
        width: int = 640,
        height: int = 480,
    ) -> None:
        super().__init__(name, width, height)
        self._cap = cv2.VideoCapture(source)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"RealCamera {name!r}: failed to open source {source!r}"
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self) -> np.ndarray:
        """Capture and return the next frame.

        Raises
        ------
        RuntimeError
            If the capture device is closed or returns an empty frame.
        """
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"RealCamera {self.name!r}: failed to read frame")
        return frame

    def close(self) -> None:
        """Release the underlying ``cv2.VideoCapture``."""
        self._cap.release()

    def is_open(self) -> bool:
        return self._cap.isOpened()


# ---------------------------------------------------------------------------
# FakeCamera
# ---------------------------------------------------------------------------


class FakeCamera(Camera):
    """Deterministic camera backed by image files or a generated test pattern.

    Parameters
    ----------
    name:
        Logical name for this camera.
    image_paths:
        List of absolute paths to BGR image files (JPEG / PNG / etc.).
        If the list is empty a solid-colour test pattern is generated.
        If the list has exactly one entry, every ``read()`` returns the same frame.
    width, height:
        All loaded images are resized to this resolution.
    loop:
        When ``True`` (default) the sequence restarts after the last image.
        When ``False`` a ``StopIteration`` is raised once all images are
        exhausted.
    fps:
        Nominal frame rate (informational; ``FakeCamera.read()`` is
        synchronous and does not sleep).
    """

    def __init__(
        self,
        name: str,
        image_paths: list[str],
        width: int = 640,
        height: int = 480,
        loop: bool = True,
        fps: float = 15.0,
    ) -> None:
        super().__init__(name, width, height)
        self.fps = fps
        self._loop = loop
        self._index: int = 0
        self._closed: bool = False

        if not image_paths:
            # Generate a solid blue-ish test pattern — easily distinguishable
            # from real footage in logs.
            self._frames: list[np.ndarray] = [self._make_test_pattern(width, height)]
        else:
            self._frames = self._load_images(image_paths, width, height)

    # ------------------------------------------------------------------
    # Camera interface
    # ------------------------------------------------------------------

    def read(self) -> np.ndarray:
        """Return the next frame in the sequence.

        Raises
        ------
        RuntimeError
            If the camera has been closed.
        StopIteration
            If ``loop=False`` and all images have been returned.
        """
        if self._closed:
            raise RuntimeError(f"FakeCamera {self.name!r}: camera is closed")
        if self._index >= len(self._frames):
            if self._loop:
                self._index = 0
            else:
                raise StopIteration(f"FakeCamera {self.name!r}: frame sequence exhausted")
        frame = self._frames[self._index]
        # Only advance for multi-frame cameras; single-frame stays deterministic.
        if len(self._frames) > 1:
            self._index += 1
        return frame.copy()

    def close(self) -> None:
        """Mark the camera as closed; subsequent ``read()`` calls will raise."""
        self._closed = True

    def is_open(self) -> bool:
        return not self._closed

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_test_pattern(width: int, height: int) -> np.ndarray:
        """Return an ``H×W×3`` uint8 BGR solid-colour test frame (blue)."""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = 200  # blue channel
        frame[:, :, 1] = 50
        frame[:, :, 2] = 50
        return frame

    @staticmethod
    def _load_images(paths: list[str], width: int, height: int) -> list[np.ndarray]:
        """Load and resize images from disk."""
        frames: list[np.ndarray] = []
        for p in paths:
            if not os.path.isfile(p):
                raise FileNotFoundError(f"FakeCamera: image not found: {p!r}")
            img = cv2.imread(p)
            if img is None:
                raise ValueError(f"FakeCamera: cv2.imread returned None for {p!r}")
            if img.shape[1] != width or img.shape[0] != height:
                img = cv2.resize(img, (width, height))
            frames.append(img)
        return frames


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "Camera",
    "FakeCamera",
    "RealCamera",
]
