"""Unit tests for :class:`SimSampledPathDriver`.

These tests use a hand-built fake bridge stub instead of a real PyBullet sim,
so they exercise the threading contract (`bridge.submit` indirection) and the
Driver Protocol delegation without touching rtb or pybullet.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("roboticstoolbox")

import numpy as np  # noqa: E402

from src.drivers.base import RobotState  # noqa: E402
from src.drivers.sim.sim_sampled_path import SimSampledPathDriver  # noqa: E402

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSim:
    """Minimal RobotArmSim stand-in — only what start_trajectory touches."""

    def __init__(self) -> None:
        self.set_targets_calls: list[list[float]] = []

    def set_joint_targets(self, q: list[float]) -> None:
        self.set_targets_calls.append(list(q))

    def is_connected(self) -> bool:  # pragma: no cover - not exercised here
        return True


class _FakeBridge:
    """Records submit/start_trajectory calls so we can assert thread routing."""

    def __init__(self) -> None:
        self.sim = _FakeSim()
        self.submit_calls: list[Any] = []
        self.start_trajectory_calls: list[tuple[list, float]] = []

    def submit(self, fn, timeout: float = 5.0):  # noqa: ARG002
        # The real bridge runs fn on the GUI thread. The fake runs it inline,
        # but records the call so tests can assert that submit was the entry
        # point (not start_trajectory directly).
        self.submit_calls.append(fn)
        return fn(self.sim)

    def start_trajectory(self, waypoints, dwell_s):
        self.start_trajectory_calls.append((list(waypoints), float(dwell_s)))
        if waypoints:
            self.sim.set_joint_targets(waypoints[0])

    def trajectory_status(self) -> dict:  # pragma: no cover
        return {"active": False}


class _FakeInner:
    """Minimal Driver-protocol-shaped object exposing _bridge."""

    def __init__(self, bridge: _FakeBridge) -> None:
        self._bridge = bridge
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.stop_calls = 0
        self.run_program_calls: list[tuple[str, str]] = []
        self.is_connected_value = True
        self._next_state = RobotState(
            joints_rad=(0.0,) * 7,
            tcp_xyz_m=(0.0, 0.0, 0.0),
            tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
            moving=False,
        )
        self.name = "sim:fake"
        self.dof = 7

    def connect(self) -> None:
        self.connect_calls += 1

    def disconnect(self) -> None:
        self.disconnect_calls += 1

    def is_connected(self) -> bool:
        return self.is_connected_value

    def get_state(self) -> RobotState:
        return self._next_state

    def stop(self) -> None:
        self.stop_calls += 1

    def run_program(self, source: str, name: str = "main") -> None:
        self.run_program_calls.append((source, name))


@pytest.fixture
def panda_robot():
    import roboticstoolbox as rtb

    return rtb.models.Panda()


@pytest.fixture
def driver(panda_robot):
    bridge = _FakeBridge()
    inner = _FakeInner(bridge)
    drv = SimSampledPathDriver(inner, panda_robot, dt_s=0.05)
    return drv, inner, bridge


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_constructor_resolves_bridge_via_underscore_attr(panda_robot):
    bridge = _FakeBridge()
    inner = _FakeInner(bridge)
    drv = SimSampledPathDriver(inner, panda_robot)
    assert drv._bridge is bridge


def test_constructor_resolves_bridge_via_public_attr(panda_robot):
    class _PublicBridgeInner:
        def __init__(self, bridge):
            self.bridge = bridge

    bridge = _FakeBridge()
    inner = _PublicBridgeInner(bridge)
    drv = SimSampledPathDriver(inner, panda_robot)
    assert drv._bridge is bridge


def test_constructor_rejects_inner_without_bridge(panda_robot):
    class _NoBridgeInner:
        pass

    with pytest.raises(ValueError, match="_bridge"):
        SimSampledPathDriver(_NoBridgeInner(), panda_robot)


# ---------------------------------------------------------------------------
# Threading contract — must route through bridge.submit
# ---------------------------------------------------------------------------


def test_move_joint_routes_through_bridge_submit(driver):
    drv, inner, bridge = driver
    drv.move_joint([0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], wait=False)
    # Exactly one submit call (the start_trajectory wrapper) and one
    # subsequent start_trajectory invocation (made by the lambda from the
    # GUI thread, simulated inline by _FakeBridge.submit).
    assert len(bridge.submit_calls) == 1
    assert len(bridge.start_trajectory_calls) == 1
    waypoints, dwell_s = bridge.start_trajectory_calls[0]
    assert dwell_s == pytest.approx(drv._dt_s)
    assert len(waypoints) >= 2  # at least start + end


def test_move_linear_routes_through_bridge_submit(driver):
    drv, inner, bridge = driver
    drv.move_linear(
        xyz_m=[0.4, 0.0, 0.5],
        quat_wxyz=[1.0, 0.0, 0.0, 0.0],
        speed_m_s=0.1,
        wait=False,
    )
    assert len(bridge.submit_calls) == 1
    assert len(bridge.start_trajectory_calls) == 1


def test_play_program_routes_through_bridge_submit(driver, panda_robot):
    drv, inner, bridge = driver

    from src.motion.ir import (
        JointTarget,
        Move,
        MoveKind,
        Procedure,
        Program,
        SpeedData,
        ToolData,
        WObjData,
        ZoneData,
    )

    tool = ToolData("tool0", 0.001, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    wobj = WObjData("wobj0", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    move = Move(
        kind=MoveKind.MOVE_ABS_J,
        target=JointTarget(q_rad=(0.1,) + (0.0,) * 6),
        speed=SpeedData(v_tcp_mm_s=200.0),
        zone=ZoneData.fine(),
        tool=tool,
        wobj=wobj,
    )
    prog = Program(name="t", procedures=(Procedure(name="main", body=(move,)),))
    drv.play_program(prog)

    assert len(bridge.submit_calls) == 1
    assert len(bridge.start_trajectory_calls) == 1


# ---------------------------------------------------------------------------
# Driver Protocol delegation
# ---------------------------------------------------------------------------


def test_connect_delegates_to_inner(driver):
    drv, inner, _ = driver
    drv.connect()
    assert inner.connect_calls == 1


def test_disconnect_delegates_to_inner(driver):
    drv, inner, _ = driver
    drv.disconnect()
    assert inner.disconnect_calls == 1


def test_is_connected_delegates_to_inner(driver):
    drv, inner, _ = driver
    inner.is_connected_value = False
    assert drv.is_connected() is False


def test_get_state_delegates_to_inner(driver):
    drv, inner, _ = driver
    sentinel = RobotState(
        joints_rad=(0.5,) * 7,
        tcp_xyz_m=(1.0, 2.0, 3.0),
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        moving=True,
    )
    inner._next_state = sentinel
    assert drv.get_state() is sentinel


def test_stop_delegates_to_inner(driver):
    drv, inner, _ = driver
    drv.stop()
    assert inner.stop_calls == 1


def test_run_program_delegates_to_inner(driver):
    drv, inner, _ = driver
    drv.run_program("source-text", "main")
    assert inner.run_program_calls == [("source-text", "main")]


# ---------------------------------------------------------------------------
# Sanity: panda waypoints contain the seed config
# ---------------------------------------------------------------------------


def test_move_joint_first_waypoint_matches_seed(driver):
    drv, inner, bridge = driver
    target = [0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    drv.move_joint(target, wait=False)
    waypoints, _ = bridge.start_trajectory_calls[0]
    # First waypoint is the seed configuration (zeros for default rtb Panda).
    np.testing.assert_allclose(waypoints[0], [0.0] * 7, atol=1e-9)
    # Last waypoint is the target.
    np.testing.assert_allclose(waypoints[-1], target, atol=1e-6)
