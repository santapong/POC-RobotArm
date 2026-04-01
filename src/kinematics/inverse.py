"""Inverse Kinematics solver."""

import numpy as np
import roboticstoolbox as rtb
from spatialmath import SE3


def solve_ik(
    robot: rtb.Robot,
    target_position: list[float],
    target_orientation: list[float] | None = None,
    method: str = "LM",
    q0: list[float] | None = None,
) -> dict:
    """Compute inverse kinematics: target pose -> joint angles.

    Args:
        robot: A roboticstoolbox Robot instance.
        target_position: [x, y, z] target position in meters.
        target_orientation: [roll, pitch, yaw] in radians (optional).
            If None, only position is constrained.
        method: IK method - "LM" (Levenberg-Marquardt), "NR" (Newton-Raphson),
            or "GN" (Gauss-Newton). Default: "LM".
        q0: Initial joint angle guess. If None, uses zeros.

    Returns:
        Dict with keys:
            - success: bool indicating if IK converged
            - joint_angles: list of joint angles in radians (or None if failed)
            - position_error: residual position error in meters
            - message: human-readable result description
    """
    pos = np.array(target_position, dtype=float)

    if target_orientation is not None:
        rpy = np.array(target_orientation, dtype=float)
        T_target = SE3.RPY(rpy) * SE3(pos)
        # Actually, let's construct it correctly:
        T_target = SE3(pos) @ SE3.RPY(rpy)
        # SE3 with both position and orientation
        T_target = SE3.Rt(SE3.RPY(rpy).R, pos)
        mask = None  # constrain all 6 DOF
    else:
        T_target = SE3(pos)
        mask = [1, 1, 1, 0, 0, 0]  # only constrain position (x, y, z)

    if q0 is not None:
        q_init = np.array(q0, dtype=float)
    else:
        q_init = np.zeros(robot.n)

    try:
        if method.upper() == "LM":
            sol = robot.ikine_LM(T_target, q0=q_init, mask=mask)
        elif method.upper() == "NR":
            sol = robot.ikine_NR(T_target, q0=q_init)
        elif method.upper() == "GN":
            sol = robot.ikine_GN(T_target, q0=q_init)
        else:
            return {
                "success": False,
                "joint_angles": None,
                "position_error": None,
                "message": f"Unknown method '{method}'. Use 'LM', 'NR', or 'GN'.",
            }
    except Exception as e:
        return {
            "success": False,
            "joint_angles": None,
            "position_error": None,
            "message": f"IK solver error: {e}",
        }

    if sol.success:
        # Verify by computing FK
        T_actual = robot.fkine(sol.q)
        pos_error = float(np.linalg.norm(T_actual.t - pos))
        return {
            "success": True,
            "joint_angles": sol.q.tolist(),
            "position_error": pos_error,
            "message": f"IK converged. Position error: {pos_error:.6f} m",
        }
    else:
        return {
            "success": False,
            "joint_angles": sol.q.tolist() if sol.q is not None else None,
            "position_error": None,
            "message": f"IK did not converge. The target may be unreachable. Reason: {sol.reason}",
        }
