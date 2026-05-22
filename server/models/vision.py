"""Pydantic v2 models for the vision pipeline REST API.

Covers camera registration, detection results, calibration requests, grasp poses,
and live WebSocket frames.

Notes
-----
- ``from_domain`` / ``to_domain`` bridge the Pydantic layer to the library domain objects
  in ``src.vision.types``.
- ``CameraSpec.source`` accepts ``int`` for real cameras and ``str`` for paths/URLs.
- ``HandEyeRequest`` validates N >= 3 pose pairs via a model-level validator.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.vision.types import (
    CameraExtrinsics,
    CameraIntrinsics,
    Detection,
    GraspPose,
)

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


class CameraSpec(BaseModel):
    """Body for ``POST /api/vision/cameras``."""

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["real", "fake"]
    source: int | str
    name: str
    width: int = 640
    height: int = 480
    fake_image_paths: list[str] = []
    fps: float = 15.0

    @model_validator(mode="after")
    def _validate_source(self) -> "CameraSpec":
        if self.kind == "real" and not isinstance(self.source, int):
            raise ValueError("CameraSpec: real camera source must be an integer device index")
        return self


class CameraStatus(BaseModel):
    """Status of a registered camera."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: str
    width: int
    height: int
    has_intrinsics: bool
    has_extrinsics: bool
    live_detector: Optional[str] = None


# ---------------------------------------------------------------------------
# Intrinsics / extrinsics
# ---------------------------------------------------------------------------


class CameraIntrinsicsModel(BaseModel):
    """Pydantic adapter for :class:`~src.vision.types.CameraIntrinsics`."""

    model_config = ConfigDict(from_attributes=True)

    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    dist_coeffs: list[float]

    @classmethod
    def from_domain(cls, obj: CameraIntrinsics) -> "CameraIntrinsicsModel":
        return cls(
            fx=obj.fx,
            fy=obj.fy,
            cx=obj.cx,
            cy=obj.cy,
            width=obj.width,
            height=obj.height,
            dist_coeffs=list(obj.dist_coeffs),
        )

    def to_domain(self) -> CameraIntrinsics:
        return CameraIntrinsics(
            fx=self.fx,
            fy=self.fy,
            cx=self.cx,
            cy=self.cy,
            width=self.width,
            height=self.height,
            dist_coeffs=tuple(self.dist_coeffs),
        )


class CameraExtrinsicsModel(BaseModel):
    """Pydantic adapter for :class:`~src.vision.types.CameraExtrinsics`."""

    model_config = ConfigDict(from_attributes=True)

    # 3x3 rotation matrix as nested list
    R_cam_in_world: list[list[float]]
    t_cam_in_world: list[float]
    reference_frame: str = "world"
    mount: Literal["eye_to_hand", "eye_in_hand"] = "eye_to_hand"

    @classmethod
    def from_domain(cls, obj: CameraExtrinsics) -> "CameraExtrinsicsModel":
        return cls(
            R_cam_in_world=[list(row) for row in obj.R_cam_in_world],
            t_cam_in_world=list(obj.t_cam_in_world),
            reference_frame=obj.reference_frame,
            mount=obj.mount,
        )

    def to_domain(self) -> CameraExtrinsics:
        return CameraExtrinsics(
            R_cam_in_world=tuple(tuple(float(v) for v in row) for row in self.R_cam_in_world),
            t_cam_in_world=(
                float(self.t_cam_in_world[0]),
                float(self.t_cam_in_world[1]),
                float(self.t_cam_in_world[2]),
            ),
            reference_frame=self.reference_frame,
            mount=self.mount,
        )


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


class DetectorSpec(BaseModel):
    """Body for ``POST /api/vision/detectors``."""

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["yolo", "color"]
    name: str
    config: dict = {}


