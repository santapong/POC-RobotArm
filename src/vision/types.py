"""Vision pipeline data types.

Frozen dataclasses representing camera calibration results, object detections,
and grasp poses. Designed to be importable without any heavy dependencies
(cv2, numpy); only the standard library is required.

Notes
-----
- All JSON I/O uses a ``__type__`` discriminator so that ``from_dict`` is fully
  self-describing and can reject mismatched types.
- Quaternion convention is ``(w, x, y, z)`` throughout.
- ``dist_coeffs`` follows OpenCV conventions; valid lengths are 4, 5, 8, or 14.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Tolerances
# ---------------------------------------------------------------------------

_QUAT_NORM_TOL: float = 1e-6
_UNIT_VEC_TOL: float = 1e-6
_VALID_DIST_LENGTHS: frozenset[int] = frozenset((4, 5, 8, 14))


# ---------------------------------------------------------------------------
# Helpers (module-private, not re-exported)
# ---------------------------------------------------------------------------


def _check_quat_norm(q: tuple[float, float, float, float], name: str) -> None:
    norm = math.sqrt(sum(c * c for c in q))
    if abs(norm - 1.0) > _QUAT_NORM_TOL:
        raise ValueError(f"{name} must be unit-norm within {_QUAT_NORM_TOL}; |q|={norm:.9f}")


def _check_unit_vec(v: tuple[float, float, float], name: str) -> None:
    norm = math.sqrt(sum(c * c for c in v))
    if abs(norm - 1.0) > _UNIT_VEC_TOL:
        raise ValueError(f"{name} must be unit-norm within {_UNIT_VEC_TOL}; |v|={norm:.9f}")


# ---------------------------------------------------------------------------
# CameraIntrinsics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CameraIntrinsics:
    """Pinhole camera intrinsic parameters.

    All fields follow the OpenCV convention. ``dist_coeffs`` must have length
    4, 5, 8, or 14 (the four supported OpenCV distortion models).

    Example
    -------
    >>> ci = CameraIntrinsics(fx=600.0, fy=600.0, cx=320.0, cy=240.0,
    ...                       width=640, height=480, dist_coeffs=(0,)*5)
    >>> ci.K()
    [[600.0, 0.0, 320.0], [0.0, 600.0, 240.0], [0.0, 0.0, 1.0]]
    """

    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    dist_coeffs: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.dist_coeffs) not in _VALID_DIST_LENGTHS:
            raise ValueError(
                f"CameraIntrinsics.dist_coeffs must have length in "
                f"{sorted(_VALID_DIST_LENGTHS)}, got {len(self.dist_coeffs)}"
            )

    def K(self) -> list[list[float]]:
        """Return the 3×3 camera matrix as a nested list."""
        return [
            [self.fx, 0.0, self.cx],
            [0.0, self.fy, self.cy],
            [0.0, 0.0, 1.0],
        ]

    def K_np(self):  # type: ignore[return]
        """Return the 3×3 camera matrix as a numpy float64 array.

        The numpy import is deferred so ``types.py`` itself remains numpy-free.
        """
        import numpy as np  # local import — keeps types.py stdlib-only

        return np.array(self.K(), dtype=np.float64)

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict with a ``__type__`` discriminator."""
        return {
            "__type__": "CameraIntrinsics",
            "fx": self.fx,
            "fy": self.fy,
            "cx": self.cx,
            "cy": self.cy,
            "width": self.width,
            "height": self.height,
            "dist_coeffs": list(self.dist_coeffs),
        }

    @classmethod
    def from_dict(cls, d: dict) -> CameraIntrinsics:
        """Reconstruct from a dict previously produced by ``to_dict``."""
        t = d.get("__type__")
        if t != "CameraIntrinsics":
            raise ValueError(f"Expected __type__ 'CameraIntrinsics', got {t!r}")
        return cls(
            fx=float(d["fx"]),
            fy=float(d["fy"]),
            cx=float(d["cx"]),
            cy=float(d["cy"]),
            width=int(d["width"]),
            height=int(d["height"]),
            dist_coeffs=tuple(float(v) for v in d["dist_coeffs"]),
        )


