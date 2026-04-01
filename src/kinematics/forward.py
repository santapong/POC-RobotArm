"""Forward Kinematics solver."""

import numpy as np
import roboticstoolbox as rtb
from spatialmath import SE3


def solve_fk(robot: rtb.Robot, joint_angles: list[float]) -> dict:
    """Compute forward kinematics: joint angles -> end-effector pose.

    Args:
        robot: A roboticstoolbox Robot instance.
        joint_angles: List of joint angles in radians.

    Returns:
        Dict with keys:
            - position: [x, y, z] end-effector position in meters
            - rotation_matrix: 3x3 rotation matrix
            - euler_angles: [roll, pitch, yaw] in radians
            - homogeneous_matrix: 4x4 transformation matrix
    """
    q = np.array(joint_angles, dtype=float)
    if len(q) != robot.n:
        raise ValueError(
            f"Expected {robot.n} joint angles, got {len(q)}"
        )

    T: SE3 = robot.fkine(q)

    position = T.t.tolist()
    rotation = T.R.tolist()
    euler = T.rpy().tolist()  # roll, pitch, yaw
    homogeneous = T.A.tolist()

    return {
        "position": position,
        "rotation_matrix": rotation,
        "euler_angles": euler,
        "homogeneous_matrix": homogeneous,
    }


def solve_fk_all_joints(robot: rtb.Robot, joint_angles: list[float]) -> list[dict]:
    """Compute FK for every joint frame (useful for visualization).

    Returns a list of dicts, one per joint, each with position and rotation.
    """
    q = np.array(joint_angles, dtype=float)
    if len(q) != robot.n:
        raise ValueError(
            f"Expected {robot.n} joint angles, got {len(q)}"
        )

    frames = []
    for i in range(robot.n):
        T = robot.fkine(q, end=robot.links[i])
        frames.append({
            "joint_index": i,
            "position": T.t.tolist(),
            "rotation_matrix": T.R.tolist(),
        })

    # Add end-effector
    T_ee = robot.fkine(q)
    frames.append({
        "joint_index": "end_effector",
        "position": T_ee.t.tolist(),
        "rotation_matrix": T_ee.R.tolist(),
    })

    return frames
