"""Pydantic v2 models for the POC-RobotArm FastAPI server.

Re-exports every model so callers can do::

    from server.models import StationModel, RobotCatalogEntry, ...
"""

from __future__ import annotations

from server.models.catalog import RobotCatalogEntry
from server.models.errors import ErrorResponse
from server.models.motion import (
    MoveModel,
    ProcedureModel,
    ProgramModel,
    SpeedDataModel,
    ToolDataModel,
    WObjDataModel,
    ZoneDataModel,
)
from server.models.runtime import (
    AssetImportResponse,
    JogRequest,
    PostRequest,
    PostResponse,
    RobotStateResponse,
    RunRecord,
    RunStart,
)
from server.models.station import (
    FixtureEntryModel,
    FrameModel,
    IOSignalModel,
    RobotEntryModel,
    StationModel,
    ToolEntryModel,
    WorkpieceEntryModel,
)
from server.models.vision import (
    CameraExtrinsicsModel,
    CameraIntrinsicsModel,
    CameraSpec,
    CameraStatus,
    CharucoPoseRequest,
    DetectionModel,
    DetectorSpec,
    DetectorStatus,
    GraspPoseModel,
    GraspPreviewRequest,
    GraspPreviewResponse,
    HandEyeRequest,
    LiveDetectionFrame,
    PosePairModel,
    RunDetectionRequest,
    RunDetectionResponse,
)

__all__ = [
    "AssetImportResponse",
    "CameraExtrinsicsModel",
    "CameraIntrinsicsModel",
    "CameraSpec",
    "CameraStatus",
    "CharucoPoseRequest",
    "DetectionModel",
    "DetectorSpec",
    "DetectorStatus",
    "ErrorResponse",
    "FixtureEntryModel",
    "FrameModel",
    "GraspPoseModel",
    "GraspPreviewRequest",
    "GraspPreviewResponse",
    "HandEyeRequest",
    "IOSignalModel",
    "JogRequest",
    "LiveDetectionFrame",
    "MoveModel",
    "PostRequest",
    "PostResponse",
    "PosePairModel",
    "ProcedureModel",
    "ProgramModel",
    "RobotCatalogEntry",
    "RobotEntryModel",
    "RobotStateResponse",
    "RunDetectionRequest",
    "RunDetectionResponse",
    "RunRecord",
    "RunStart",
    "SpeedDataModel",
    "StationModel",
    "ToolDataModel",
    "ToolEntryModel",
    "WObjDataModel",
    "WorkpieceEntryModel",
    "ZoneDataModel",
]
