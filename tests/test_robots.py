"""Tests for robot models."""

import numpy as np
import pytest

from src.robots.custom import CustomRobot
from src.robots.predefined import get_panda, get_robot, get_robot_info, get_ur5, list_robots


class TestPredefinedRobots:
    def test_panda_loads(self):
        panda = get_panda()
        assert panda.n == 7
        assert panda is not None

    def test_ur5_loads(self):
        ur5 = get_ur5()
        assert ur5.n == 6

    def test_list_robots(self):
        robots = list_robots()
        names = [r["name"] for r in robots]
        assert "panda" in names
        assert "ur5" in names

    def test_get_robot_by_name(self):
        panda = get_robot("panda")
        assert panda.n == 7
        ur5 = get_robot("ur5")
        assert ur5.n == 6

    def test_get_robot_unknown(self):
        with pytest.raises(ValueError, match="Unknown robot"):
            get_robot("nonexistent")

    def test_get_robot_info(self):
        info = get_robot_info("panda")
        assert info["name"] == "panda"
        assert info["dof"] == 7
        assert len(info["joint_limits"]) > 0


class TestCustomRobot:
    def test_create_3dof(self):
        """Create a simple 3-DOF planar arm."""
        params = [
            {"a": 1.0, "alpha": 0, "d": 0},
            {"a": 1.0, "alpha": 0, "d": 0},
            {"a": 0.5, "alpha": 0, "d": 0},
        ]
        custom = CustomRobot("test_3dof", params)
        robot = custom.get_robot()
        assert robot.n == 3

    def test_custom_registered(self):
        """Custom robot should be accessible via get_robot."""
        params = [
            {"a": 1.0, "alpha": 0, "d": 0},
            {"a": 0.5, "alpha": 0, "d": 0},
        ]
        CustomRobot("test_2dof", params, register=True)
        robot = get_robot("test_2dof")
        assert robot.n == 2

    def test_validate_valid_params(self):
        params = [
            {"a": 1.0, "alpha": 0, "d": 0},
            {"a": 0.5, "alpha": np.pi / 2, "d": 0.1},
        ]
        errors = CustomRobot.validate_dh_params(params)
        assert errors == []

    def test_validate_missing_keys(self):
        params = [{"a": 1.0}]  # missing alpha and d
        errors = CustomRobot.validate_dh_params(params)
        assert len(errors) > 0

    def test_validate_empty(self):
        errors = CustomRobot.validate_dh_params([])
        assert len(errors) > 0

    def test_validate_bad_joint_type(self):
        params = [{"a": 1.0, "alpha": 0, "d": 0, "joint_type": "linear"}]
        errors = CustomRobot.validate_dh_params(params)
        assert any("joint_type" in e for e in errors)

    def test_prismatic_joint(self):
        params = [
            {"a": 0, "alpha": 0, "d": 0, "joint_type": "prismatic"},
            {"a": 1.0, "alpha": 0, "d": 0, "joint_type": "revolute"},
        ]
        custom = CustomRobot("test_prismatic", params)
        assert custom.robot.n == 2
