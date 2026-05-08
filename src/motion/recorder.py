"""In-memory motion recorder that builds a vendor-neutral :class:`Program`.

The :class:`Recorder` is the write-side companion to :mod:`src.motion.ir`.
Call sites stream high-level events (joint moves, linear moves, I/O,
waits, comments) into a single recorder instance and at the end ask for
an immutable :class:`Program` that can be:

* persisted via :func:`src.motion.ir.dump`,
* replayed via :class:`src.motion.player.Player`, or
* fed into a vendor post-processor (e.g. ``RAPIDPost``).

Design notes
------------
* All recorded steps are :pep:`557` ``frozen=True`` dataclasses, so the
  recorder never mutates an IR instance after appending it. Defaults
  (tool, workobject, speed, zone) are stored on the recorder itself and
  copied (by value, since they are also frozen and hashable) into each
  :class:`Move` at append-time.
* :meth:`set_speed` / :meth:`set_zone` modify the *future* defaults only
  — anything already in the log is untouched, matching the way teach
  pendants update modal speed/zone for subsequent moves.
* The internal log is a plain ``list`` for ergonomic ``append`` /
  ``len`` semantics. :meth:`as_program` materialises a fresh tuple-backed
  :class:`Procedure` so the returned :class:`Program` is fully immutable.
"""

from __future__ import annotations

from typing import Sequence

from src.motion.ir import (
    Comment,
    IOKind,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    ProcedureStep,
    Program,
    SpeedData,
    ToolData,
    Wait,
    WObjData,
    ZoneData,
)


class Recorder:
    """Append-only log that builds a :class:`Program` from streamed events.

    Parameters
    ----------
    default_tool:
        Tool data attached to every recorded :class:`Move`.
    default_wobj:
        Workobject data attached to every recorded :class:`Move`.
    default_speed:
        Speed profile applied to subsequent moves until :meth:`set_speed`
        changes it. Defaults to ``SpeedData(100.0)``.
    default_zone:
        Blend zone applied to subsequent moves until :meth:`set_zone`
        changes it. Defaults to ``ZoneData.fine()``.
    """

    def __init__(
        self,
        default_tool: ToolData,
        default_wobj: WObjData,
        default_speed: SpeedData = SpeedData(100.0),
        default_zone: ZoneData = ZoneData.fine(),
    ) -> None:
        if not isinstance(default_tool, ToolData):
            raise TypeError(
                f"default_tool must be ToolData, got {type(default_tool).__name__}"
            )
        if not isinstance(default_wobj, WObjData):
            raise TypeError(
                f"default_wobj must be WObjData, got {type(default_wobj).__name__}"
            )
        if not isinstance(default_speed, SpeedData):
            raise TypeError(
                f"default_speed must be SpeedData, got {type(default_speed).__name__}"
            )
        if not isinstance(default_zone, ZoneData):
            raise TypeError(
                f"default_zone must be ZoneData, got {type(default_zone).__name__}"
            )

        self._tool: ToolData = default_tool
        self._wobj: WObjData = default_wobj
        self._speed: SpeedData = default_speed
        self._zone: ZoneData = default_zone
        self._log: list[ProcedureStep] = []

    # ------------------------------------------------------------- defaults

    def set_speed(self, speed: SpeedData) -> None:
        """Update the speed default for subsequent moves only."""
        if not isinstance(speed, SpeedData):
            raise TypeError(f"speed must be SpeedData, got {type(speed).__name__}")
        self._speed = speed

    def set_zone(self, zone: ZoneData) -> None:
        """Update the blend-zone default for subsequent moves only."""
        if not isinstance(zone, ZoneData):
            raise TypeError(f"zone must be ZoneData, got {type(zone).__name__}")
        self._zone = zone

    # ------------------------------------------------------------- accessors

    @property
    def default_tool(self) -> ToolData:
        return self._tool

    @property
    def default_wobj(self) -> WObjData:
        return self._wobj

    @property
    def default_speed(self) -> SpeedData:
        return self._speed

    @property
    def default_zone(self) -> ZoneData:
        return self._zone

    def __len__(self) -> int:
        return len(self._log)

    @property
    def log(self) -> tuple[ProcedureStep, ...]:
        """Read-only view of the steps recorded so far (in insertion order)."""
        return tuple(self._log)

    # --------------------------------------------------------------- record

    def record_move_joint(self, q_rad: Sequence[float]) -> Move:
        """Append a ``MOVE_ABS_J`` to the log targeting the given joint angles.

        ``q_rad`` is the joint vector in radians (length must equal the
        robot's DOF). The recorded move uses the recorder's current tool,
        wobj, speed and zone defaults.
        """
        target = JointTarget(q_rad=tuple(float(q) for q in q_rad))
        move = Move(
            kind=MoveKind.MOVE_ABS_J,
            target=target,
            speed=self._speed,
            zone=self._zone,
            tool=self._tool,
            wobj=self._wobj,
        )
        self._log.append(move)
        return move

    def record_move_linear(
        self,
        xyz_m: Sequence[float],
        quat_wxyz: Sequence[float],
    ) -> Move:
        """Append a ``MOVE_L`` to the log targeting the given Cartesian pose.

        ``xyz_m`` is the position in metres, ``quat_wxyz`` is a unit
        quaternion in ``(w, x, y, z)`` order. The recorded move uses the
        recorder's current tool, wobj, speed and zone defaults.
        """
        target = PoseTarget(
            xyz_m=tuple(float(c) for c in xyz_m),
            quat_wxyz=tuple(float(c) for c in quat_wxyz),
        )
        move = Move(
            kind=MoveKind.MOVE_L,
            target=target,
            speed=self._speed,
            zone=self._zone,
            tool=self._tool,
            wobj=self._wobj,
        )
        self._log.append(move)
        return move

    def record_io(self, signal: str, value: int, kind: IOKind = IOKind.SET) -> IOOp:
        """Append a digital-I/O operation to the log."""
        op = IOOp(signal=signal, value=value, kind=kind)
        self._log.append(op)
        return op

    def record_wait(self, seconds: float) -> Wait:
        """Append a time-based wait (in seconds) to the log."""
        wait = Wait(seconds=float(seconds))
        self._log.append(wait)
        return wait

    def record_comment(self, text: str) -> Comment:
        """Append a free-form comment to the log."""
        comment = Comment(text=text)
        self._log.append(comment)
        return comment

    # ------------------------------------------------------- materialisation

    def as_program(self, name: str = "recording") -> Program:
        """Wrap the recorded log into a single-procedure :class:`Program`.

        The returned :class:`Program` has one :class:`Procedure` named
        ``"main"`` whose body is the recorded steps in insertion order. The
        recorder's default tool and wobj are exported as the program-level
        ``tools`` / ``wobjs`` collections so post-processors can declare
        them in the generated source.
        """
        procedure = Procedure(name="main", body=tuple(self._log))
        return Program(
            name=name,
            tools=(self._tool,),
            wobjs=(self._wobj,),
            procedures=(procedure,),
        )

    def clear(self) -> None:
        """Reset the log; defaults (tool, wobj, speed, zone) are preserved."""
        self._log.clear()


__all__ = ["Recorder"]
