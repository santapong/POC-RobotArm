"""Camera intrinsic calibration using ChArUco boards.

Uses the unified ``cv2.aruco.CharucoDetector`` API introduced in OpenCV 4.7.
Requires ``opencv-contrib-python >= 4.10`` (``[vision]`` extra).

Notes
-----
- ``CharucoBoardSpec`` is a frozen dataclass; create one and pass it to both
  ``detect_charuco`` and ``calibrate_intrinsic``.
- ``calibrate_intrinsic`` raises ``ValueError`` when fewer than 50 corners have
  been detected across all supplied frames; the error message names the counts
  so the caller can surface them to the UI.
- All ``cv2`` calls are made on the calling thread.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from src.vision.types import CameraIntrinsics

# ---------------------------------------------------------------------------
# Board spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CharucoBoardSpec:
    """Parameters for a ChArUco calibration board.

    Defaults match a commonly 3D-printed A3 board (5×7 squares, 4 cm squares,
    3 cm ArUco markers, 4×4_50 dictionary).

    Parameters
    ----------
    squares_x, squares_y:
        Number of chessboard squares along x and y axes.
    square_length_m:
        Side length of a chessboard square in metres.
    marker_length_m:
        Side length of the embedded ArUco marker in metres; must be smaller
        than ``square_length_m``.
    aruco_dict_id:
        ``cv2.aruco.DICT_*`` constant identifying the ArUco dictionary.
    """

    squares_x: int = 5
    squares_y: int = 7
    square_length_m: float = 0.04
    marker_length_m: float = 0.03
    aruco_dict_id: int = cv2.aruco.DICT_4X4_50

    def __post_init__(self) -> None:
        if self.squares_x < 2 or self.squares_y < 2:
            raise ValueError("CharucoBoardSpec: squares_x and squares_y must be >= 2")
        if self.marker_length_m >= self.square_length_m:
            raise ValueError(
                "CharucoBoardSpec: marker_length_m must be < square_length_m"
            )

    def make_board(self) -> cv2.aruco.CharucoBoard:
        """Instantiate and return the corresponding ``cv2.aruco.CharucoBoard``."""
        aruco_dict = cv2.aruco.getPredefinedDictionary(self.aruco_dict_id)
        return cv2.aruco.CharucoBoard(
            (self.squares_x, self.squares_y),
            self.square_length_m,
            self.marker_length_m,
            aruco_dict,
        )


# ---------------------------------------------------------------------------
# Per-frame detection
# ---------------------------------------------------------------------------


def detect_charuco(
    frame_bgr: np.ndarray,
    board: cv2.aruco.CharucoBoard,
) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Detect ChArUco corners and IDs in a single frame.

    Uses the unified ``cv2.aruco.CharucoDetector`` API (OpenCV >= 4.7).

    Parameters
    ----------
    frame_bgr:
        ``H×W×3`` uint8 BGR image.
    board:
        The ``cv2.aruco.CharucoBoard`` to detect.

    Returns
    -------
    charuco_corners:
        ``(N, 1, 2)`` float32 array of detected corner pixel coordinates, or
        ``None`` if detection failed.
    charuco_ids:
        ``(N, 1)`` int32 array of corner IDs, or ``None`` if detection failed.
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    detector = cv2.aruco.CharucoDetector(board)
    charuco_corners, charuco_ids, _marker_corners, _marker_ids = detector.detectBoard(gray)
    if charuco_corners is None or charuco_ids is None or len(charuco_ids) < 4:
        return None, None
    return charuco_corners, charuco_ids


# ---------------------------------------------------------------------------
# Batch calibration
# ---------------------------------------------------------------------------


def calibrate_intrinsic(
    frames_bgr: list[np.ndarray],
    board: cv2.aruco.CharucoBoard,
    image_size: tuple[int, int],
) -> CameraIntrinsics:
    """Estimate camera intrinsics from a batch of ChArUco frames.

    Parameters
    ----------
    frames_bgr:
        List of ``H×W×3`` uint8 BGR images containing the ChArUco board.
    board:
        The ``cv2.aruco.CharucoBoard`` used during capture.
    image_size:
        ``(width, height)`` of the images in pixels.

    Returns
    -------
    CameraIntrinsics
        Calibrated intrinsic parameters. ``dist_coeffs`` has length 5.

    Raises
    ------
    ValueError
        If the total number of detected corners across all frames is below 50.
    """
    all_corners: list[np.ndarray] = []
    all_ids: list[np.ndarray] = []
    frames_with_corners = 0

    for frame in frames_bgr:
        corners, ids = detect_charuco(frame, board)
        if corners is not None and ids is not None:
            all_corners.append(corners)
            all_ids.append(ids)
            frames_with_corners += 1

    total_corners = sum(len(ids) for ids in all_ids)
    if total_corners < 50:
        raise ValueError(
            f"Insufficient corners — captured {len(frames_bgr)} frames, "
            f"{frames_with_corners} had corners, total {total_corners} >= 50 required"
        )

    # cv2.aruco.calibrateCameraCharuco signature:
    # (charucoCorners, charucoIds, board, imageSize, cameraMatrix, distCoeffs)
    # Returns: (ret, cameraMatrix, distCoeffs, rvecs, tvecs)
    w, h = image_size
    ret, camera_matrix, dist_coeffs, _rvecs, _tvecs = cv2.aruco.calibrateCameraCharuco(
        charucoCorners=all_corners,
        charucoIds=all_ids,
        board=board,
        imageSize=(w, h),
        cameraMatrix=None,
        distCoeffs=None,
    )

    if not math.isfinite(ret):
        raise ValueError(f"calibrateCameraCharuco returned non-finite RMS error: {ret}")

    fx = float(camera_matrix[0, 0])
    fy = float(camera_matrix[1, 1])
    cx = float(camera_matrix[0, 2])
    cy = float(camera_matrix[1, 2])
    dist = tuple(float(v) for v in dist_coeffs.flatten())

    return CameraIntrinsics(
        fx=fx,
        fy=fy,
        cx=cx,
        cy=cy,
        width=w,
        height=h,
        dist_coeffs=dist,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "CharucoBoardSpec",
    "calibrate_intrinsic",
    "detect_charuco",
]
