"""Interactive 3D GUI for the robot arm simulation.

Opens a native PyBullet OpenGL window with:
  - Mouse-controlled camera (rotate / pan / zoom)
  - One slider per joint for live position control
  - Three sliders + a trigger to solve IK to an XYZ target
  - A red sphere marking the active IK target

If a ``SimBridge`` is provided (or one has already been initialized in this
process), the GUI drains its command queue every tick so an LLM running on
a worker thread can drive the simulator.

Run with:
    python -m src.simulation
"""

from __future__ import annotations

import argparse
import threading
import time
from typing import Optional

import pybullet as p

from src.simulation.bridge import SimBridge
from src.simulation.engine import RobotArmSim


def _add_joint_sliders(sim: RobotArmSim) -> list[int]:
    sliders: list[int] = []
    for j in sim.joints:
        midpoint = max(min(0.0, j.upper), j.lower)
        sliders.append(p.addUserDebugParameter(j.name, j.lower, j.upper, midpoint))
    return sliders


def run(
    urdf_path: Optional[str] = None,
    hz: float = 240.0,
    bridge: Optional[SimBridge] = None,
    stop_event: Optional[threading.Event] = None,
) -> None:
    if bridge is None:
        sim = RobotArmSim(urdf_path=urdf_path, use_gui=True)
        owns_sim = True
    else:
        sim = bridge.sim
        owns_sim = False

    joint_sliders = _add_joint_sliders(sim)

    tx = p.addUserDebugParameter("target_x", -1.0, 1.0, 0.5)
    ty = p.addUserDebugParameter("target_y", -1.0, 1.0, 0.0)
    tz = p.addUserDebugParameter("target_z", 0.0, 1.5, 0.7)
    # PyBullet has no real button; bumping these sliders triggers an action.
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
            if stop_event is not None and stop_event.is_set():
                break

            # If the LLM-driven trajectory is active, sliders shouldn't fight it.
            traj_active = bridge is not None and bridge.trajectory_status().get("active")

            cur_slider_vals = [p.readUserDebugParameter(s) for s in joint_sliders]
            user_moved_slider = any(
                abs(c - p_) > 1e-4 for c, p_ in zip(cur_slider_vals, prev_slider_vals)
            )
            if user_moved_slider and not traj_active:
                target_angles = list(cur_slider_vals)
                sim.set_joint_targets(target_angles)
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
                sim.set_joint_targets(target_angles)

            cur_reset = p.readUserDebugParameter(reset_trigger)
            if cur_reset != last_reset:
                last_reset = cur_reset
                target_angles = [0.0] * sim.num_joints
                sim.reset_joint_angles(target_angles)
                sim.set_joint_targets(target_angles)
                if bridge is not None:
                    bridge.cancel_trajectory()

            if bridge is not None:
                bridge.tick()

            sim.step()
            time.sleep(dt)
    except KeyboardInterrupt:
        pass
    finally:
        if owns_sim:
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
