"""End-to-end: FakeOllamaClient → agent → tools → bridge → sim.

Drives the full natural-language path without Ollama. Each test starts
a real headless ``RobotArmSim``, installs the bridge, then asks the
agent (with the fake client) to perform a task and asserts the
simulator state changed accordingly.
"""

from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("pybullet")

from src.llm.agent import RobotArmAgent  # noqa: E402
from src.llm.fake_client import FakeOllamaClient  # noqa: E402
from src.simulation.bridge import SimBridge  # noqa: E402
from src.simulation.engine import RobotArmSim  # noqa: E402


@pytest.fixture
def sim_with_bridge():
    SimBridge.shutdown()
    sim = RobotArmSim(robot_name="panda", use_gui=False)
    bridge = SimBridge.initialize(sim)
    yield sim, bridge
    SimBridge.shutdown()
    sim.disconnect()


def _agent_call(bridge: SimBridge, agent: RobotArmAgent, message: str, timeout=10.0):
    """Run agent.process on a worker thread; tick the bridge until it returns."""
    holder: dict = {}

    def worker():
        holder["reply"] = agent.process(message)

    t = threading.Thread(target=worker)
    t.start()
    deadline = time.monotonic() + timeout
    while t.is_alive() and time.monotonic() < deadline:
        bridge.tick()
        time.sleep(0.005)
    t.join(timeout=1.0)
    assert "reply" in holder, "agent did not return within timeout"
    return holder["reply"]


def test_state_query_returns_connected(sim_with_bridge):
    sim, bridge = sim_with_bridge
    bridge.tick()
    agent = RobotArmAgent(client=FakeOllamaClient())
    reply = _agent_call(bridge, agent, "what's the simulator state?")
    assert "ee_position" in reply
    assert "connected" in reply


def test_xyz_kv_move_drives_arm_to_target(sim_with_bridge):
    sim, bridge = sim_with_bridge
    agent = RobotArmAgent(client=FakeOllamaClient())
    reply = _agent_call(bridge, agent, "Please move to x=0.4 y=0.0 z=0.5")
    bridge.tick()
    pos = bridge.snapshot()["ee_position"]
    import math

    dist = math.sqrt(
        sum((a - b) ** 2 for a, b in zip(pos, [0.4, 0.0, 0.5]))
    )
    assert dist < 0.05, f"expected arm at (0.4, 0, 0.5); got {pos}"
    assert "Moving the end-effector" in reply


def test_joint_command_routes_to_sim_set_joint(sim_with_bridge):
    sim, bridge = sim_with_bridge
    agent = RobotArmAgent(client=FakeOllamaClient())
    reply = _agent_call(bridge, agent, "rotate joint 1 to 30 deg")
    assert "joint" in reply.lower() or "Driving" in reply
    bridge.tick()
    angles = bridge.snapshot()["joint_angles"]
    # First arm joint should now be near 30° (≈ 0.524 rad)
    import math

    assert abs(angles[0] - math.radians(30)) < 0.05


def test_reset_returns_arm_to_home(sim_with_bridge):
    sim, bridge = sim_with_bridge
    sim.set_joint_targets([0.5] * sim.num_joints)
    for _ in range(20):
        sim.step()

    agent = RobotArmAgent(client=FakeOllamaClient())
    _agent_call(bridge, agent, "please reset the arm")
    bridge.tick()
    angles = bridge.snapshot()["joint_angles"]
    expected = list(sim.spec.home_q)
    for got, want in zip(angles, expected):
        assert abs(got - want) < 1e-6, f"reset went to {angles}, expected {expected}"


def test_unknown_input_does_not_crash(sim_with_bridge):
    sim, bridge = sim_with_bridge
    agent = RobotArmAgent(client=FakeOllamaClient())
    reply = _agent_call(bridge, agent, "fly the robot to the moon")
    assert "Sorry" in reply or "didn't recognise" in reply


def test_back_to_back_moves_complete(sim_with_bridge):
    """UAT US-10: concurrent commands serialize cleanly."""
    sim, bridge = sim_with_bridge
    agent = RobotArmAgent(client=FakeOllamaClient())

    holder: dict = {"replies": []}

    def w(msg):
        holder["replies"].append(agent.process(msg))

    t1 = threading.Thread(target=w, args=("move to x=0.4 y=0.0 z=0.5",))
    t2 = threading.Thread(target=w, args=("move to x=0.3 y=0.0 z=0.6",))
    t1.start()
    time.sleep(0.05)
    t2.start()
    deadline = time.monotonic() + 15.0
    while (t1.is_alive() or t2.is_alive()) and time.monotonic() < deadline:
        bridge.tick()
        time.sleep(0.005)
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)
    assert not t1.is_alive() and not t2.is_alive()
    assert len(holder["replies"]) == 2
    bridge.tick()
    pos = bridge.snapshot()["ee_position"]
    # Final position should match the second move (0.3, 0, 0.6) within tolerance
    import math
    dist_to_second = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, [0.3, 0.0, 0.6])))
    assert dist_to_second < 0.1, f"final position {pos} matches neither move"
