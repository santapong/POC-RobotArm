"""Tool definitions for the LLM agent to call kinematics functions.

Heavyweight kinematics dependencies (roboticstoolbox) are lazy-imported so
that the simulator/LLM-bridge tools can be exercised without installing the
full FK/IK stack.
"""

import json
import math
from concurrent.futures import TimeoutError as FuturesTimeoutError

# Tolerance (metres) under which an IK move is considered successful.
_SIM_IK_TOL = 0.05


def _sim_bridge():
    """Return the active SimBridge or ``None`` if the simulator isn't running."""
    from src.simulation.bridge import SimBridge

    if not SimBridge.is_initialized():
        return None
    return SimBridge.instance()


def _sim_ok(**data) -> str:
    return json.dumps({"ok": True, **data})


def _sim_err(code: str, message: str, **extras) -> str:
    return json.dumps({"ok": False, "error_code": code, "message": message, **extras})

# Tool schemas for Ollama function calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "forward_kinematics",
            "description": (
                "Compute forward kinematics: given joint angles (in radians), "
                "compute the end-effector position and orientation. "
                "Returns position [x,y,z] in meters and euler angles [roll,pitch,yaw] in radians."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "robot_name": {
                        "type": "string",
                        "description": "Name of the robot (e.g., 'panda', 'ur5')",
                    },
                    "joint_angles": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Joint angles in radians. Must match the robot's DOF.",
                    },
                },
                "required": ["robot_name", "joint_angles"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inverse_kinematics",
            "description": (
                "Compute inverse kinematics: given a target position (and optionally orientation), "
                "find the joint angles that reach that pose. "
                "Position is [x,y,z] in meters, orientation is [roll,pitch,yaw] in radians."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "robot_name": {
                        "type": "string",
                        "description": "Name of the robot (e.g., 'panda', 'ur5')",
                    },
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Target [x, y, z] position in meters.",
                    },
                    "orientation": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Optional target [roll, pitch, yaw] in radians.",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["LM", "NR", "GN"],
                        "description": "IK solver method. Default: LM (Levenberg-Marquardt).",
                    },
                },
                "required": ["robot_name", "position"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_robots",
            "description": "List all available robot models with their degrees of freedom.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_robot_details",
            "description": "Get detailed information about a robot including DOF and joint limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "robot_name": {
                        "type": "string",
                        "description": "Name of the robot.",
                    },
                },
                "required": ["robot_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "visualize_robot",
            "description": (
                "Create a 3D visualization of the robot in a given joint configuration. "
                "Saves the plot as a PNG image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "robot_name": {
                        "type": "string",
                        "description": "Name of the robot.",
                    },
                    "joint_angles": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Joint angles in radians.",
                    },
                    "save_path": {
                        "type": "string",
                        "description": "File path to save the image (default: robot_plot.png).",
                    },
                },
                "required": ["robot_name", "joint_angles"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sim_get_state",
            "description": (
                "Return the live 3D simulator's current state: joint angles (radians), "
                "end-effector position [x,y,z] in metres, end-effector orientation as a "
                "quaternion [x,y,z,w], number of joints, connection status, and active "
                "trajectory info. Use this before commanding motion to check what's loaded."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sim_reset",
            "description": "Reset the live simulator to the home pose (all joints at 0 rad).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sim_set_joint",
            "description": (
                "Drive a single joint of the live simulator to an angle. "
                "Angles are in DEGREES for ergonomics. Set 'relative' true to add to "
                "the current angle instead of setting it absolutely."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer", "description": "0-based joint index."},
                    "angle_deg": {"type": "number", "description": "Target angle in degrees."},
                    "relative": {
                        "type": "boolean",
                        "description": "If true, add to current angle. Default false.",
                    },
                },
                "required": ["idx", "angle_deg"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sim_set_joints",
            "description": (
                "Drive ALL joints of the live simulator. Length must equal the robot's DOF. "
                "Angles are in RADIANS."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "angles_rad": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "One angle per joint, in radians.",
                    },
                },
                "required": ["angles_rad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sim_move_to_xyz",
            "description": (
                "Solve IK for the live simulator and command the end-effector to move to "
                "[x,y,z] in metres. Optionally takes a 'rpy' (roll/pitch/yaw, radians). "
                "Returns the joint solution and the achieved position. "
                "If the achieved position is farther than 5 cm from the target the call "
                "fails with IK_UNREACHABLE."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"},
                    "rpy": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Optional [roll, pitch, yaw] in radians.",
                    },
                    "place_marker": {
                        "type": "boolean",
                        "description": "If true (default), place a red sphere at the target.",
                    },
                },
                "required": ["x", "y", "z"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sim_play_trajectory",
            "description": (
                "Run a non-blocking joint-space trajectory in the live simulator. "
                "Each waypoint is a full joint vector (radians). The simulator advances "
                "to the next waypoint every 'dwell_s' seconds. Returns immediately."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "waypoints": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "List of joint vectors (radians).",
                    },
                    "dwell_s": {
                        "type": "number",
                        "description": "Seconds spent at each waypoint. Default 0.5.",
                    },
                },
                "required": ["waypoints"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_custom_robot",
            "description": (
                "Create a custom robot from DH parameters. Each joint needs: "
                "a (link length), alpha (link twist), d (link offset), "
                "theta (angle offset, optional), joint_type ('revolute' or 'prismatic', default: 'revolute')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the custom robot.",
                    },
                    "dh_params": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "number"},
                                "alpha": {"type": "number"},
                                "d": {"type": "number"},
                                "theta": {"type": "number"},
                                "joint_type": {"type": "string"},
                            },
                            "required": ["a", "alpha", "d"],
                        },
                        "description": "List of DH parameter dicts, one per joint.",
                    },
                },
                "required": ["name", "dh_params"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name and return a JSON string result."""
    try:
        if name == "forward_kinematics":
            from src.robots.predefined import get_robot
            from src.kinematics.forward import solve_fk

            robot = get_robot(arguments["robot_name"])
            result = solve_fk(robot, arguments["joint_angles"])
            result["position"] = [round(v, 6) for v in result["position"]]
            result["euler_angles"] = [round(v, 6) for v in result["euler_angles"]]
            return json.dumps(result, indent=2)

        elif name == "inverse_kinematics":
            from src.robots.predefined import get_robot
            from src.kinematics.inverse import solve_ik

            robot = get_robot(arguments["robot_name"])
            orientation = arguments.get("orientation")
            method = arguments.get("method", "LM")
            result = solve_ik(robot, arguments["position"], orientation, method)
            if result["joint_angles"]:
                result["joint_angles"] = [round(v, 6) for v in result["joint_angles"]]
            return json.dumps(result, indent=2)

        elif name == "list_available_robots":
            from src.robots.predefined import list_robots

            return json.dumps(list_robots(), indent=2)

        elif name == "get_robot_details":
            from src.robots.predefined import get_robot_info

            return json.dumps(get_robot_info(arguments["robot_name"]), indent=2)

        elif name == "visualize_robot":
            from src.robots.predefined import get_robot
            from src.visualization.plotter import plot_robot

            robot = get_robot(arguments["robot_name"])
            save_path = arguments.get("save_path", "robot_plot.png")
            path = plot_robot(robot, arguments["joint_angles"], save_path=save_path)
            return json.dumps({"saved_to": path, "message": f"Plot saved to {path}"})

        elif name == "sim_get_state":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")
            snap = bridge.snapshot()
            if not snap.get("connected"):
                return _sim_err("SIM_DISCONNECTED", "Simulator disconnected.")
            return _sim_ok(**snap)

        elif name == "sim_reset":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")

            def _reset(sim):
                bridge.cancel_trajectory()
                zeros = [0.0] * sim.num_joints
                sim.reset_joint_angles(zeros)
                sim.set_joint_targets(zeros)

            try:
                bridge.submit(_reset)
            except FuturesTimeoutError:
                return _sim_err("SIM_TIMEOUT", "GUI loop did not respond in time.")
            return _sim_ok(message="Simulator reset to home pose.")

        elif name == "sim_set_joint":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")
            idx = int(arguments["idx"])
            angle_deg = float(arguments["angle_deg"])
            relative = bool(arguments.get("relative", False))
            angle_rad = math.radians(angle_deg)

            def _move(sim):
                if idx < 0 or idx >= sim.num_joints:
                    raise ValueError(
                        f"joint index {idx} out of range [0, {sim.num_joints})"
                    )
                cur = sim.get_joint_angles()
                joint = sim.joints[idx]
                requested = (cur[idx] + angle_rad) if relative else angle_rad
                applied = max(joint.lower, min(joint.upper, requested))
                target = list(cur)
                target[idx] = applied
                sim.set_joint_targets(target)
                return {
                    "requested": requested,
                    "applied": applied,
                    "clamped": applied != requested,
                    "lower": joint.lower,
                    "upper": joint.upper,
                }

            try:
                result = bridge.submit(_move)
            except FuturesTimeoutError:
                return _sim_err("SIM_TIMEOUT", "GUI loop did not respond in time.")
            except ValueError as e:
                return _sim_err("INVALID_ARG", str(e))

            if result["clamped"]:
                return _sim_err(
                    "JOINT_LIMIT_CLAMPED",
                    "Requested angle was clamped to joint limits.",
                    joint_index=idx,
                    requested_rad=result["requested"],
                    applied_rad=result["applied"],
                    lower_rad=result["lower"],
                    upper_rad=result["upper"],
                )
            return _sim_ok(joint_index=idx, applied_rad=result["applied"])

        elif name == "sim_set_joints":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")
            angles = list(arguments["angles_rad"])

            def _move(sim):
                if len(angles) != sim.num_joints:
                    raise ValueError(
                        f"expected {sim.num_joints} joint angles, got {len(angles)}"
                    )
                clamped: list[float] = []
                any_clamp = False
                for j, a in zip(sim.joints, angles):
                    ca = max(j.lower, min(j.upper, float(a)))
                    if ca != a:
                        any_clamp = True
                    clamped.append(ca)
                sim.set_joint_targets(clamped)
                return {"clamped": any_clamp, "applied": clamped}

            try:
                result = bridge.submit(_move)
            except FuturesTimeoutError:
                return _sim_err("SIM_TIMEOUT", "GUI loop did not respond in time.")
            except ValueError as e:
                return _sim_err("INVALID_ARG", str(e))

            payload = {"applied_rad": result["applied"]}
            if result["clamped"]:
                return _sim_err(
                    "JOINT_LIMIT_CLAMPED",
                    "One or more joint angles were clamped to limits.",
                    requested_rad=angles,
                    **payload,
                )
            return _sim_ok(**payload)

        elif name == "sim_move_to_xyz":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")
            x = float(arguments["x"])
            y = float(arguments["y"])
            z = float(arguments["z"])
            rpy = arguments.get("rpy")
            place_marker = bool(arguments.get("place_marker", True))

            def _solve_and_command(sim):
                target_orn = None
                if rpy is not None:
                    import pybullet as p

                    target_orn = list(p.getQuaternionFromEuler(list(rpy)))
                sol = sim.solve_ik([x, y, z], target_orn)
                # Snap the arm to the IK solution so the visual update is immediate,
                # then hold it there with position control for any subsequent physics.
                sim.reset_joint_angles(sol)
                sim.set_joint_targets(sol)
                actual_pos, _ = sim.get_end_effector_pose()
                marker_id = sim.add_target_marker([x, y, z]) if place_marker else None
                dist = math.sqrt(
                    sum((a - b) ** 2 for a, b in zip(actual_pos, [x, y, z]))
                )
                return {
                    "joint_angles": sol,
                    "achieved_position": actual_pos,
                    "distance": dist,
                    "marker_id": marker_id,
                }

            try:
                result = bridge.submit(_solve_and_command, timeout=10.0)
            except FuturesTimeoutError:
                return _sim_err("SIM_TIMEOUT", "GUI loop did not respond in time.")

            if result["distance"] > _SIM_IK_TOL:
                return _sim_err(
                    "IK_UNREACHABLE",
                    f"IK could not reach target within {_SIM_IK_TOL} m "
                    f"(distance={result['distance']:.4f} m).",
                    requested_position=[x, y, z],
                    achieved_position=result["achieved_position"],
                    joint_angles=[round(a, 6) for a in result["joint_angles"]],
                    distance=result["distance"],
                )
            return _sim_ok(
                requested_position=[x, y, z],
                achieved_position=[round(v, 6) for v in result["achieved_position"]],
                joint_angles=[round(a, 6) for a in result["joint_angles"]],
                distance=result["distance"],
            )

        elif name == "sim_play_trajectory":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")
            waypoints = arguments["waypoints"]
            dwell_s = float(arguments.get("dwell_s", 0.5))

            def _install(sim):
                for i, wp in enumerate(waypoints):
                    if len(wp) != sim.num_joints:
                        raise ValueError(
                            f"waypoint {i} has {len(wp)} values, expected {sim.num_joints}"
                        )
                bridge.start_trajectory(waypoints, dwell_s)
                return {"installed": len(waypoints)}

            try:
                result = bridge.submit(_install)
            except FuturesTimeoutError:
                return _sim_err("SIM_TIMEOUT", "GUI loop did not respond in time.")
            except ValueError as e:
                return _sim_err("INVALID_ARG", str(e))
            return _sim_ok(
                waypoints=result["installed"],
                dwell_s=dwell_s,
                message="Trajectory queued; advancing in the background.",
            )

        elif name == "create_custom_robot":
            from src.robots.custom import CustomRobot

            errors = CustomRobot.validate_dh_params(arguments["dh_params"])
            if errors:
                return json.dumps({"success": False, "errors": errors})
            custom = CustomRobot(arguments["name"], arguments["dh_params"])
            return json.dumps({
                "success": True,
                "name": arguments["name"],
                "dof": custom.robot.n,
                "message": f"Custom robot '{arguments['name']}' created with {custom.robot.n} DOF.",
            })

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})
