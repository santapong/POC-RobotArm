"""Replay a vendor-neutral :class:`Program` through a :class:`Driver`.

The :class:`Player` is the read-side companion to :class:`Recorder`:
given any :class:`Driver` (sim or real hardware), it walks the steps
of a :class:`Procedure` and dispatches them to the corresponding driver
method. Sim drivers ignore non-motion steps such as :class:`IOOp` and
:class:`Wait` since those only have meaning on a real controller; the
player emits a one-shot :func:`warnings.warn` for each unsupported op
kind so the omission is visible without flooding the log.

Design notes
------------
* The player depends only on the :class:`Driver` Protocol — no concrete
  backend is imported. This keeps the module trivially testable with a
  ``MagicMock(spec=Driver)`` and lets it work transparently against the
  real ABB / future drivers.
* The mapping between :class:`MoveKind` and driver methods is intentionally
  conservative:

  - ``MOVE_ABS_J`` -> ``driver.move_joint``
  - ``MOVE_J`` (pose target) / ``MOVE_L`` (pose target) -> ``driver.move_linear``
  - ``MOVE_J`` (joint target) -> ``driver.move_joint``
  - ``MOVE_C`` -> ``driver.move_linear`` with a one-shot warning, since
    the sim driver does not implement true circular interpolation.
* The ``wait_each`` flag is propagated verbatim to ``driver.move_*``;
  callers that want fire-and-forget behaviour pass ``wait_each=False``.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from src.motion.ir import (
    Comment,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Program,
    Wait,
)

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from src.drivers.base import Driver
    from src.motion.recorder import Recorder


class Player:
    """Walk a :class:`Program` and dispatch each step to a :class:`Driver`."""

    def __init__(self, driver: "Driver") -> None:
        self._driver = driver
        # Track which unsupported op kinds we've already warned about so a
        # long program doesn't generate one warning per IOOp.
        self._warned_kinds: set[str] = set()

    @property
    def driver(self) -> "Driver":
        return self._driver

    # ------------------------------------------------------------- playback

    def play_program(
        self,
        program: Program,
        procedure_name: str = "main",
        wait_each: bool = True,
    ) -> None:
        """Replay the named procedure of ``program`` through the driver.

        Parameters
        ----------
        program:
            The :class:`Program` to play back.
        procedure_name:
            Name of the procedure inside ``program`` to execute. Defaults
            to ``"main"``. Raises :class:`KeyError` if no procedure with
            that name exists.
        wait_each:
            If ``True`` (default) each :class:`Move` blocks until the
            driver reports completion. If ``False`` the moves are fired
            in sequence without waiting; the underlying driver is
            responsible for queueing.
        """
        if not isinstance(program, Program):
            raise TypeError(f"program must be a Program, got {type(program).__name__}")

        procedure = self._find_procedure(program, procedure_name)
        for step in procedure.body:
            self._dispatch(step, wait_each=wait_each)

    def play_recording(self, recorder: "Recorder", wait_each: bool = True) -> None:
        """Convenience: materialise ``recorder`` into a :class:`Program` and play it."""
        program = recorder.as_program()
        self.play_program(program, procedure_name="main", wait_each=wait_each)

    # ------------------------------------------------------------- internals

    @staticmethod
    def _find_procedure(program: Program, name: str):
        """Return the procedure named ``name`` or raise :class:`KeyError`."""
        for proc in program.procedures:
            if proc.name == name:
                return proc
        raise KeyError(
            f"Program {program.name!r} has no procedure named {name!r}; "
            f"available: {[p.name for p in program.procedures]}"
        )

    def _dispatch(self, step, *, wait_each: bool) -> None:
        """Dispatch a single :class:`ProcedureStep` to the driver."""
        if isinstance(step, Move):
            self._dispatch_move(step, wait_each=wait_each)
        elif isinstance(step, IOOp):
            self._dispatch_io(step)
        elif isinstance(step, Wait):
            self._dispatch_wait(step)
        elif isinstance(step, Comment):
            # Comments are echoed by post-processors but have no runtime effect.
            return
        else:  # pragma: no cover - defensive: should never happen
            raise TypeError(f"Unknown procedure step: {type(step).__name__}")

    def _dispatch_move(self, move: Move, *, wait_each: bool) -> None:
        kind = move.kind
        target = move.target

        if kind == MoveKind.MOVE_ABS_J:
            assert isinstance(target, JointTarget)  # enforced by Move.__post_init__
            self._driver.move_joint(target.q_rad, wait=wait_each)
            return

        if kind == MoveKind.MOVE_J:
            # MOVE_J accepts both joint and pose targets (see Move.__post_init__).
            if isinstance(target, JointTarget):
                self._driver.move_joint(target.q_rad, wait=wait_each)
            else:
                assert isinstance(target, PoseTarget)
                self._driver.move_linear(
                    target.xyz_m, target.quat_wxyz, wait=wait_each
                )
            return

        if kind == MoveKind.MOVE_L:
            assert isinstance(target, PoseTarget)
            self._driver.move_linear(target.xyz_m, target.quat_wxyz, wait=wait_each)
            return

        if kind == MoveKind.MOVE_C:
            assert isinstance(target, PoseTarget)
            warnings.warn(
                "Player: MOVE_C is not natively supported by the sim driver; "
                "falling back to a linear move to the end target. The via point "
                "is ignored in this slice.",
                stacklevel=3,
            )
            self._driver.move_linear(target.xyz_m, target.quat_wxyz, wait=wait_each)
            return

        # Should be unreachable thanks to MoveKind being closed.
        raise ValueError(f"Unhandled MoveKind: {kind!r}")  # pragma: no cover

    def _dispatch_io(self, op: IOOp) -> None:
        """Dispatch I/O to the driver if it supports it; warn once otherwise."""
        # Real drivers (e.g. ABB) may grow a ``set_io`` method; the sim
        # driver doesn't have one today.
        set_io = getattr(self._driver, "set_io", None)
        if callable(set_io):
            set_io(op.signal, op.value, op.kind)
            return
        self._warn_unsupported(f"IOOp:{op.kind.value}")

    def _dispatch_wait(self, wait: Wait) -> None:
        """Dispatch a wait to the driver if it supports it; warn once otherwise."""
        wait_fn = getattr(self._driver, "wait", None)
        if callable(wait_fn):
            wait_fn(seconds=wait.seconds, signal=wait.signal)
            return
        # The "kind" we deduplicate on distinguishes time vs signal waits so
        # both make it into the user's logs in mixed programs.
        kind = "Wait:seconds" if wait.seconds is not None else "Wait:signal"
        self._warn_unsupported(kind)

    def _warn_unsupported(self, op_kind: str) -> None:
        """Emit a single :func:`warnings.warn` per distinct ``op_kind``."""
        if op_kind in self._warned_kinds:
            return
        self._warned_kinds.add(op_kind)
        warnings.warn(
            f"Player: driver {getattr(self._driver, 'name', type(self._driver).__name__)!r} "
            f"does not support {op_kind}; the step will be skipped. "
            f"Subsequent {op_kind} steps in this program will be silently skipped.",
            stacklevel=3,
        )


__all__ = ["Player"]
