"""Pydantic v2 adapters for motion IR domain objects.

Mirrors ``src.motion.ir`` dataclasses field-for-field. The Union discriminator
approach adds a ``kind`` literal field to ``JointTargetModel`` / ``PoseTargetModel``
so Pydantic can round-trip the polymorphic ``Move.target`` field.

Notes
-----
- IR dataclasses are oblivious to the ``kind`` discriminator; it is injected by
  ``from_domain`` and stripped by ``to_domain``.
- ``ZoneData.kind`` (a ``ZoneKind`` enum) is serialised as its string value.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from src.motion.ir import (
    Comment,
    ConfigData,
    IOKind,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    Program,
    SpeedData,
    ToolData,
    Wait,
    WObjData,
    ZoneData,
    ZoneKind,
)


class ToolDataModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.ToolData`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    mass_kg: float
    tcp_xyz_m: tuple[float, float, float]
    tcp_quat_wxyz: tuple[float, float, float, float]
    cog_xyz_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    robhold: bool = True

    @classmethod
    def from_domain(cls, obj: ToolData) -> "ToolDataModel":
        return cls(
            name=obj.name,
            mass_kg=obj.mass_kg,
            tcp_xyz_m=(obj.tcp_xyz_m[0], obj.tcp_xyz_m[1], obj.tcp_xyz_m[2]),
            tcp_quat_wxyz=(
                obj.tcp_quat_wxyz[0],
                obj.tcp_quat_wxyz[1],
                obj.tcp_quat_wxyz[2],
                obj.tcp_quat_wxyz[3],
            ),
            cog_xyz_m=(obj.cog_xyz_m[0], obj.cog_xyz_m[1], obj.cog_xyz_m[2]),
            robhold=obj.robhold,
        )

    def to_domain(self) -> ToolData:
        return ToolData(
            name=self.name,
            mass_kg=self.mass_kg,
            tcp_xyz_m=self.tcp_xyz_m,
            tcp_quat_wxyz=self.tcp_quat_wxyz,
            cog_xyz_m=self.cog_xyz_m,
            robhold=self.robhold,
        )


class WObjDataModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.WObjData`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    base_xyz_m: tuple[float, float, float]
    base_quat_wxyz: tuple[float, float, float, float]
    user_xyz_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    user_quat_wxyz: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    robhold: bool = False

    @classmethod
    def from_domain(cls, obj: WObjData) -> "WObjDataModel":
        return cls(
            name=obj.name,
            base_xyz_m=(obj.base_xyz_m[0], obj.base_xyz_m[1], obj.base_xyz_m[2]),
            base_quat_wxyz=(
                obj.base_quat_wxyz[0],
                obj.base_quat_wxyz[1],
                obj.base_quat_wxyz[2],
                obj.base_quat_wxyz[3],
            ),
            user_xyz_m=(obj.user_xyz_m[0], obj.user_xyz_m[1], obj.user_xyz_m[2]),
            user_quat_wxyz=(
                obj.user_quat_wxyz[0],
                obj.user_quat_wxyz[1],
                obj.user_quat_wxyz[2],
                obj.user_quat_wxyz[3],
            ),
            robhold=obj.robhold,
        )

    def to_domain(self) -> WObjData:
        return WObjData(
            name=self.name,
            base_xyz_m=self.base_xyz_m,
            base_quat_wxyz=self.base_quat_wxyz,
            user_xyz_m=self.user_xyz_m,
            user_quat_wxyz=self.user_quat_wxyz,
            robhold=self.robhold,
        )


class SpeedDataModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.SpeedData`."""

    model_config = ConfigDict(from_attributes=True)

    v_tcp_mm_s: float
    v_ori_deg_s: float = 500.0
    v_lin_ext_mm_s: float = 5000.0
    v_rot_ext_deg_s: float = 1000.0
    a_tcp_mm_s2: Optional[float] = None
    a_ori_deg_s2: Optional[float] = None

    @classmethod
    def from_domain(cls, obj: SpeedData) -> "SpeedDataModel":
        return cls(
            v_tcp_mm_s=obj.v_tcp_mm_s,
            v_ori_deg_s=obj.v_ori_deg_s,
            v_lin_ext_mm_s=obj.v_lin_ext_mm_s,
            v_rot_ext_deg_s=obj.v_rot_ext_deg_s,
            a_tcp_mm_s2=obj.a_tcp_mm_s2,
            a_ori_deg_s2=obj.a_ori_deg_s2,
        )

    def to_domain(self) -> SpeedData:
        return SpeedData(
            v_tcp_mm_s=self.v_tcp_mm_s,
            v_ori_deg_s=self.v_ori_deg_s,
            v_lin_ext_mm_s=self.v_lin_ext_mm_s,
            v_rot_ext_deg_s=self.v_rot_ext_deg_s,
            a_tcp_mm_s2=self.a_tcp_mm_s2,
            a_ori_deg_s2=self.a_ori_deg_s2,
        )


class ZoneDataModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.ZoneData`."""

    model_config = ConfigDict(from_attributes=True)

    kind: str  # serialised ZoneKind value: "FINE" or "RADIUS"
    radius_mm: float = 0.0

    @classmethod
    def from_domain(cls, obj: ZoneData) -> "ZoneDataModel":
        return cls(kind=obj.kind.value, radius_mm=obj.radius_mm)

    def to_domain(self) -> ZoneData:
        return ZoneData(kind=ZoneKind(self.kind), radius_mm=self.radius_mm)


class ConfigDataModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.ConfigData`."""

    model_config = ConfigDict(from_attributes=True)

    cf1: int
    cf4: int
    cf6: int
    cfx: int

    @classmethod
    def from_domain(cls, obj: ConfigData) -> "ConfigDataModel":
        return cls(cf1=obj.cf1, cf4=obj.cf4, cf6=obj.cf6, cfx=obj.cfx)

    def to_domain(self) -> ConfigData:
        return ConfigData(cf1=self.cf1, cf4=self.cf4, cf6=self.cf6, cfx=self.cfx)


class JointTargetModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.JointTarget`.

    The ``kind`` literal ``"joint"`` is the Pydantic discriminator key.
    """

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["joint"] = "joint"
    q_rad: tuple[float, ...]
    ext_axes_rad: tuple[float, ...] = ()

    @classmethod
    def from_domain(cls, obj: JointTarget) -> "JointTargetModel":
        return cls(kind="joint", q_rad=obj.q_rad, ext_axes_rad=obj.ext_axes_rad)

    def to_domain(self) -> JointTarget:
        return JointTarget(q_rad=self.q_rad, ext_axes_rad=self.ext_axes_rad)


class PoseTargetModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.PoseTarget`.

    The ``kind`` literal ``"pose"`` is the Pydantic discriminator key.
    """

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["pose"] = "pose"
    xyz_m: tuple[float, float, float]
    quat_wxyz: tuple[float, float, float, float]
    config: Optional[ConfigDataModel] = None
    ext_axes_rad: tuple[float, ...] = ()

    @classmethod
    def from_domain(cls, obj: PoseTarget) -> "PoseTargetModel":
        return cls(
            kind="pose",
            xyz_m=(obj.xyz_m[0], obj.xyz_m[1], obj.xyz_m[2]),
            quat_wxyz=(obj.quat_wxyz[0], obj.quat_wxyz[1], obj.quat_wxyz[2], obj.quat_wxyz[3]),
            config=ConfigDataModel.from_domain(obj.config) if obj.config else None,
            ext_axes_rad=obj.ext_axes_rad,
        )

    def to_domain(self) -> PoseTarget:
        return PoseTarget(
            xyz_m=self.xyz_m,
            quat_wxyz=self.quat_wxyz,
            config=self.config.to_domain() if self.config else None,
            ext_axes_rad=self.ext_axes_rad,
        )


TargetModel = Annotated[
    Union[JointTargetModel, PoseTargetModel],
    Field(discriminator="kind"),
]


class IOOpModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.IOOp`."""

    model_config = ConfigDict(from_attributes=True)

    signal: str
    value: Union[int, float]
    kind: str  # IOKind value

    @classmethod
    def from_domain(cls, obj: IOOp) -> "IOOpModel":
        return cls(signal=obj.signal, value=obj.value, kind=obj.kind.value)

    def to_domain(self) -> IOOp:
        return IOOp(signal=self.signal, value=self.value, kind=IOKind(self.kind))


class WaitModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.Wait`."""

    model_config = ConfigDict(from_attributes=True)

    seconds: Optional[float] = None
    signal: Optional[str] = None

    @classmethod
    def from_domain(cls, obj: Wait) -> "WaitModel":
        return cls(seconds=obj.seconds, signal=obj.signal)

    def to_domain(self) -> Wait:
        return Wait(seconds=self.seconds, signal=self.signal)


class CommentModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.Comment`."""

    model_config = ConfigDict(from_attributes=True)

    text: str

    @classmethod
    def from_domain(cls, obj: Comment) -> "CommentModel":
        return cls(text=obj.text)

    def to_domain(self) -> Comment:
        return Comment(text=self.text)


class MoveModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.Move`.

    The ``target`` field uses Pydantic's ``discriminator="kind"`` so JSON
    round-trips correctly between ``JointTargetModel`` and ``PoseTargetModel``.
    """

    model_config = ConfigDict(from_attributes=True)

    kind: str  # MoveKind value: "MOVE_J", "MOVE_L", "MOVE_C", "MOVE_ABS_J"
    target: TargetModel
    speed: SpeedDataModel
    zone: ZoneDataModel
    tool: ToolDataModel
    wobj: WObjDataModel
    circ_via: Optional[PoseTargetModel] = None

    @classmethod
    def from_domain(cls, obj: Move) -> "MoveModel":
        if isinstance(obj.target, JointTarget):
            target_model: TargetModel = JointTargetModel.from_domain(obj.target)
        else:
            target_model = PoseTargetModel.from_domain(obj.target)
        return cls(
            kind=obj.kind.value,
            target=target_model,
            speed=SpeedDataModel.from_domain(obj.speed),
            zone=ZoneDataModel.from_domain(obj.zone),
            tool=ToolDataModel.from_domain(obj.tool),
            wobj=WObjDataModel.from_domain(obj.wobj),
            circ_via=PoseTargetModel.from_domain(obj.circ_via) if obj.circ_via else None,
        )

    def to_domain(self) -> Move:
        target = self.target.to_domain()
        return Move(
            kind=MoveKind(self.kind),
            target=target,
            speed=self.speed.to_domain(),
            zone=self.zone.to_domain(),
            tool=self.tool.to_domain(),
            wobj=self.wobj.to_domain(),
            circ_via=self.circ_via.to_domain() if self.circ_via else None,
        )


# A step in a procedure body: Move, IOOp, Wait, or Comment.
ProcedureStepModel = Union[MoveModel, IOOpModel, WaitModel, CommentModel]


class ProcedureModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.Procedure`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    params: list[str] = []
    body: list[ProcedureStepModel] = []

    @classmethod
    def from_domain(cls, obj: Procedure) -> "ProcedureModel":
        body_models: list[ProcedureStepModel] = []
        for step in obj.body:
            if isinstance(step, Move):
                body_models.append(MoveModel.from_domain(step))
            elif isinstance(step, IOOp):
                body_models.append(IOOpModel.from_domain(step))
            elif isinstance(step, Wait):
                body_models.append(WaitModel.from_domain(step))
            elif isinstance(step, Comment):
                body_models.append(CommentModel.from_domain(step))
        return cls(name=obj.name, params=list(obj.params), body=body_models)


class ProgramModel(BaseModel):
    """Adapter for :class:`~src.motion.ir.Program`.

    Notes
    -----
    - ``from_domain`` / ``to_domain`` cover the full tree.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    modules_metadata: dict[str, str] = {}
    tools: list[ToolDataModel] = []
    wobjs: list[WObjDataModel] = []
    procedures: list[ProcedureModel] = []

    @classmethod
    def from_domain(cls, obj: Program) -> "ProgramModel":
        return cls(
            name=obj.name,
            modules_metadata=dict(obj.modules_metadata),
            tools=[ToolDataModel.from_domain(t) for t in obj.tools],
            wobjs=[WObjDataModel.from_domain(w) for w in obj.wobjs],
            procedures=[ProcedureModel.from_domain(p) for p in obj.procedures],
        )


__all__ = [
    "CommentModel",
    "ConfigDataModel",
    "IOOpModel",
    "JointTargetModel",
    "MoveModel",
    "PoseTargetModel",
    "ProcedureModel",
    "ProgramModel",
    "SpeedDataModel",
    "TargetModel",
    "ToolDataModel",
    "WObjDataModel",
    "WaitModel",
    "ZoneDataModel",
]