class DetectorStatus(BaseModel):
    """Status of a registered detector."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: str
    config: dict
    live_cameras: list[str] = []


# ---------------------------------------------------------------------------
# Detection + GraspPose
# ---------------------------------------------------------------------------


class GraspPoseModel(BaseModel):
    """Pydantic adapter for :class:`~src.vision.types.GraspPose`."""

    model_config = ConfigDict(from_attributes=True)

    xyz_m: list[float]
    quat_wxyz: list[float]
    frame: str
    approach_vector: list[float] = [0.0, 0.0, -1.0]

    @classmethod
    def from_domain(cls, obj: GraspPose) -> "GraspPoseModel":
        return cls(
            xyz_m=list(obj.xyz_m),
            quat_wxyz=list(obj.quat_wxyz),
            frame=obj.frame,
            approach_vector=list(obj.approach_vector),
        )

    def to_domain(self) -> GraspPose:
        return GraspPose(
            xyz_m=(float(self.xyz_m[0]), float(self.xyz_m[1]), float(self.xyz_m[2])),
            quat_wxyz=(
                float(self.quat_wxyz[0]),
                float(self.quat_wxyz[1]),
                float(self.quat_wxyz[2]),
                float(self.quat_wxyz[3]),
            ),
            frame=self.frame,
            approach_vector=(
                float(self.approach_vector[0]),
                float(self.approach_vector[1]),
                float(self.approach_vector[2]),
            ),
        )


class DetectionModel(BaseModel):
    """Pydantic adapter for :class:`~src.vision.types.Detection`."""

    model_config = ConfigDict(from_attributes=True)

    class_name: str
    confidence: float
    bbox_xyxy: list[float]
    mask: Optional[list[list[int]]] = None
    pose_in_camera: Optional[GraspPoseModel] = None
    pose_in_world: Optional[GraspPoseModel] = None

    @classmethod
    def from_domain(cls, obj: Detection) -> "DetectionModel":
        return cls(
            class_name=obj.class_name,
            confidence=obj.confidence,
            bbox_xyxy=list(obj.bbox_xyxy),
            mask=[list(row) for row in obj.mask] if obj.mask is not None else None,
            pose_in_camera=(
                GraspPoseModel.from_domain(obj.pose_in_camera)
                if obj.pose_in_camera is not None
                else None
            ),
            pose_in_world=(
                GraspPoseModel.from_domain(obj.pose_in_world)
                if obj.pose_in_world is not None
                else None
            ),
        )


# ---------------------------------------------------------------------------
# Hand-eye calibration
# ---------------------------------------------------------------------------


class PosePairModel(BaseModel):
    """One (gripper, target) pose pair for hand-eye calibration."""

    model_config = ConfigDict(from_attributes=True)

    # 3x3 rotation matrices as nested lists; 3-element translation vectors
    R_gripper2base: list[list[float]]
    t_gripper2base: list[float]
    R_target2cam: list[list[float]]
    t_target2cam: list[float]


class HandEyeRequest(BaseModel):
    """Body for ``POST /api/vision/cameras/{name}/calibrate/hand-eye``."""

    model_config = ConfigDict(from_attributes=True)

    pose_pairs: list[PosePairModel]
    method: str = "park"
    mount: Literal["eye_to_hand", "eye_in_hand"] = "eye_to_hand"
    reference_frame: str = "world"

    @field_validator("pose_pairs")
    @classmethod
    def _at_least_three(cls, v: list[PosePairModel]) -> list[PosePairModel]:
        if len(v) < 3:
            raise ValueError("HandEyeRequest: at least 3 pose pairs are required")
        return v


# ---------------------------------------------------------------------------
# Detection run
# ---------------------------------------------------------------------------


class RunDetectionRequest(BaseModel):
    """Body for ``POST /api/vision/detectors/{name}/run``."""

    model_config = ConfigDict(from_attributes=True)

    camera: str
    return_grasp: bool = False
    plane_z_m: float = 0.0


class RunDetectionResponse(BaseModel):
    """Response for one-shot detection."""

    model_config = ConfigDict(from_attributes=True)

    camera: str
    detector: str
    detections: list[DetectionModel]
    grasps: list[GraspPoseModel] = []
    monotonic_s: float


# ---------------------------------------------------------------------------
# Live detection WebSocket frame
# ---------------------------------------------------------------------------


class LiveDetectionFrame(BaseModel):
    """Server-push frame over ``/ws/vision/detections``."""

    model_config = ConfigDict(from_attributes=True)

    camera: str
    detector: str
    detections: list[DetectionModel]
    grasps: list[GraspPoseModel] = []
    monotonic_s: float


# ---------------------------------------------------------------------------
# ChArUco pose (JSON body — replaces the old Form() parameters)
# ---------------------------------------------------------------------------


class CharucoPoseRequest(BaseModel):
    """Body for ``POST /api/vision/cameras/{name}/charuco_pose``.

    ``aruco_dict_id`` maps to a ``cv2.aruco`` dict constant; the default ``0``
    corresponds to ``cv2.aruco.DICT_4X4_50``, resolved lazily by the router so
    this model need not import cv2.
    """

    model_config = ConfigDict(from_attributes=True)

    squares_x: int = 5
    squares_y: int = 7
    square_length_m: float = 0.04
    marker_length_m: float = 0.03
    aruco_dict_id: int = 0  # cv2.aruco.DICT_4X4_50


# ---------------------------------------------------------------------------
# Grasp preview (Open Question 2)
# ---------------------------------------------------------------------------


class GraspPreviewRequest(BaseModel):
    """Body for ``POST /api/vision/grasp_preview``."""

    model_config = ConfigDict(from_attributes=True)

    robot_id: str
    grasp: GraspPoseModel
    preview_mode: Literal["jog", "ik_only"] = "ik_only"


class GraspPreviewResponse(BaseModel):
    """Response for ``POST /api/vision/grasp_preview``."""

    model_config = ConfigDict(from_attributes=True)

    joints_rad: list[float]
    reachable: bool
    ik_residual_m: float
    applied: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "CameraExtrinsicsModel",
    "CameraIntrinsicsModel",
    "CameraSpec",
    "CameraStatus",
    "CharucoPoseRequest",
    "DetectionModel",
    "DetectorSpec",
    "DetectorStatus",
    "GraspPoseModel",
    "GraspPreviewRequest",
    "GraspPreviewResponse",
    "HandEyeRequest",
    "LiveDetectionFrame",
    "PosePairModel",
    "RunDetectionRequest",
    "RunDetectionResponse",
]
