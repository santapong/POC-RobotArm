"""Tests for the motion :class:`Player` (:mod:`src.motion.player`).

These tests exercise the player against a ``MagicMock(spec=Driver)`` so
they're hermetic — no PyBullet, no real controller, no networking. The
spec ensures the mock only accepts the actual Driver Protocol surface,
catching API drift at test time.
"""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

from src.drivers.base import Driver
from src.motion import (
    IOKind,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    Program,
    Recorder,
    SpeedData,
    ToolData,
    Wait,
    WObjData,
    ZoneData,
    ZoneKind,
)
from src.motion.player import Player

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _identity_quat() -> tuple[float, float, float, float]:
    return (1.0, 0.0, 0.0, 0.0)


@pytest.fixture
def tool() -> ToolData:
    return ToolData("tool0", 0.5, (0.0, 0.0, 0.1), _identity_quat())


@pytest.fixture
def wobj() -> WObjData:
    return WObjData("wobj0", (0.0, 0.0, 0.0), _identity_quat())


@pytest.fixture
def speed() -> SpeedData:
    return SpeedData(100.0)


@pytest.fixture
def mock_driver() -> MagicMock:
    """A Driver-shaped mock that satisfies isinstance(..., Driver)."""
    drv = MagicMock(spec=Driver)
    drv.name = "mock:test"
    drv.dof = 6
    return drv


@pytest.fixture
def player(mock_driver: MagicMock) -> Player:
    return Player(mock_driver)


def _wrap(steps, name: str = "main") -> Program:
    """Wrap a list of ProcedureSteps in a single-procedure Program."""
    return Program(name="test_prog", procedures=(Procedure(name=name, body=tuple(steps)),))


# ---------------------------------------------------------------------------
# Move dispatch
# ---------------------------------------------------------------------------


def test_play_program_calls_move_joint_for_move_abs_j(
    player: Player, mock_driver: MagicMock, tool: ToolData, wobj: WObjData, speed: SpeedData
) -> None:
    q = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    move = Move(MoveKind.MOVE_ABS_J, JointTarget(q), speed, ZoneData.fine(), tool, wobj)

    player.play_program(_wrap([move]))

    mock_driver.move_joint.assert_called_once_with(q, wait=True)
    mock_driver.move_linear.assert_not_called()


def test_play_program_calls_move_linear_for_move_l(
    player: Player, mock_driver: MagicMock, tool: ToolData, wobj: WObjData, speed: SpeedData
) -> None:
    xyz = (0.5, 0.1, 0.4)
    quat = (1.0, 0.0, 0.0, 0.0)
    move = Move(MoveKind.MOVE_L, PoseTarget(xyz, quat), speed, ZoneData.fine(), tool, wobj)

    player.play_program(_wrap([move]))

    mock_driver.move_linear.assert_called_once_with(xyz, quat, wait=True)
    mock_driver.move_joint.assert_not_called()


def test_wait_each_false_propagates_to_driver(
    player: Player, mock_driver: MagicMock, tool: ToolData, wobj: WObjData, speed: SpeedData
) -> None:
    q = (0.0,) * 6
    xyz = (0.5, 0.1, 0.4)
    quat = (1.0, 0.0, 0.0, 0.0)
    moves = [
        Move(MoveKind.MOVE_ABS_J, JointTarget(q), speed, ZoneData.fine(), tool, wobj),
        Move(MoveKind.MOVE_L, PoseTarget(xyz, quat), speed, ZoneData.fine(), tool, wobj),
    ]

    player.play_program(_wrap(moves), wait_each=False)

    mock_driver.move_joint.assert_called_once_with(q, wait=False)
    mock_driver.move_linear.assert_called_once_with(xyz, quat, wait=False)


