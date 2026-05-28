"""Project / Job / Operation Pydantic models.

These mirror the TypeScript types in ``web-arc/src/types.ts`` exactly — same
field names, same JSON shape — so a project saved by the browser app can be
re-opened by the server and vice versa.

Python-side fields use ``snake_case`` for ergonomics; the wire format is
``camelCase`` via the alias generator and ``populate_by_name=True``, so
``model_dump(by_alias=True)`` produces JSON that round-trips with the TS app.
"""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


def _camel(s: str) -> str:
    head, *rest = s.split("_")
    return head + "".join(p.capitalize() for p in rest)


class _Camel(BaseModel):
    """Shared base: camelCase JSON, accept either name on parse."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=_camel,
    )


Vec3 = Tuple[float, float, float]
Severity = Literal["OK", "INFO", "WARN", "ERR", "DEBUG"]
MoveType = Literal["MoveJ", "MoveL", "MoveC", "MoveP"]
ToolType = Literal["GRIPPER_2F", "GRIPPER_3F", "SUCTION", "MIG", "SPINDLE", "DISPENSER"]
PartKind = Literal["BOX", "CYLINDER", "PLATE", "STEP"]
WeaveType = Literal["NONE", "ZIGZAG", "SINE", "TRIANGLE", "TRAPEZOID"]
OpKind = Literal["PICKPLACE", "WELD", "MILL", "DISPENSE"]
Strategy = Literal["POINTS", "CONTOUR", "RASTER", "SEAM"]


class Mount(_Camel):
    offset: Vec3 = (0.0, 0.0, 0.0)
    rpy: Vec3 = (0.0, 0.0, 0.0)


class ToolSize(_Camel):
    stroke: Optional[float] = None
    length: Optional[float] = None
    dia: Optional[float] = None
    width: Optional[float] = None


class ToolLead(_Camel):
    in_: float = Field(0.02, alias="in")
    out: float = 0.02


class Tool(_Camel):
    id: str
    name: str
    type: ToolType
    mount: Mount = Field(default_factory=Mount)
    tcp_offset: Vec3
    size: ToolSize = Field(default_factory=ToolSize)
    lead: ToolLead = Field(default_factory=ToolLead)


class Payload(_Camel):
    mass: float = 0.0
    com: Vec3 = (0.0, 0.0, 0.0)


class TcpFrame(_Camel):
    id: str
    name: str
    offset: Vec3
    rpy: Vec3
    payload: Payload = Field(default_factory=Payload)


class PartPose(_Camel):
    pos: Vec3 = (0.5, 0.0, 0.0)
    rpy: Vec3 = (0.0, 0.0, 0.0)


class Part(_Camel):
    id: str
    name: str
    kind: PartKind
    dims: dict[str, float]
    pose: PartPose = Field(default_factory=PartPose)


class Weave(_Camel):
    type: WeaveType = "NONE"
    amplitude: float = 0.004
    wavelength: float = 0.012
    edge_dwell: float = 0.05


class Pick(_Camel):
    point: Vec3
    normal: Vec3
    dwell: Optional[float] = None


class IoTrigger(_Camel):
    type: str
    ch: int
    value: bool
    label: str


class Waypoint(_Camel):
    id: int
    name: str
    type: MoveType
    tcp: Vec3
    rot: Vec3
    joints: List[float]
    vel: float
    acc: float
    blend: float = 0.0
    dwell: float = 0.0
    io: Optional[IoTrigger] = None
    t: float = 0.0
    op: Optional[str] = None


class OperationParams(_Camel):
    standoff: float = 5.0
    approach: float = 60.0
    vel: float = 30.0
    acc: float = 40.0
    weave: Weave = Field(default_factory=Weave)
    picks: List[Pick] = Field(default_factory=list)


class Operation(_Camel):
    id: int
    name: str
    enabled: bool = True
    kind: OpKind
    part_id: str
    tool_id: str
    tcp_id: str = "tcp-tip"
    strategy: Strategy = "POINTS"
    params: OperationParams = Field(default_factory=OperationParams)


class Job(_Camel):
    id: str = "0"
    name: str = "Untitled Program"
    author: str = "OP"
    active_tcp_id: str = "tcp-tip"
    post_format: str = "URScript"
    ops: List[Operation] = Field(default_factory=list)


class RobotLinks(_Camel):
    base_height: float = 0.26
    upper_arm: float = 0.42
    forearm: float = 0.34
    wrist_offset: float = 0.155
    flange_offset: float = 0.025


class RobotModel(_Camel):
    id: str
    name: str
    manufacturer: str
    family: str
    dof: int = 6
    payload: float
    reach: float
    links: RobotLinks = Field(default_factory=RobotLinks)
    joint_limits: List[Tuple[float, float]] = Field(default_factory=list)
    max_joint_vel: List[float] = Field(default_factory=list)
    max_tcp_speed: float = 1.0
    accent: str = "#4ade80"


class DocMeta(_Camel):
    name: str
    author: str = "OP"
    modified: str = ""


class Doc(_Camel):
    version: int = 2
    meta: DocMeta
    job: Job
    active_tcp_id: str = "tcp-tip"
    # Optional RobotModel id this project was authored for. Missing on a v1
    # doc → resolves to the default (ur5e) at read time.
    robot_id: Optional[str] = None


class Trajectory(_Camel):
    id: str
    name: str
    author: str
    tool: str = ""
    payload: float = 0.0
    total_time: float = 0.0
    path_length: float = 0.0
    max_tcp_speed: float = 0.0
    max_joint_vel: float = 0.0
    max_joint_acc: float = 0.0
    singularity_warnings: int = 0
    collision_warnings: int = 0
    reach_warnings: int = 0
    waypoints: List[Waypoint] = Field(default_factory=list)


__all__ = [
    "Vec3", "Severity", "MoveType", "ToolType", "PartKind", "WeaveType", "OpKind", "Strategy",
    "Mount", "ToolSize", "ToolLead", "Tool", "Payload", "TcpFrame",
    "PartPose", "Part", "Weave", "Pick", "IoTrigger", "Waypoint",
    "OperationParams", "Operation", "Job", "DocMeta", "Doc", "Trajectory",
]
