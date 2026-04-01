"""Tests for forward kinematics."""

import numpy as np
import pytest
from src.robots.predefined import get_panda, get_ur5
from src.kinematics.forward import solve_fk, solve_fk_all_joints


class TestForwardKinematics:
    def test_fk_panda_home(self):
        """FK at home position should return a valid pose."""
        panda = get_panda()
        q = [0.0] * panda.n
        result = solve_fk(panda, q)

        assert "position" in result
        assert "rotation_matrix" in result
        assert "euler_angles" in result
        assert len(result["position"]) == 3
        assert len(result["euler_angles"]) == 3
        # Position should be finite
        assert all(np.isfinite(v) for v in result["position"])

    def test_fk_panda_known_config(self):
        """FK at a known configuration should return reasonable values."""
        panda = get_panda()
        q = [0, -0.3, 0, -2.2, 0, 2.0, 0.79]
        result = solve_fk(panda, q)

        # End-effector should be in a reasonable workspace
        pos = result["position"]
        assert -2.0 < pos[0] < 2.0  # x
        assert -2.0 < pos[1] < 2.0  # y
        assert -1.0 < pos[2] < 2.0  # z

    def test_fk_ur5_home(self):
        """FK for UR5 at home position."""
        ur5 = get_ur5()
        q = [0.0] * ur5.n
        result = solve_fk(ur5, q)

        assert len(result["position"]) == 3
        assert all(np.isfinite(v) for v in result["position"])

    def test_fk_wrong_dof(self):
        """FK with wrong number of joint angles should raise ValueError."""
        panda = get_panda()
        with pytest.raises(ValueError, match="Expected 7 joint angles"):
            solve_fk(panda, [0.0] * 3)

    def test_fk_all_joints(self):
        """All joint frames should be computed."""
        panda = get_panda()
        q = [0.0] * panda.n
        frames = solve_fk_all_joints(panda, q)

        # Should have n joints + end-effector
        assert len(frames) == panda.n + 1
        assert frames[-1]["joint_index"] == "end_effector"

        # Each frame should have position
        for f in frames:
            assert len(f["position"]) == 3

    def test_fk_different_configs_differ(self):
        """Different joint angles should produce different end-effector poses."""
        panda = get_panda()
        q1 = [0.0] * panda.n
        q2 = [0.5, -0.3, 0.2, -1.5, 0.1, 1.0, 0.4]

        r1 = solve_fk(panda, q1)
        r2 = solve_fk(panda, q2)

        assert r1["position"] != r2["position"]

    def test_fk_returns_4x4_homogeneous(self):
        """Homogeneous matrix should be 4x4."""
        panda = get_panda()
        q = [0.0] * panda.n
        result = solve_fk(panda, q)

        H = np.array(result["homogeneous_matrix"])
        assert H.shape == (4, 4)
        # Bottom row should be [0, 0, 0, 1]
        np.testing.assert_array_almost_equal(H[3, :], [0, 0, 0, 1])
