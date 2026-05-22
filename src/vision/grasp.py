"""Grasp pose estimation from 2-D detections.

Provides :func:`pixel_to_world`, which back-projects a bounding-box centroid
through the pinhole camera model onto a horizontal world-frame plane
(``z = plane_z_m``) and builds a :class:`~src.vision.types.GraspPose`.

Notes
-----
- Requires ``opencv-contrib-python >= 4.10`` (``[vision]`` extra).
- The orientation quaternion encodes:
  1. A rotation that aligns the TCP +z axis with *approach_axis*.
  2. A rotation around the world z-axis by the bounding-box long-axis angle
     (degrees, from ``cv2.minAreaRect``).  Falls back to ``(1,0,0,0)`` when
     the bbox is square (side difference ≤ 1 pixel).
- All arithmetic is in metres; the caller is responsible for ensuring that
  ``extrinsics.t_cam_in_world`` is expressed in the same units.
"""

from __future__ import annotations

import math
from typing import Literal

import cv2
import numpy as np

from src.vision.types import CameraExtrinsics, CameraIntrinsics, Detection, GraspPose

# Threshold below which the ray is considered parallel to the ground plane.
_RAY_PARALLEL_TOL: float = 1e-6


def _rotation_matrix_to_quat(R: np.ndarray) -> tuple[float, float, float, float]:
    """Convert a 3×3 rotation matrix to a unit quaternion ``(w, x, y, z)``."""
    trace = float(R[0, 0] + R[1, 1] + R[2, 2])
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = float(R[2, 1] - R[1, 2]) * s
        y = float(R[0, 2] - R[2, 0]) * s
        z = float(R[1, 0] - R[0, 1]) * s
    elif float(R[0, 0]) > float(R[1, 1]) and float(R[0, 0]) > float(R[2, 2]):
        s = 2.0 * math.sqrt(1.0 + float(R[0, 0]) - float(R[1, 1]) - float(R[2, 2]))
        w = float(R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = float(R[0, 1] + R[1, 0]) / s
        z = float(R[0, 2] + R[2, 0]) / s
    elif float(R[1, 1]) > float(R[2, 2]):
        s = 2.0 * math.sqrt(1.0 + float(R[1, 1]) - float(R[0, 0]) - float(R[2, 2]))
        w = float(R[0, 2] - R[2, 0]) / s
        x = float(R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = float(R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + float(R[2, 2]) - float(R[0, 0]) - float(R[1, 1]))
        w = float(R[1, 0] - R[0, 1]) / s
        x = float(R[0, 2] + R[2, 0]) / s
        y = float(R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    # Normalise to guard against floating-point drift.
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    return (w / norm, x / norm, y / norm, z / norm)


def _quat_multiply(
    q1: tuple[float, float, float, float],
    q2: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Hamilton product of two ``(w, x, y, z)`` quaternions."""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def _approach_quat(approach_axis: Literal["-z", "+z"]) -> tuple[float, float, float, float]:
    """Return the quaternion that rotates world +z to point along *approach_axis*.

    - ``"-z"``: 180° rotation around world x-axis → TCP +z points down.
    - ``"+z"``: identity → TCP +z points up.
    """
    if approach_axis == "+z":
        return (1.0, 0.0, 0.0, 0.0)
    # 180° around x: (w=0, x=1, y=0, z=0)
    return (0.0, 1.0, 0.0, 0.0)


def _yaw_quat(angle_deg: float) -> tuple[float, float, float, float]:
    """Return a quaternion for a rotation of *angle_deg* around world z."""
    half = math.radians(angle_deg) * 0.5
    return (math.cos(half), 0.0, 0.0, math.sin(half))


def pixel_to_world(
    detection: Detection,
    intrinsics: CameraIntrinsics,
    extrinsics: CameraExtrinsics,
    plane_z_m: float = 0.0,
    approach_axis: Literal["-z", "+z"] = "-z",
) -> GraspPose:
    """Back-project a 2-D detection to a world-frame :class:`GraspPose`.

    Algorithm
    ---------
    1. Compute centroid ``(u_px, v_px) = ((x1+x2)/2, (y1+y2)/2)``.
    2. Undistort the centroid via ``cv2.undistortPoints`` using ``intrinsics.K``
       and ``dist_coeffs``, yielding normalised image coordinates ``(u, v)``
       such that the ray direction in the camera frame is ``[u, v, 1]``.
    3. Transform the ray origin ``(0,0,0)_cam`` and direction ``[u,v,1]`` into
       the world frame using ``R_cam_in_world`` and ``t_cam_in_world``.
    4. Intersect the world-frame ray with the plane ``z = plane_z_m``.
       Raises ``ValueError`` if ``|d_z| < 1e-6`` (ray nearly parallel to plane).
    5. Compute orientation:
       - Get the long-axis angle from ``cv2.minAreaRect`` on the bbox corners.
       - If the bbox is square (within 1 px), the yaw component is identity.
       - Build ``q = q_approach ⊗ q_yaw``.

    Parameters
    ----------
    detection:
        The 2-D detection; ``bbox_xyxy`` must be set.
    intrinsics:
        Calibrated camera intrinsics.
    extrinsics:
        Camera pose in the world frame.
    plane_z_m:
        Height of the ground plane in the world frame (metres). Default 0.
    approach_axis:
        ``"-z"`` (TCP approaches from above, default) or ``"+z"`` (upward).

    Returns
    -------
    GraspPose
        Grasp pose in ``extrinsics.reference_frame``.

    Raises
    ------
    ValueError
        If the camera ray is nearly parallel to the ground plane.
    """
    x1, y1, x2, y2 = detection.bbox_xyxy

    # Step 1 — centroid.
    u_px = (x1 + x2) * 0.5
    v_px = (y1 + y2) * 0.5

    # Step 2 — undistort to normalised image coords.
    K = intrinsics.K_np()
    dist = np.array(intrinsics.dist_coeffs, dtype=np.float64)
    pt = np.array([[[u_px, v_px]]], dtype=np.float32)
    normalised = cv2.undistortPoints(pt, K, dist)
    u_n = float(normalised[0, 0, 0])
    v_n = float(normalised[0, 0, 1])
    # Ray direction in camera frame.
    d_cam = np.array([u_n, v_n, 1.0], dtype=np.float64)

    # Step 3 — transform into world frame.
    R = np.array(extrinsics.R_cam_in_world, dtype=np.float64)
    t = np.array(extrinsics.t_cam_in_world, dtype=np.float64)
    # Ray origin in world = t (camera origin in world).
    o_world = t
    # Ray direction in world = R @ d_cam.
    d_world = R @ d_cam

    # Step 4 — intersect with z = plane_z_m.
    d_z = float(d_world[2])
    if abs(d_z) < _RAY_PARALLEL_TOL:
        raise ValueError("Camera ray nearly parallel to ground plane")
    t_param = (plane_z_m - float(o_world[2])) / d_z
    hit = o_world + t_param * d_world
    xyz = (float(hit[0]), float(hit[1]), float(hit[2]))

    # Step 5 — orientation.
    q_approach = _approach_quat(approach_axis)
    approach_vec = (0.0, 0.0, -1.0) if approach_axis == "-z" else (0.0, 0.0, 1.0)

    bbox_w = x2 - x1
    bbox_h = y2 - y1
    square = abs(bbox_w - bbox_h) <= 1.0

    if square:
        q_yaw = (1.0, 0.0, 0.0, 0.0)
    else:
        # minAreaRect returns angle in degrees (OpenCV 4.5+: [−90, 0)).
        corners = np.array(
            [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32
        )
        _, _, angle_deg = cv2.minAreaRect(corners)
        q_yaw = _yaw_quat(angle_deg)

    quat = _quat_multiply(q_approach, q_yaw)

    return GraspPose(
        xyz_m=xyz,
        quat_wxyz=quat,
        frame=extrinsics.reference_frame,
        approach_vector=approach_vec,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "pixel_to_world",
]
