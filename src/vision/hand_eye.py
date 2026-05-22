"""Hand-eye calibration solver.

Wraps ``cv2.calibrateHandEye`` with a clean Python interface that handles:

- Mount-aware data preparation: for ``eye_to_hand``, the gripper-to-base poses
  are inverted (to base-to-gripper) before passing them to OpenCV, which
  internally models the eye-in-hand geometry.
- A human-readable method selector via a ``Literal`` string.
- Output packaged as a :class:`~src.vision.types.CameraExtrinsics`.

Notes
-----
- Requires ``opencv-contrib-python >= 4.10`` (``[vision]`` extra).
- At least 3 pose pairs are required; fewer gives a degenerate system.
- Input rotation matrices may be passed as ``(3, 3)`` numpy arrays or
  pre-built lists of such arrays.  Translation vectors must be ``(3,)``
  1-D arrays or ``(3, 1)`` column vectors.
"""

from __future__ import annotations

from typing import Literal, Sequence

import cv2
import numpy as np

from src.vision.types import CameraExtrinsics

# ---------------------------------------------------------------------------
# Method map
# ---------------------------------------------------------------------------

HandEyeMethod = Literal["tsai", "park", "horaud", "andreff", "daniilidis"]

_METHOD_MAP: dict[str, int] = {
    "tsai": cv2.CALIB_HAND_EYE_TSAI,
    "park": cv2.CALIB_HAND_EYE_PARK,
    "horaud": cv2.CALIB_HAND_EYE_HORAUD,
    "andreff": cv2.CALIB_HAND_EYE_ANDREFF,
    "daniilidis": cv2.CALIB_HAND_EYE_DANIILIDIS,
}


# ---------------------------------------------------------------------------
# solve_hand_eye
# ---------------------------------------------------------------------------


def solve_hand_eye(
    R_gripper2base: Sequence[np.ndarray],
    t_gripper2base: Sequence[np.ndarray],
    R_target2cam: Sequence[np.ndarray],
    t_target2cam: Sequence[np.ndarray],
    method: HandEyeMethod = "park",
    mount: Literal["eye_to_hand", "eye_in_hand"] = "eye_to_hand",
    reference_frame: str = "base",
) -> CameraExtrinsics:
    """Solve the hand-eye calibration problem.

    For ``eye_to_hand`` (camera fixed, target on gripper): each
    ``(R_gripper2base[i], t_gripper2base[i])`` pair is inverted to
    ``(R_base2gripper[i], t_base2gripper[i])`` before being passed to
    ``cv2.calibrateHandEye``, which internally solves the eye-in-hand
    equation ``AX = XB``.  The returned ``R, t`` then represent the camera
    pose in the base frame.

    For ``eye_in_hand`` (camera on gripper): the poses are passed unchanged
    and the returned ``R, t`` represent the camera pose relative to the gripper
    (tool-centre-point frame).

    Parameters
    ----------
    R_gripper2base:
        Sequence of ``(3, 3)`` rotation matrices (gripper → base).
    t_gripper2base:
        Sequence of ``(3,)`` or ``(3, 1)`` translation vectors in metres.
    R_target2cam:
        Sequence of ``(3, 3)`` rotation matrices (calibration target → camera).
    t_target2cam:
        Sequence of ``(3,)`` or ``(3, 1)`` translation vectors in metres.
    method:
        One of ``"tsai"``, ``"park"``, ``"horaud"``, ``"andreff"``,
        ``"daniilidis"``. Default is ``"park"``.
    mount:
        ``"eye_to_hand"`` (camera fixed, default) or ``"eye_in_hand"``
        (camera on gripper).
    reference_frame:
        Name of the reference frame stored in the returned extrinsics.
        Pass ``"world"`` when the robot base coincides with the world origin.

    Returns
    -------
    CameraExtrinsics
        Calibrated camera pose with ``mount`` and ``reference_frame`` recorded.

    Raises
    ------
    ValueError
        If list lengths are mismatched or fewer than 3 pose pairs are supplied.
    KeyError
        If ``method`` is not in the recognised method map.
    """
    n = len(R_gripper2base)
    if n != len(t_gripper2base) or n != len(R_target2cam) or n != len(t_target2cam):
        raise ValueError(
            "R_gripper2base, t_gripper2base, R_target2cam, and t_target2cam "
            "must all have the same length"
        )
    if n < 3:
        raise ValueError(
            f"solve_hand_eye requires at least 3 pose pairs, got {n}"
        )
    if method not in _METHOD_MAP:
        raise ValueError(
            f"Unknown hand-eye method {method!r}; choose from {list(_METHOD_MAP)}"
        )

    cv_method = _METHOD_MAP[method]

    # Normalise translations to column vectors expected by OpenCV.
    def _col(t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=np.float64)
        return t.reshape(3, 1)

    R_g2b = [np.asarray(R, dtype=np.float64) for R in R_gripper2base]
    t_g2b = [_col(t) for t in t_gripper2base]
    R_t2c = [np.asarray(R, dtype=np.float64) for R in R_target2cam]
    t_t2c = [_col(t) for t in t_target2cam]

    if mount == "eye_to_hand":
        # Invert each gripper-to-base pose to get base-to-gripper.
        R_in = [R.T for R in R_g2b]
        t_in = [(-R.T @ t) for R, t in zip(R_g2b, t_g2b)]
    else:
        R_in = R_g2b
        t_in = t_g2b

    R_out, t_out = cv2.calibrateHandEye(
        R_in, t_in, R_t2c, t_t2c, method=cv_method
    )

    R_tuple = tuple(tuple(float(v) for v in row) for row in R_out)
    t_tuple = (float(t_out[0, 0]), float(t_out[1, 0]), float(t_out[2, 0]))

    return CameraExtrinsics(
        R_cam_in_world=R_tuple,
        t_cam_in_world=t_tuple,
        reference_frame=reference_frame,
        mount=mount,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "HandEyeMethod",
    "solve_hand_eye",
]
