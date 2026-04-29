"""Smoke tests for the PyBullet simulation engine (headless)."""

import math

import pytest

pytest.importorskip("pybullet")

from src.simulation.engine import RobotArmSim  # noqa: E402


@pytest.fixture
def sim():
    s = RobotArmSim(use_gui=False)
    yield s
    s.disconnect()


def test_loads_default_robot(sim: RobotArmSim) -> None:
    assert sim.num_joints > 0
    assert len(sim.get_joint_angles()) == sim.num_joints


def test_reset_and_read_joint_angles(sim: RobotArmSim) -> None:
    target = [0.1] * sim.num_joints
    sim.reset_joint_angles(target)
    angles = sim.get_joint_angles()
    for got, want in zip(angles, target):
        assert math.isclose(got, want, abs_tol=1e-6)


def test_end_effector_pose_has_three_components(sim: RobotArmSim) -> None:
    pos, orn = sim.get_end_effector_pose()
    assert len(pos) == 3
    assert len(orn) == 4  # quaternion (xyzw)


def test_ik_returns_angles_for_each_joint(sim: RobotArmSim) -> None:
    sol = sim.solve_ik([0.4, 0.0, 0.6])
    assert len(sol) == sim.num_joints
    for a in sol:
        assert math.isfinite(a)


def test_ik_brings_end_effector_close_to_target(sim: RobotArmSim) -> None:
    target = [0.4, 0.0, 0.6]
    sol = sim.solve_ik(target)
    sim.reset_joint_angles(sol)
    pos, _ = sim.get_end_effector_pose()
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, target)))
    # PyBullet's IK is iterative; allow a generous tolerance for the smoke test.
    assert dist < 0.1, f"end-effector at {pos}, target {target}, dist={dist:.3f}"
