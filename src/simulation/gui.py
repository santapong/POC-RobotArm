"""Interactive 3D GUI for the robot arm simulation.

Opens a native PyBullet OpenGL window with:
  - Mouse-controlled camera (rotate / pan / zoom)
  - One slider per joint for live position control
  - Three sliders + a trigger to solve IK to an XYZ target
  - A red sphere marking the active IK target

Run with:
    python -m src.simulation
"""

from __future__ import annotations

import argparse
import time
from typing import Optional

import pybullet as p

from src.simulation.engine import RobotArmSim


def _add_joint_sliders(sim: RobotArmSim) -> list[int]:
    sliders: list[int] = []
    for j in sim.joints:
        midpoint = max(min(0.0, j.upper), j.lower)
        sliders.append(p.addUserDebugParameter(j.name, j.lower, j.upper, midpoint))
    return sliders


def run(urdf_path: Optional[str] = None, hz: float = 240.0) -> None:
    sim = RobotArmSim(urdf_path=urdf_path, use_gui=True)

    joint_sliders = _add_joint_sliders(sim)

    tx = p.addUserDebugParameter("target_x", -1.0, 1.0, 0.5)
    ty = p.addUserDebugParameter("target_y", -1.0, 1.0, 0.0)
    tz = p.addUserDebugParameter("target_z", 0.0, 1.5, 0.7)
    # PyBullet has no real button; bumping this slider triggers an IK solve.
    ik_trigger = p.addUserDebugParameter("solve_ik (move slider)", 1, 0, 1)
    reset_trigger = p.addUserDebugParameter("reset (move slider)", 1, 0, 1)

    last_ik = p.readUserDebugParameter(ik_trigger)
    last_reset = p.readUserDebugParameter(reset_trigger)
    prev_slider_vals = [p.readUserDebugParameter(s) for s in joint_sliders]
    target_angles = list(prev_slider_vals)
    marker: Optional[int] = None

    dt = 1.0 / hz
    try:
        while sim.is_connected():
            cur_slider_vals = [p.readUserDebugParameter(s) for s in joint_sliders]
            # If the user moved any joint slider, switch to manual joint mode.
            for i, (cur, prev) in enumerate(zip(cur_slider_vals, prev_slider_vals)):
                if abs(cur - prev) > 1e-4:
                    target_angles = list(cur_slider_vals)
                    break
            prev_slider_vals = cur_slider_vals

            cur_ik = p.readUserDebugParameter(ik_trigger)
            if cur_ik != last_ik:
                last_ik = cur_ik
                target = [
                    p.readUserDebugParameter(tx),
                    p.readUserDebugParameter(ty),
                    p.readUserDebugParameter(tz),
                ]
                if marker is not None:
                    sim.remove_body(marker)
                marker = sim.add_target_marker(target)
                target_angles = sim.solve_ik(target)

            cur_reset = p.readUserDebugParameter(reset_trigger)
            if cur_reset != last_reset:
                last_reset = cur_reset
                target_angles = [0.0] * sim.num_joints
                sim.reset_joint_angles(target_angles)

            sim.set_joint_targets(target_angles)
            sim.step()
            time.sleep(dt)
    except KeyboardInterrupt:
        pass
    finally:
        sim.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="3D robot arm simulator (PyBullet GUI)")
    parser.add_argument(
        "--urdf",
        default=None,
        help="Path to a URDF (default: kuka_iiwa/model.urdf bundled with PyBullet). "
        "Try 'franka_panda/panda.urdf' for a 7-DOF Panda.",
    )
    parser.add_argument(
        "--hz", type=float, default=240.0, help="Simulation step rate (default: 240)."
    )
    args = parser.parse_args()
    run(urdf_path=args.urdf, hz=args.hz)


if __name__ == "__main__":
    main()
