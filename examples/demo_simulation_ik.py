"""Animate the arm reaching a sequence of XYZ targets via inverse kinematics.

Run:
    python examples/demo_simulation_ik.py
"""

from __future__ import annotations

import math
import time

from src.simulation.engine import RobotArmSim


def waypoints_circle(center=(0.5, 0.0, 0.6), radius=0.2, n=60):
    cx, cy, cz = center
    for i in range(n):
        theta = 2.0 * math.pi * i / n
        yield (cx, cy + radius * math.cos(theta), cz + radius * math.sin(theta))


def main() -> None:
    sim = RobotArmSim(use_gui=True)
    print(f"Loaded {sim.urdf_path} with {sim.num_joints} movable joints.")

    marker = None
    try:
        # Run a few laps so you can watch it.
        for _ in range(3):
            for target in waypoints_circle():
                if marker is not None:
                    sim.remove_body(marker)
                marker = sim.add_target_marker(target)
                angles = sim.solve_ik(target)
                sim.set_joint_targets(angles)
                for _ in range(20):
                    sim.step()
                    time.sleep(1.0 / 240.0)

        ee_pos, _ = sim.get_end_effector_pose()
        print(f"Final end-effector position: {ee_pos}")
    except KeyboardInterrupt:
        pass
    finally:
        sim.disconnect()


if __name__ == "__main__":
    main()
