"""Tests for the vendor-neutral robot driver layer.

These tests exercise :class:`src.drivers.SimDriver` against a mocked
:class:`SimBridge` so they never spin up PyBullet. The bridge surface is
small and well-defined (``submit``, ``snapshot``, ``cancel_trajectory``)
which makes mocking straightforward and keeps the tests fast.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest

from src.drivers import Driver, RobotState, SimDriver

# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------


class _FakeSim:
    """Minimal stand-in for :class:`RobotArmSim` used by ``submit`` callables."""

    def __init__(self, num_joints: int = 6) -> None:
        self.num_joints = num_joints
        self.reset_calls: list[list[float]] = []
        self.target_calls: list[list[float]] = []
        self.ik_calls: list[tuple[list[float], object]] = []
        self.last_ik_solution: list[float] = [0.0] * num_joints

    def reset_joint_angles(self, angles):
        self.reset_calls.append(list(angles))

    def set_joint_targets(self, angles, force: float = 200.0):
        self.target_calls.append(list(angles))

    def solve_ik(self, position, orientation=None, **_):
        self.ik_calls.append((list(position), orientation))
        return list(self.last_ik_solution)


def _make_bridge(snapshot: dict | None = None, sim: _FakeSim | None = None) -> MagicMock:
    """Build a MagicMock SimBridge with a configurable snapshot and submit()."""
    bridge = MagicMock(name="SimBridge")
    sim = sim or _FakeSim()

    bridge.snapshot.return_value = snapshot or {
        "connected": True,
        "num_joints": sim.num_joints,
        "joint_angles": [0.0] * sim.num_joints,
        "ee_position": [0.1, 0.2, 0.3],
        "ee_orientation": [0.0, 0.0, 0.0, 1.0],  # xyzw
        "trajectory": {"active": False},
    }

    def _submit(fn, timeout: float = 5.0):
        return fn(sim)

    bridge.submit.side_effect = _submit
    bridge._fake_sim = sim  # surfaced for assertion convenience
    return bridge


@pytest.fixture
def fake_bridge() -> MagicMock:
    return _make_bridge()


@pytest.fixture
def driver(fake_bridge: MagicMock) -> SimDriver:
    return SimDriver(fake_bridge, robot_name="panda", dof=fake_bridge._fake_sim.num_joints)


# ---------------------------------------------------------------------------
# RobotState
# ---------------------------------------------------------------------------


def test_robot_state_round_trip_and_immutability():
    state = RobotState(
        joints_rad=(0.1, 0.2, 0.3),
        tcp_xyz_m=(0.4, 0.5, 0.6),
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        moving=False,
        error=None,
    )

    # Round-trip via dataclasses.asdict (proves the dataclass is consistent).
    payload = dataclasses.asdict(state)
    assert payload["joints_rad"] == (0.1, 0.2, 0.3)
    assert payload["tcp_xyz_m"] == (0.4, 0.5, 0.6)
    assert payload["tcp_quat_wxyz"] == (1.0, 0.0, 0.0, 0.0)
    assert payload["moving"] is False
    assert payload["error"] is None

    # Frozen dataclass: assignment must fail.
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.moving = True  # type: ignore[misc]

    # Default value for ``error``.
    minimal = RobotState(
        joints_rad=(),
        tcp_xyz_m=(0.0, 0.0, 0.0),
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        moving=False,
    )
    assert minimal.error is None


# ---------------------------------------------------------------------------
# Driver Protocol structural conformance
# ---------------------------------------------------------------------------


def test_sim_driver_satisfies_driver_protocol(driver: SimDriver):
    # ``runtime_checkable`` Protocols permit isinstance() checks.
    assert isinstance(driver, Driver)


def test_sim_driver_exposes_required_attributes(driver: SimDriver):
    assert driver.name == "sim:panda"
    assert driver.dof == 6
    # Every method named in the Protocol must be callable on the instance.
    for method in (
        "connect",
        "disconnect",
        "is_connected",
        "get_state",
        "move_joint",
        "move_linear",
        "run_program",
        "stop",
    ):
        assert callable(getattr(driver, method)), method


# ---------------------------------------------------------------------------
# SimDriver behaviour
# ---------------------------------------------------------------------------


def test_connect_disconnect_toggles_is_connected(driver: SimDriver):
    assert driver.is_connected() is False
    driver.connect()
    assert driver.is_connected() is True
    driver.disconnect()
    assert driver.is_connected() is False
    # Idempotent.
    driver.disconnect()
    assert driver.is_connected() is False


def test_get_state_translates_snapshot_to_robot_state(fake_bridge: MagicMock):
    fake_bridge.snapshot.return_value = {
        "connected": True,
        "num_joints": 3,
        "joint_angles": [0.1, -0.2, 0.3],
        "ee_position": [0.5, 0.6, 0.7],
        # PyBullet xyzw = (0.1, 0.2, 0.3, 0.9239)
        "ee_orientation": [0.1, 0.2, 0.3, 0.9239],
        "trajectory": {"active": True, "index": 1, "total": 3, "dwell_s": 0.5},
    }
    drv = SimDriver(fake_bridge, robot_name="panda", dof=3)

    state = drv.get_state()

    assert isinstance(state, RobotState)
    assert state.joints_rad == (0.1, -0.2, 0.3)
    assert state.tcp_xyz_m == (0.5, 0.6, 0.7)
    # Reordered to wxyz canonical form.
    assert state.tcp_quat_wxyz == (0.9239, 0.1, 0.2, 0.3)
    assert state.moving is True
    assert state.error is None


def test_get_state_reports_error_when_disconnected(fake_bridge: MagicMock):
    fake_bridge.snapshot.return_value = {
        "connected": False,
        "num_joints": 0,
        "joint_angles": [],
        "ee_position": [0.0, 0.0, 0.0],
        "ee_orientation": [0.0, 0.0, 0.0, 1.0],
        "trajectory": {"active": False},
    }
    drv = SimDriver(fake_bridge, robot_name="panda", dof=0)

    state = drv.get_state()

    assert state.joints_rad == ()
    assert state.moving is False
    assert state.error is not None


def test_move_joint_submits_and_calls_set_joints_on_sim(fake_bridge: MagicMock):
    drv = SimDriver(fake_bridge, robot_name="panda", dof=6)
    targets = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]

    drv.move_joint(targets, wait=False)

    fake_bridge.submit.assert_called_once()
    sim: _FakeSim = fake_bridge._fake_sim
    # The submitted callable must have driven the sim toward the targets.
    assert sim.reset_calls == [targets]
    assert sim.target_calls == [targets]


def test_move_joint_rejects_wrong_dof(driver: SimDriver):
    with pytest.raises(ValueError):
        driver.move_joint([0.0, 0.1], wait=False)  # dof=6, only 2 supplied


def test_move_joint_accepts_speed_and_blend_args(fake_bridge: MagicMock):
    """API parity: speed_frac/blend_m must be accepted (and silently ignored)."""
    drv = SimDriver(fake_bridge, robot_name="panda", dof=6)
    drv.move_joint([0.0] * 6, speed_frac=0.9, blend_m=0.05, wait=False)
    fake_bridge.submit.assert_called_once()


def test_move_linear_passes_position_and_quat_to_ik(fake_bridge: MagicMock):
    drv = SimDriver(fake_bridge, robot_name="panda", dof=6)
    # Canonical wxyz unit quaternion (90deg rotation about Y); the driver
    # must reorder to PyBullet's xyzw and validate unit-norm at the boundary.
    s = 0.7071068
    drv.move_linear(
        xyz_m=[0.4, 0.0, 0.5],
        quat_wxyz=[s, 0.0, s, 0.0],
        wait=False,
    )

    sim: _FakeSim = fake_bridge._fake_sim
    assert len(sim.ik_calls) == 1
    pos, orn = sim.ik_calls[0]
    assert pos == [0.4, 0.0, 0.5]
    assert orn == [0.0, s, 0.0, s]  # xyzw


def test_run_program_raises_not_implemented(driver: SimDriver):
    with pytest.raises(NotImplementedError):
        driver.run_program("MODULE main\nENDMODULE\n", name="main")


def test_stop_cancels_trajectory(driver: SimDriver, fake_bridge: MagicMock):
    driver.stop()
    fake_bridge.cancel_trajectory.assert_called_once_with()


# ---------------------------------------------------------------------------
# Regression: move_linear validates unit-norm quaternion (audit must-fix #3).
# Earlier the driver only checked length, so a non-unit quaternion silently
# scaled the orientation when reordered into PyBullet's xyzw form.
# ---------------------------------------------------------------------------


def test_move_linear_rejects_non_unit_quaternion(fake_bridge: MagicMock):
    drv = SimDriver(fake_bridge, robot_name="panda", dof=6)
    with pytest.raises(ValueError, match="unit-norm"):
        drv.move_linear(
            xyz_m=[0.4, 0.0, 0.5],
            quat_wxyz=[0.9, 0.1, 0.2, 0.3],     # norm ~0.987, NOT unit
            wait=False,
        )


def test_move_linear_rejects_wrong_length_quaternion(fake_bridge: MagicMock):
    drv = SimDriver(fake_bridge, robot_name="panda", dof=6)
    with pytest.raises(ValueError, match="4 components"):
        drv.move_linear(
            xyz_m=[0.4, 0.0, 0.5],
            quat_wxyz=[1.0, 0.0, 0.0],          # only 3 components
            wait=False,
        )
