"""Demo: Inverse Kinematics - finding joint angles for target positions."""

import numpy as np
from src.robots.predefined import get_panda, get_ur5
from src.kinematics.forward import solve_fk
from src.kinematics.inverse import solve_ik
from src.visualization.plotter import plot_robot


def main():
    print("=" * 60)
    print("Inverse Kinematics Demo")
    print("=" * 60)

    # --- Panda Robot ---
    panda = get_panda()
    print(f"\n--- {panda.name} ({panda.n} DOF) ---")

    # Target: reach a point in front of the robot
    target_pos = [0.5, 0.0, 0.5]
    print(f"\nTarget position: {target_pos}")
    result = solve_ik(panda, target_pos)
    print(f"  Success: {result['success']}")
    print(f"  Joint angles: {result['joint_angles']}")
    print(f"  Position error: {result['position_error']}")
    print(f"  Message: {result['message']}")

    # Verify with FK
    if result["success"]:
        fk_result = solve_fk(panda, result["joint_angles"])
        print(f"  FK verification: {fk_result['position']}")
        plot_robot(panda, result["joint_angles"],
                   title=f"Panda IK -> {target_pos}", save_path="panda_ik.png")
        print("  Plot saved to panda_ik.png")

    # Target with orientation
    target_pos2 = [0.4, 0.2, 0.3]
    target_orn = [np.pi, 0, np.pi / 4]  # roll, pitch, yaw
    print(f"\nTarget position: {target_pos2} with orientation: {target_orn}")
    result2 = solve_ik(panda, target_pos2, target_orientation=target_orn)
    print(f"  Success: {result2['success']}")
    print(f"  Joint angles: {result2['joint_angles']}")
    print(f"  Message: {result2['message']}")

    # --- UR5 Robot ---
    ur5 = get_ur5()
    print(f"\n--- {ur5.name} ({ur5.n} DOF) ---")

    target_pos3 = [0.3, 0.3, 0.3]
    print(f"\nTarget position: {target_pos3}")
    result3 = solve_ik(ur5, target_pos3)
    print(f"  Success: {result3['success']}")
    print(f"  Joint angles: {result3['joint_angles']}")
    print(f"  Message: {result3['message']}")

    if result3["success"]:
        fk_result3 = solve_fk(ur5, result3["joint_angles"])
        print(f"  FK verification: {fk_result3['position']}")

    # --- Round-trip test ---
    print(f"\n--- Round-trip Test (FK -> IK -> FK) ---")
    q_original = [0.1, -0.5, 0.3, -1.5, 0.2, 1.8, 0.5]
    fk_orig = solve_fk(panda, q_original)
    print(f"  Original joint angles: {q_original}")
    print(f"  FK position: {fk_orig['position']}")

    ik_result = solve_ik(panda, fk_orig["position"])
    if ik_result["success"]:
        fk_verify = solve_fk(panda, ik_result["joint_angles"])
        pos_err = np.linalg.norm(
            np.array(fk_orig["position"]) - np.array(fk_verify["position"])
        )
        print(f"  IK joint angles: {ik_result['joint_angles']}")
        print(f"  FK verify position: {fk_verify['position']}")
        print(f"  Round-trip position error: {pos_err:.8f} m")
    else:
        print(f"  IK failed: {ik_result['message']}")


if __name__ == "__main__":
    main()