# ---------------------------------------------------------------------------
# CameraExtrinsics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CameraExtrinsics:
    """Camera pose in a reference frame produced by hand-eye calibration.

    ``R_cam_in_world`` is a 3×3 rotation matrix (row-major, as nested tuples).
    ``t_cam_in_world`` is the camera origin in metres expressed in
    ``reference_frame`` coordinates.
    """

    R_cam_in_world: tuple[tuple[float, ...], ...]
    t_cam_in_world: tuple[float, float, float]
    reference_frame: str = "world"
    mount: Literal["eye_to_hand", "eye_in_hand"] = "eye_to_hand"

    def __post_init__(self) -> None:
        if len(self.R_cam_in_world) != 3 or any(len(row) != 3 for row in self.R_cam_in_world):
            raise ValueError("CameraExtrinsics.R_cam_in_world must be a 3×3 matrix")
        if len(self.t_cam_in_world) != 3:
            raise ValueError("CameraExtrinsics.t_cam_in_world must have length 3")
        if self.mount not in ("eye_to_hand", "eye_in_hand"):
            raise ValueError(
                f"CameraExtrinsics.mount must be 'eye_to_hand' or 'eye_in_hand', "
                f"got {self.mount!r}"
            )

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict with a ``__type__`` discriminator."""
        return {
            "__type__": "CameraExtrinsics",
            "R_cam_in_world": [list(row) for row in self.R_cam_in_world],
            "t_cam_in_world": list(self.t_cam_in_world),
            "reference_frame": self.reference_frame,
            "mount": self.mount,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CameraExtrinsics:
        """Reconstruct from a dict previously produced by ``to_dict``."""
        t = d.get("__type__")
        if t != "CameraExtrinsics":
            raise ValueError(f"Expected __type__ 'CameraExtrinsics', got {t!r}")
        return cls(
            R_cam_in_world=tuple(tuple(float(v) for v in row) for row in d["R_cam_in_world"]),
            t_cam_in_world=tuple(float(v) for v in d["t_cam_in_world"]),  # type: ignore[arg-type]
            reference_frame=str(d.get("reference_frame", "world")),
            mount=str(d.get("mount", "eye_to_hand")),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# GraspPose
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraspPose:
    """6-DoF grasp pose in a named reference frame.

    ``quat_wxyz`` must be unit-norm. ``approach_vector`` must be unit-norm;
    defaults to ``(0.0, 0.0, -1.0)`` (downward approach).
    """

    xyz_m: tuple[float, float, float]
    quat_wxyz: tuple[float, float, float, float]
    frame: str
    approach_vector: tuple[float, float, float] = (0.0, 0.0, -1.0)

    def __post_init__(self) -> None:
        if len(self.xyz_m) != 3:
            raise ValueError("GraspPose.xyz_m must have length 3")
        if len(self.quat_wxyz) != 4:
            raise ValueError("GraspPose.quat_wxyz must have 4 components (w,x,y,z)")
        _check_quat_norm(self.quat_wxyz, "GraspPose.quat_wxyz")
        if len(self.approach_vector) != 3:
            raise ValueError("GraspPose.approach_vector must have length 3")
        _check_unit_vec(self.approach_vector, "GraspPose.approach_vector")

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict with a ``__type__`` discriminator."""
        return {
            "__type__": "GraspPose",
            "xyz_m": list(self.xyz_m),
            "quat_wxyz": list(self.quat_wxyz),
            "frame": self.frame,
            "approach_vector": list(self.approach_vector),
        }

    @classmethod
    def from_dict(cls, d: dict) -> GraspPose:
        """Reconstruct from a dict previously produced by ``to_dict``."""
        t = d.get("__type__")
        if t != "GraspPose":
            raise ValueError(f"Expected __type__ 'GraspPose', got {t!r}")
        return cls(
            xyz_m=tuple(float(v) for v in d["xyz_m"]),  # type: ignore[arg-type]
            quat_wxyz=tuple(float(v) for v in d["quat_wxyz"]),  # type: ignore[arg-type]
            frame=str(d["frame"]),
            approach_vector=tuple(float(v) for v in d.get("approach_vector", [0, 0, -1])),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Detection:
    """Single object detection result.

    ``confidence`` must be in ``[0, 1]``. ``bbox_xyxy`` must satisfy
    ``x2 > x1`` and ``y2 > y1``. ``mask`` and ``pose_*`` are optional;
    ``mask`` is always ``None`` in Phase 2.
    """

    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    mask: Optional[tuple[tuple[int, ...], ...]] = None
    pose_in_camera: Optional[GraspPose] = None
    pose_in_world: Optional[GraspPose] = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"Detection.confidence must be in [0, 1], got {self.confidence}"
            )
        if len(self.bbox_xyxy) != 4:
            raise ValueError("Detection.bbox_xyxy must have 4 elements (x1, y1, x2, y2)")
        x1, y1, x2, y2 = self.bbox_xyxy
        if x2 <= x1:
            raise ValueError(
                f"Detection.bbox_xyxy requires x2 > x1, got x1={x1}, x2={x2}"
            )
        if y2 <= y1:
            raise ValueError(
                f"Detection.bbox_xyxy requires y2 > y1, got y1={y1}, y2={y2}"
            )

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict with a ``__type__`` discriminator."""
        return {
            "__type__": "Detection",
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox_xyxy": list(self.bbox_xyxy),
            "mask": (
                [list(row) for row in self.mask] if self.mask is not None else None
            ),
            "pose_in_camera": (
                self.pose_in_camera.to_dict() if self.pose_in_camera is not None else None
            ),
            "pose_in_world": (
                self.pose_in_world.to_dict() if self.pose_in_world is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Detection:
        """Reconstruct from a dict previously produced by ``to_dict``."""
        t = d.get("__type__")
        if t != "Detection":
            raise ValueError(f"Expected __type__ 'Detection', got {t!r}")
        mask_raw = d.get("mask")
        mask = tuple(tuple(int(v) for v in row) for row in mask_raw) if mask_raw is not None else None
        pic_raw = d.get("pose_in_camera")
        piw_raw = d.get("pose_in_world")
        return cls(
            class_name=str(d["class_name"]),
            confidence=float(d["confidence"]),
            bbox_xyxy=tuple(float(v) for v in d["bbox_xyxy"]),  # type: ignore[arg-type]
            mask=mask,
            pose_in_camera=GraspPose.from_dict(pic_raw) if pic_raw is not None else None,
            pose_in_world=GraspPose.from_dict(piw_raw) if piw_raw is not None else None,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "CameraExtrinsics",
    "CameraIntrinsics",
    "Detection",
    "GraspPose",
]
