"""Demo: Forward Kinematics with different robots and configurations."""

import numpy as np
from src.robots.predefined import get_panda, get_ur5
from src.kinematics.forward import solve_fk, solve_fk_all_joints
from src.visualization.plotter import plot_robot


def main():
    print("=" * 60)
    print("Forward Kinematics Demo")
    print("=" * 60)

    # --- Panda Robot ---
    panda = get_panda()
    print(f"\n--- {panda.name} ({panda.n} DOF) ---")

    # Home position (all zeros)
    q_home = [0.0] * panda.n
    result = solve_fk(panda, q_home)
    print(f"\nHome position (all zeros):")
    print(f"  End-effector position: {result['position']}")
    print(f"  Euler angles (RPY):    {result['euler_angles']}")

    # A typical "ready" configuration
    q_ready = [0, -0.3, 0, -2.2, 0, 2.0, 0.79]
    result = solve_fk(panda, q_ready)
    print(f"\nReady configuration {q_ready}:")
    print(f"  End-effector position: {result['position']}")
    print(f"  Euler angles (RPY):    {result['euler_angles']}")

    # Save a plot
    plot_robot(panda, q_ready, title="Panda - Ready Config", save_path="panda_ready.png")
    print("  Plot saved to panda_ready.png")

    # --- UR5 Robot ---
    ur5 = get_ur5()
    print(f"\n--- {ur5.name} ({ur5.n} DOF) ---")

    q_home_ur5 = [0.0] * ur5.n
    result = solve_fk(ur5, q_home_ur5)
    print(f"\nHome position (all zeros):")
    print(f"  End-effector position: {result['position']}")
    print(f"  Euler angles (RPY):    {result['euler_angles']}")

    q_bent = [0, -np.pi / 4, np.pi / 4, 0, np.pi / 4, 0]
    result = solve_fk(ur5, q_bent)
    print(f"\nBent configuration:")
    print(f"  End-effector position: {result['position']}")
    print(f"  Euler angles (RPY):    {result['euler_angles']}")

    plot_robot(ur5, q_bent, title="UR5 - Bent Config", save_path="ur5_bent.png")
    print("  Plot saved to ur5_bent.png")

    # --- All joint frames ---
    print(f"\n--- All Joint Frames (Panda ready config) ---")
    frames = solve_fk_all_joints(panda, q_ready)
    for f in frames:
        pos = [round(v, 4) for v in f["position"]]
        print(f"  Joint {f['joint_index']}: position = {pos}")


if __name__ == "__main__":
    main()
