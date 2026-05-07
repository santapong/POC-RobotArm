"""Tests for the URDF catalog: every advertised robot must load and reach a target."""

import math

import pytest

pytest.importorskip("pybullet")

from src.robots.catalog import CATALOG, get_spec, list_names  # noqa: E402
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
    expected = {"panda", "ur5", "iiwa", "abb_irb1200"}
    assert set(CATALOG.keys()) == expected


def test_abb_irb1200_specifics():
    """ABB IRB 1200 must declare 6-DOF and load with the expected joint count."""
    spec = get_spec("abb_irb1200")
    assert spec.dof == 6
    assert spec.ee_link_name == "ee_link"
    assert len(spec.home_q) == 6

    sim = RobotArmSim(robot_name="abb_irb1200", use_gui=False)
    try:
        assert sim.num_joints == 6
        # Joint names should follow the joint1..joint6 convention used in the URDF.
        names = [j.name for j in sim.joints]
        assert names == [f"joint{i}" for i in range(1, 7)]
    finally:
        sim.disconnect()


def test_unknown_robot_raises():
    with pytest.raises(ValueError, match="Unknown robot"):
        get_spec("nonexistent")


def test_urdf_path_and_robot_name_mutually_exclusive():
    with pytest.raises(ValueError, match="not both"):
        RobotArmSim(robot_name="panda", urdf_path="kuka_iiwa/model.urdf", use_gui=False)
