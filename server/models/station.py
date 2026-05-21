"""Pydantic v2 adapters for station scene-graph domain objects.

Mirrors ``src.station.scene`` dataclasses field-for-field. The ``from_domain``
classmethods convert from frozen dataclasses; ``to_domain`` builds the domain
objects back. Validation stays in the domain layer — these models do only
JSON shape work.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from src.station.scene import (
    FixtureEntry,
    Frame,
    IOSignal,
    RobotEntry,
    Station,
    ToolEntry,
    WorkpieceEntry,
)


class FrameModel(BaseModel):
    """Pydantic adapter for :class:`~src.station.scene.Frame`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    xyz_m: tuple[float, float, float]
    quat_wxyz: tuple[float, float, float, float]
    parent: Optional[str] = None

    @classmethod
    def from_domain(cls, obj: Frame) -> "FrameModel":
        return cls(
            name=obj.name,
            xyz_m=(obj.xyz_m[0], obj.xyz_m[1], obj.xyz_m[2]),
            quat_wxyz=(obj.quat_wxyz[0], obj.quat_wxyz[1], obj.quat_wxyz[2], obj.quat_wxyz[3]),
            parent=obj.parent,
        )

    def to_domain(self) -> Frame:
        return Frame(
            name=self.name,
            xyz_m=self.xyz_m,
            quat_wxyz=self.quat_wxyz,
            parent=self.parent,
        )


class RobotEntryModel(BaseModel):
    """Pydantic adapter for :class:`~src.station.scene.RobotEntry`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    robot_catalog_name: str
    base_frame: str

    @classmethod
    def from_domain(cls, obj: RobotEntry) -> "RobotEntryModel":
        return cls(name=obj.name, robot_catalog_name=obj.robot_catalog_name, base_frame=obj.base_frame)

    def to_domain(self) -> RobotEntry:
        return RobotEntry(name=self.name, robot_catalog_name=self.robot_catalog_name, base_frame=self.base_frame)


class ToolEntryModel(BaseModel):
    """Pydantic adapter for :class:`~src.station.scene.ToolEntry`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    parent_frame: str
    mesh_path: Optional[str] = None
    tcp_xyz_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    tcp_quat_wxyz: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)

    @classmethod
    def from_domain(cls, obj: ToolEntry) -> "ToolEntryModel":
        return cls(
            name=obj.name,
            parent_frame=obj.parent_frame,
            mesh_path=obj.mesh_path,
            tcp_xyz_m=(obj.tcp_xyz_m[0], obj.tcp_xyz_m[1], obj.tcp_xyz_m[2]),
            tcp_quat_wxyz=(
                obj.tcp_quat_wxyz[0],
                obj.tcp_quat_wxyz[1],
                obj.tcp_quat_wxyz[2],
                obj.tcp_quat_wxyz[3],
            ),
        )

    def to_domain(self) -> ToolEntry:
        return ToolEntry(
            name=self.name,
            parent_frame=self.parent_frame,
            mesh_path=self.mesh_path,
            tcp_xyz_m=self.tcp_xyz_m,
            tcp_quat_wxyz=self.tcp_quat_wxyz,
        )


class WorkpieceEntryModel(BaseModel):
    """Pydantic adapter for :class:`~src.station.scene.WorkpieceEntry`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    parent_frame: str
    mesh_path: Optional[str] = None

    @classmethod
    def from_domain(cls, obj: WorkpieceEntry) -> "WorkpieceEntryModel":
        return cls(name=obj.name, parent_frame=obj.parent_frame, mesh_path=obj.mesh_path)

    def to_domain(self) -> WorkpieceEntry:
        return WorkpieceEntry(name=self.name, parent_frame=self.parent_frame, mesh_path=self.mesh_path)


class FixtureEntryModel(BaseModel):
    """Pydantic adapter for :class:`~src.station.scene.FixtureEntry`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    parent_frame: str
    mesh_path: Optional[str] = None

    @classmethod
    def from_domain(cls, obj: FixtureEntry) -> "FixtureEntryModel":
        return cls(name=obj.name, parent_frame=obj.parent_frame, mesh_path=obj.mesh_path)

    def to_domain(self) -> FixtureEntry:
        return FixtureEntry(name=self.name, parent_frame=self.parent_frame, mesh_path=self.mesh_path)


class IOSignalModel(BaseModel):
    """Pydantic adapter for :class:`~src.station.scene.IOSignal`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: Literal["DI", "DO", "AI", "AO"]
    default_value: int | float | bool = 0

    @classmethod
    def from_domain(cls, obj: IOSignal) -> "IOSignalModel":
        return cls(name=obj.name, kind=obj.kind, default_value=obj.default_value)

    def to_domain(self) -> IOSignal:
        return IOSignal(name=self.name, kind=self.kind, default_value=self.default_value)


class StationModel(BaseModel):
    """Pydantic adapter for a full :class:`~src.station.scene.Station`.

    Notes
    -----
    - ``from_domain`` converts every collection from frozen tuples.
    - ``to_domain`` reconstructs the domain object; validation runs in ``Station.__post_init__``.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    frames: list[FrameModel] = []
    robots: list[RobotEntryModel] = []
    tools: list[ToolEntryModel] = []
    workpieces: list[WorkpieceEntryModel] = []
    fixtures: list[FixtureEntryModel] = []
    io_signals: list[IOSignalModel] = []

    @classmethod
    def from_domain(cls, station: Station) -> "StationModel":
        return cls(
            name=station.name,
            frames=[FrameModel.from_domain(f) for f in station.frames],
            robots=[RobotEntryModel.from_domain(r) for r in station.robots],
            tools=[ToolEntryModel.from_domain(t) for t in station.tools],
            workpieces=[WorkpieceEntryModel.from_domain(w) for w in station.workpieces],
            fixtures=[FixtureEntryModel.from_domain(f) for f in station.fixtures],
            io_signals=[IOSignalModel.from_domain(s) for s in station.io_signals],
        )

    def to_domain(self) -> Station:
        return Station(
            name=self.name,
            frames=tuple(f.to_domain() for f in self.frames),
            robots=tuple(r.to_domain() for r in self.robots),
            tools=tuple(t.to_domain() for t in self.tools),
            workpieces=tuple(w.to_domain() for w in self.workpieces),
            fixtures=tuple(f.to_domain() for f in self.fixtures),
            io_signals=tuple(s.to_domain() for s in self.io_signals),
        )


__all__ = [
    "FixtureEntryModel",
    "FrameModel",
    "IOSignalModel",
    "RobotEntryModel",
    "StationModel",
    "ToolEntryModel",
    "WorkpieceEntryModel",
]
