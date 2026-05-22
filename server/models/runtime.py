"""Pydantic v2 models for runtime / operational requests and responses."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from server.models.station import FixtureEntryModel


class JogRequest(BaseModel):
    """Body for ``POST /api/station/robots/{id}/jog``.

    Exactly one of ``(joint_index + value_rad)`` or ``values_rad`` must be set.
    """

    model_config = ConfigDict(from_attributes=True)

    joint_index: Optional[int] = None
    value_rad: Optional[float] = None
    values_rad: Optional[list[float]] = None

    @model_validator(mode="after")
    def _validate_exclusive(self) -> "JogRequest":
        single = self.joint_index is not None and self.value_rad is not None
        multi = self.values_rad is not None
        if single == multi:  # both true or both false
            raise ValueError(
                "JogRequest: provide either (joint_index + value_rad) or values_rad, not both/neither"
            )
        return self


class RobotStateResponse(BaseModel):
    """Live snapshot of a robot's joint state returned from state/jog endpoints."""

    model_config = ConfigDict(from_attributes=True)

    catalog_name: str
    dof: int
    joints_rad: list[float]
    tcp_xyz_m: tuple[float, float, float]
    tcp_quat_wxyz: tuple[float, float, float, float]
    moving: bool
    error: Optional[str] = None


class PostRequest(BaseModel):
    """Body for ``POST /api/programs/{id}/post``."""

    model_config = ConfigDict(from_attributes=True)

    vendor: Literal["rapid", "krl", "urscript"]


class PostResponse(BaseModel):
    """Response body for the post-processor endpoint."""

    model_config = ConfigDict(from_attributes=True)

    vendor: str
    source: str
    file_extension: str


class RunStart(BaseModel):
    """Body for ``POST /api/programs/{id}/run``."""

    model_config = ConfigDict(from_attributes=True)

    procedure_name: str = "main"
    dt_s: float = 0.01


class RunRecord(BaseModel):
    """Persistent record of a program run."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str
    program_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: float
    finished_at: Optional[float] = None
    violation_count: int = 0
    error: Optional[str] = None


class AssetImportResponse(BaseModel):
    """Response body for ``POST /api/assets/import``."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    kind: Literal["mesh", "dxf"]
    filename: str
    summary: str
    saved_path: str = ""
    station_entity: Optional[FixtureEntryModel] = None


__all__ = [
    "AssetImportResponse",
    "JogRequest",
    "PostRequest",
    "PostResponse",
    "RobotStateResponse",
    "RunRecord",
    "RunStart",
]