def test_move_c_falls_back_to_move_linear_with_warning(
    player: Player, mock_driver: MagicMock, tool: ToolData, wobj: WObjData, speed: SpeedData
) -> None:
    end = PoseTarget((0.6, 0.1, 0.4), _identity_quat())
    via = PoseTarget((0.55, 0.1, 0.45), _identity_quat())
    move_c = Move(
        MoveKind.MOVE_C, end, speed, ZoneData(ZoneKind.RADIUS, 5.0), tool, wobj, circ_via=via
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        player.play_program(_wrap([move_c]))

    # Falls back to move_linear with the *end* target, ignoring the via point.
    mock_driver.move_linear.assert_called_once_with(end.xyz_m, end.quat_wxyz, wait=True)
    # And we emitted a warning.
    assert any("MOVE_C" in str(w.message) for w in caught), (
        f"Expected a MOVE_C warning; got: {[str(w.message) for w in caught]}"
    )


# ---------------------------------------------------------------------------
# Procedure lookup
# ---------------------------------------------------------------------------


def test_unknown_procedure_name_raises_key_error(
    player: Player, tool: ToolData, wobj: WObjData, speed: SpeedData
) -> None:
    q = (0.0,) * 6
    move = Move(MoveKind.MOVE_ABS_J, JointTarget(q), speed, ZoneData.fine(), tool, wobj)
    prog = _wrap([move], name="main")

    with pytest.raises(KeyError, match="missing_procedure"):
        player.play_program(prog, procedure_name="missing_procedure")


def test_play_program_rejects_non_program_input(player: Player) -> None:
    with pytest.raises(TypeError, match="Program"):
        player.play_program("not a program")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# play_recording is a thin alias
# ---------------------------------------------------------------------------


def test_play_recording_is_alias_of_play_program(
    player: Player, mock_driver: MagicMock, tool: ToolData, wobj: WObjData
) -> None:
    rec = Recorder(default_tool=tool, default_wobj=wobj)
    rec.record_move_joint((0.1,) * 6)
    rec.record_move_linear((0.5, 0.1, 0.4), _identity_quat())

    player.play_recording(rec)

    # Same call pattern as if we had called play_program(rec.as_program()).
    mock_driver.move_joint.assert_called_once_with((0.1,) * 6, wait=True)
    mock_driver.move_linear.assert_called_once_with(
        (0.5, 0.1, 0.4), (1.0, 0.0, 0.0, 0.0), wait=True
    )


# ---------------------------------------------------------------------------
# Non-motion steps: IOOp, Wait, Comment
# ---------------------------------------------------------------------------


def test_io_op_warns_once_when_driver_lacks_set_io(
    player: Player, mock_driver: MagicMock
) -> None:
    """Without a ``set_io`` method, the player must warn exactly once per kind."""
    op1 = IOOp("do_grip", 1, IOKind.SET)
    op2 = IOOp("do_release", 0, IOKind.SET)
    prog = _wrap([op1, op2])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        player.play_program(prog)

    set_warnings = [w for w in caught if "IOOp:SET" in str(w.message)]
    assert len(set_warnings) == 1, (
        f"Expected one warning for IOOp:SET, got {len(set_warnings)}: "
        f"{[str(w.message) for w in caught]}"
    )
    # Driver motion methods untouched.
    mock_driver.move_joint.assert_not_called()
    mock_driver.move_linear.assert_not_called()


def test_wait_warns_once_when_driver_lacks_wait(
    player: Player, mock_driver: MagicMock
) -> None:
    prog = _wrap([Wait(seconds=0.1), Wait(seconds=0.2)])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        player.play_program(prog)

    seconds_warnings = [w for w in caught if "Wait:seconds" in str(w.message)]
    assert len(seconds_warnings) == 1


def test_comment_is_silently_ignored(
    player: Player, mock_driver: MagicMock, tool: ToolData, wobj: WObjData, speed: SpeedData
) -> None:
    from src.motion.ir import Comment

    move = Move(
        MoveKind.MOVE_ABS_J, JointTarget((0.0,) * 6), speed, ZoneData.fine(), tool, wobj
    )
    prog = _wrap([Comment("startup"), move, Comment("done")])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        player.play_program(prog)

    # No warnings for comments.
    assert not any("Comment" in str(w.message) for w in caught)
    mock_driver.move_joint.assert_called_once()
