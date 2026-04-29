"""Tests for the URDF catalog: every advertised robot must load and reach a target."""

import math

import pytest

pytest.importorskip("pybullet")

from src.robots.catalog import CATALOG, list_names, get_spec  # noqa: E402
from src.simulation.engine import RobotArmSim  # noqa: E402


@pytest.mark.parametrize("name", list_names())
def test_catalog_robot_loads(name):
    sim = RobotArmSim(robot_name=name, use_gui=False)
    try:
        spec = get_spec(name)
        assert sim.num_joints == spec.dof, (
            f"{name}: expected {spec.dof} DOF, got {sim.num_joints}"
        )
        pos, orn = sim.get_end_effector_pose()
        assert len(pos) == 3
        assert len(orn) == 4
    finally:
        sim.disconnect()


@pytest.mark.parametrize("name", list_names())
def test_catalog_robot_reaches_target(name):
    sim = RobotArmSim(robot_name=name, use_gui=False)
    try:
        target = [0.4, 0.0, 0.5]
        sol = sim.solve_ik(target)
        sim.reset_joint_angles(sol)
        pos, _ = sim.get_end_effector_pose()
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, target)))
        assert dist < 0.05, f"{name}: distance to target = {dist:.4f}m"
    finally:
        sim.disconnect()


def test_catalog_keys_match_advertised():
    expected = {"panda", "ur5", "iiwa"}
    assert set(CATALOG.keys()) == expected


def test_unknown_robot_raises():
    with pytest.raises(ValueError, match="Unknown robot"):
        get_spec("nonexistent")


def test_urdf_path_and_robot_name_mutually_exclusive():
    with pytest.raises(ValueError, match="not both"):
        RobotArmSim(robot_name="panda", urdf_path="kuka_iiwa/model.urdf", use_gui=False)
