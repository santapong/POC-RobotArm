"""Vision pipeline library for POC-RobotArm.

Re-exports the full public surface of the ``src.vision`` package so that
callers can write::

    from src.vision import FakeCamera, ColorDetector, pixel_to_world

Notes
-----
- ``cv2`` is not imported at this level; individual submodules perform their
  own imports so the package is importable even without ``opencv-contrib-python``
  installed.  Instantiating any class that needs cv2 will fail with a clear
  ImportError if the ``[vision]`` extra is absent.
- ``types.py`` is stdlib-only and always importable.
"""

from __future__ import annotations

from src.vision.calibration import CharucoBoardSpec, calibrate_intrinsic, detect_charuco
from src.vision.capture import Camera, FakeCamera, RealCamera
from src.vision.detection import ColorDetector, Detector, YOLODetector
from src.vision.grasp import pixel_to_world
from src.vision.hand_eye import solve_hand_eye
from src.vision.types import CameraExtrinsics, CameraIntrinsics, Detection, GraspPose

__all__: list[str] = [
    # Capture
    "Camera",
    "FakeCamera",
    "RealCamera",
    # Detection
    "ColorDetector",
    "Detector",
    "YOLODetector",
    # Types
    "CameraExtrinsics",
    "CameraIntrinsics",
    "Detection",
    "GraspPose",
    # Calibration
    "CharucoBoardSpec",
    "calibrate_intrinsic",
    "detect_charuco",
    # Hand-eye
    "solve_hand_eye",
    # Grasp
    "pixel_to_world",
]
