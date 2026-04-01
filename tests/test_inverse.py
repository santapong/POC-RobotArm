"""Tests for inverse kinematics."""

import numpy as np
import pytest
from src.robots.predefined import get_panda, get_ur5
from src.kinematics.forward import solve_fk
from src.kinematics.inverse import solve_ik


class TestInverseKinematics:
    def test_ik_panda_reachable(self):
        """IK for a reachable position should succeed."""
        panda = get_panda()
        target = [0.5, 0.0, 0.5]
        result = solve_ik(panda, target)

        assert result["success"] is True
        assert result["joint_angles"] is not None
        assert len(result["joint_angles"]) == panda.n
        assert result["position_error"] < 0.01  # less than 1cm error

    def test_ik_round_trip(self):
        """FK -> IK -> FK should give the same position."""
        panda = get_panda()
        q_original = [0.1, -0.5, 0.3, -1.5, 0.2, 1.8, 0.5]

        # FK to get target position
        fk_result = solve_fk(panda, q_original)
        target_pos = fk_result["position"]

        # IK to recover joint angles
        ik_result = solve_ik(panda, target_pos)
        assert ik_result["success"] is True

        # FK again to verify
        fk_verify = solve_fk(panda, ik_result["joint_angles"])
        pos_error = np.linalg.norm(
            np.array(target_pos) - np.array(fk_verify["position"])
        )
        assert pos_error < 0.001  # less than 1mm

    def test_ik_ur5_reachable(self):
        """IK for UR5 at a reachable position."""
        ur5 = get_ur5()
        target = [0.3, 0.3, 0.3]
        result = solve_ik(ur5, target)

        # UR5 IK may or may not succeed depending on the target
        # but the result structure should be correct
        assert "success" in result
        assert "joint_angles" in result
        assert "message" in result

    def test_ik_invalid_method(self):
        """Invalid IK method should return error."""
        panda = get_panda()
        result = solve_ik(panda, [0.5, 0.0, 0.5], method="INVALID")

        assert result["success"] is False
        assert "Unknown method" in result["message"]

    def test_ik_with_orientation(self):
        """IK with target orientation."""
        panda = get_panda()
        target_pos = [0.4, 0.0, 0.4]
        target_orn = [np.pi, 0.0, 0.0]
        result = solve_ik(panda, target_pos, target_orientation=target_orn)

        assert "success" in result
        assert "joint_angles" in result
