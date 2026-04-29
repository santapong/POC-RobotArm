"""Tests for the SimBridge command queue and the LLM sim_* tools.

The GUI thread is simulated in-process: a worker thread submits commands,
and the test loop calls ``bridge.tick()`` to drain them — exactly what the
real GUI does.
"""

import json
import threading
import time

import pytest

pytest.importorskip("pybullet")

from src.llm.tools import execute_tool  # noqa: E402
from src.simulation.bridge import SimBridge  # noqa: E402
from src.simulation.engine import RobotArmSim  # noqa: E402


@pytest.fixture
def bridge():
    SimBridge.shutdown()
    sim = RobotArmSim(use_gui=False)
    b = SimBridge.initialize(sim)
    yield b
    SimBridge.shutdown()
    sim.disconnect()


def _drain_until(bridge: SimBridge, predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        bridge.tick()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("predicate not satisfied within timeout")


def test_get_state_reports_connection_and_dof(bridge):
    bridge.tick()  # populate snapshot
    raw = execute_tool("sim_get_state", {})
    state = json.loads(raw)
    assert state["ok"] is True
    assert state["connected"] is True
    assert state["num_joints"] == bridge.sim.num_joints
    assert len(state["joint_angles"]) == bridge.sim.num_joints
    assert len(state["ee_position"]) == 3


def test_get_state_reports_disconnected_when_no_bridge():
    SimBridge.shutdown()
    raw = execute_tool("sim_get_state", {})
    state = json.loads(raw)
    assert state["ok"] is False
    assert state["error_code"] == "SIM_DISCONNECTED"


def test_set_joint_drives_single_joint(bridge):
    result_holder: dict = {}

    def worker():
        result_holder["raw"] = execute_tool(
            "sim_set_joint", {"idx": 0, "angle_deg": 30.0}
        )

    t = threading.Thread(target=worker)
    t.start()
    _drain_until(bridge, lambda: not t.is_alive())
    t.join()

    out = json.loads(result_holder["raw"])
    assert out["ok"] is True
    assert out["joint_index"] == 0


def test_set_joint_rejects_bad_index(bridge):
    result_holder: dict = {}

    def worker():
        result_holder["raw"] = execute_tool(
            "sim_set_joint", {"idx": 999, "angle_deg": 0.0}
        )

    t = threading.Thread(target=worker)
    t.start()
    _drain_until(bridge, lambda: not t.is_alive())
    t.join()

    out = json.loads(result_holder["raw"])
    assert out["ok"] is False
    assert out["error_code"] == "INVALID_ARG"


def test_move_to_xyz_returns_ok_for_reachable_target(bridge):
    result_holder: dict = {}

    def worker():
        result_holder["raw"] = execute_tool(
            "sim_move_to_xyz", {"x": 0.4, "y": 0.0, "z": 0.6, "place_marker": False}
        )

    t = threading.Thread(target=worker)
    t.start()
    _drain_until(bridge, lambda: not t.is_alive(), timeout=15.0)
    t.join()

    out = json.loads(result_holder["raw"])
    assert out["ok"] is True, out
    assert out["distance"] < 0.05
    assert len(out["joint_angles"]) == bridge.sim.num_joints


def test_play_trajectory_advances_over_time(bridge):
    n = bridge.sim.num_joints
    waypoints = [[0.0] * n, [0.2] * n, [-0.2] * n]

    result_holder: dict = {}

    def worker():
        result_holder["raw"] = execute_tool(
            "sim_play_trajectory", {"waypoints": waypoints, "dwell_s": 0.05}
        )

    t = threading.Thread(target=worker)
    t.start()
    _drain_until(bridge, lambda: not t.is_alive())
    t.join()

    out = json.loads(result_holder["raw"])
    assert out["ok"] is True
    assert out["waypoints"] == 3
    assert bridge.trajectory_status()["active"] is True

    # Advance the trajectory by ticking past the dwell intervals.
    deadline = time.monotonic() + 2.0
    while bridge.trajectory_status()["active"] and time.monotonic() < deadline:
        bridge.tick()
        time.sleep(0.02)
    assert bridge.trajectory_status()["active"] is False


def test_reset_clears_trajectory_and_zeros_joints(bridge):
    n = bridge.sim.num_joints
    bridge.start_trajectory([[0.3] * n, [0.0] * n], dwell_s=10.0)
    assert bridge.trajectory_status()["active"] is True

    result_holder: dict = {}

    def worker():
        result_holder["raw"] = execute_tool("sim_reset", {})

    t = threading.Thread(target=worker)
    t.start()
    _drain_until(bridge, lambda: not t.is_alive())
    t.join()

    out = json.loads(result_holder["raw"])
    assert out["ok"] is True
    assert bridge.trajectory_status()["active"] is False
    bridge.tick()  # refresh snapshot
    snap = bridge.snapshot()
    assert all(abs(a) < 1e-6 for a in snap["joint_angles"])
