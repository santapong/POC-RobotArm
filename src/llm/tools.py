"""Tool definitions for the LLM agent to call kinematics functions.

Heavyweight kinematics dependencies (roboticstoolbox) are lazy-imported so
that the simulator/LLM-bridge tools can be exercised without installing the
full FK/IK stack.
"""

import json
import math
from concurrent.futures import TimeoutError as FuturesTimeoutError

from src.motion.limits import LimitsExceeded

# Tolerance (metres) under which an IK move is considered successful.
_SIM_IK_TOL = 0.05

# Sampling interval used when routing sim moves through the path interpolator.
_SIM_INTERP_DT_S = 0.05


def _one_move_program(kind_str: str, target):
    """Build a single-Move Program suitable for ``interpolate_program``.

    Args:
        kind_str: One of ``"MOVE_ABS_J"`` or ``"MOVE_L"``.
        target: A :class:`~src.motion.ir.JointTarget` or
            :class:`~src.motion.ir.PoseTarget`.

    Returns:
        A :class:`~src.motion.ir.Program` with a ``"main"`` procedure
        containing one Move.
    """
    from src.motion.ir import (
        Move,
        MoveKind,
        Procedure,
        Program,
        SpeedData,
        ToolData,
        WObjData,
        ZoneData,
    )

    tool = ToolData(name="tool0", mass_kg=0.001, tcp_xyz_m=(0.0, 0.0, 0.0), tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0))
    wobj = WObjData(name="wobj0", base_xyz_m=(0.0, 0.0, 0.0), base_quat_wxyz=(1.0, 0.0, 0.0, 0.0))
    move = Move(
        kind=MoveKind(kind_str),
        target=target,
        speed=SpeedData(v_tcp_mm_s=100.0),
        zone=ZoneData.fine(),
        tool=tool,
        wobj=wobj,
    )
    proc = Procedure(name="main", body=(move,))
    return Program(name="_llm_move", procedures=(proc,))


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
            from src.kinematics.forward import solve_fk
            from src.robots.predefined import get_robot

            robot = get_robot(arguments["robot_name"])
            result = solve_fk(robot, arguments["joint_angles"])
            result["position"] = [round(v, 6) for v in result["position"]]
            result["euler_angles"] = [round(v, 6) for v in result["euler_angles"]]
            return json.dumps(result, indent=2)

        elif name == "inverse_kinematics":
            from src.kinematics.inverse import solve_ik
            from src.robots.predefined import get_robot

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
                # Prefer the catalog's home pose; fall back to all zeros.
                home = list(sim.spec.home_q) if sim.spec and sim.spec.home_q else []
                if len(home) < sim.num_joints:
                    home = home + [0.0] * (sim.num_joints - len(home))
                home = home[: sim.num_joints]
                sim.reset_joint_angles(home)
                sim.set_joint_targets(home)

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

            # Read current angles to build the full-joint target vector.
            def _get_cur(sim):
                return list(sim.get_joint_angles())

            try:
                cur_angles = bridge.submit(_get_cur)
            except FuturesTimeoutError:
                return _sim_err("SIM_TIMEOUT", "GUI loop did not respond in time.")

            if idx < 0 or idx >= len(cur_angles):
                return _sim_err(
                    "INVALID_ARG",
                    f"joint index {idx} out of range [0, {len(cur_angles)})",
                )

            requested = (cur_angles[idx] + angle_rad) if relative else angle_rad
            target_q = list(cur_angles)
            target_q[idx] = requested

            # Route through limits-aware interpolator.
            from src.motion.ir import JointTarget
            from src.motion.path import interpolate_program
            from src.robots.predefined import get_robot

            robot_name = bridge.sim.spec.name if (bridge.sim.spec and bridge.sim.spec.name) else "panda"
            robot = get_robot(robot_name)
            prog = _one_move_program("MOVE_ABS_J", JointTarget(q_rad=tuple(float(v) for v in target_q)))
            path = interpolate_program(prog, robot, dt_s=_SIM_INTERP_DT_S, raise_on_violation=True)
            bridge.start_trajectory([list(s.q_rad) for s in path.samples], dwell_s=_SIM_INTERP_DT_S)
            return _sim_ok(joint_index=idx, applied_rad=requested)

        elif name == "sim_set_joints":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")
            angles = list(arguments["angles_rad"])

            # Validate joint count via a quick snapshot.
            def _get_nj(sim):
                return sim.num_joints

            try:
                num_joints = bridge.submit(_get_nj)
            except FuturesTimeoutError:
                return _sim_err("SIM_TIMEOUT", "GUI loop did not respond in time.")

            if len(angles) != num_joints:
                return _sim_err(
                    "INVALID_ARG",
                    f"expected {num_joints} joint angles, got {len(angles)}",
                )

            # Route through limits-aware interpolator.
            from src.motion.ir import JointTarget
            from src.motion.path import interpolate_program
            from src.robots.predefined import get_robot

            robot_name = bridge.sim.spec.name if (bridge.sim.spec and bridge.sim.spec.name) else "panda"
            robot = get_robot(robot_name)
            prog = _one_move_program("MOVE_ABS_J", JointTarget(q_rad=tuple(float(v) for v in angles)))
            path = interpolate_program(prog, robot, dt_s=_SIM_INTERP_DT_S, raise_on_violation=True)
            bridge.start_trajectory([list(s.q_rad) for s in path.samples], dwell_s=_SIM_INTERP_DT_S)
            return _sim_ok(applied_rad=angles)

        elif name == "sim_move_to_xyz":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")
            x = float(arguments["x"])
            y = float(arguments["y"])
            z = float(arguments["z"])
            rpy = arguments.get("rpy")
            place_marker = bool(arguments.get("place_marker", True))

            # Build a quaternion from optional rpy.
            if rpy is not None:
                roll, pitch, yaw = float(rpy[0]), float(rpy[1]), float(rpy[2])
                # Convert ZYX Euler to quaternion (w, x, y, z).
                cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
                cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
                cr, sr = math.cos(roll / 2), math.sin(roll / 2)
                qw = cr * cp * cy + sr * sp * sy
                qx = sr * cp * cy - cr * sp * sy
                qy = cr * sp * cy + sr * cp * sy
                qz = cr * cp * sy - sr * sp * cy
                target_quat = (qw, qx, qy, qz)
            else:
                target_quat = (1.0, 0.0, 0.0, 0.0)

            # Route through limits-aware interpolator.
            from src.motion.ir import PoseTarget
            from src.motion.path import interpolate_program
            from src.robots.predefined import get_robot

            robot_name = bridge.sim.spec.name if (bridge.sim.spec and bridge.sim.spec.name) else "panda"
            robot = get_robot(robot_name)
            prog = _one_move_program("MOVE_L", PoseTarget(xyz_m=(x, y, z), quat_wxyz=target_quat))
            path = interpolate_program(prog, robot, dt_s=_SIM_INTERP_DT_S, raise_on_violation=True)
            bridge.start_trajectory([list(s.q_rad) for s in path.samples], dwell_s=_SIM_INTERP_DT_S)

            # Verify achieved position using the last sample's FK result.
            if path.samples:
                last = path.samples[-1]
                actual_pos = list(last.flange_xyz_m)
                joint_angles = list(last.q_rad)
            else:
                actual_pos = [x, y, z]
                joint_angles = []

            # Also place a marker if requested.
            if place_marker:
                def _marker(sim):
                    sim.add_target_marker([x, y, z])

                try:
                    bridge.submit(_marker)
                except FuturesTimeoutError:
                    pass

            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(actual_pos, [x, y, z])))

            if dist > _SIM_IK_TOL:
                return _sim_err(
                    "IK_UNREACHABLE",
                    f"IK could not reach target within {_SIM_IK_TOL} m "
                    f"(distance={dist:.4f} m).",
                    requested_position=[x, y, z],
                    achieved_position=actual_pos,
                    joint_angles=[round(a, 6) for a in joint_angles],
                    distance=dist,
                )
            return _sim_ok(
                requested_position=[x, y, z],
                achieved_position=[round(v, 6) for v in actual_pos],
                joint_angles=[round(a, 6) for a in joint_angles],
                distance=dist,
            )

        elif name == "sim_play_trajectory":
            bridge = _sim_bridge()
            if bridge is None:
                return _sim_err("SIM_DISCONNECTED", "Simulator is not running.")
            waypoints = arguments["waypoints"]
            dwell_s = float(arguments.get("dwell_s", 0.5))

            # Validate waypoint shapes and wrap into MOVE_ABS_J moves for
            # per-sample limit checks.
            def _get_nj(sim):
                return sim.num_joints

            try:
                num_joints = bridge.submit(_get_nj)
            except FuturesTimeoutError:
                return _sim_err("SIM_TIMEOUT", "GUI loop did not respond in time.")

            for i, wp in enumerate(waypoints):
                if len(wp) != num_joints:
                    return _sim_err(
                        "INVALID_ARG",
                        f"waypoint {i} has {len(wp)} values, expected {num_joints}",
                    )

            # Build a multi-Move Program from the waypoints and run through
            # interpolate_program for limit checking (raise_on_violation=False so
            # violations are collected but don't abort the trajectory).
            from src.motion.ir import (
                JointTarget,
                Move,
                MoveKind,
                Procedure,
                Program,
                SpeedData,
                ToolData,
                WObjData,
                ZoneData,
            )
            from src.motion.path import interpolate_program
            from src.robots.predefined import get_robot

            robot_name = bridge.sim.spec.name if (bridge.sim.spec and bridge.sim.spec.name) else "panda"
            robot = get_robot(robot_name)
            tool = ToolData(name="tool0", mass_kg=0.001, tcp_xyz_m=(0.0, 0.0, 0.0), tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0))
            wobj = WObjData(name="wobj0", base_xyz_m=(0.0, 0.0, 0.0), base_quat_wxyz=(1.0, 0.0, 0.0, 0.0))
            moves = [
                Move(
                    kind=MoveKind.MOVE_ABS_J,
                    target=JointTarget(q_rad=tuple(float(v) for v in wp)),
                    speed=SpeedData(v_tcp_mm_s=100.0),
                    zone=ZoneData.fine(),
                    tool=tool,
                    wobj=wobj,
                )
                for wp in waypoints
            ]
            proc = Procedure(name="main", body=tuple(moves))
            prog = Program(name="_llm_traj", procedures=(proc,))
            # raise_on_violation=False: existing behaviour passes raw waypoints through.
            path = interpolate_program(prog, robot, dt_s=dwell_s, raise_on_violation=False)
            bridge.start_trajectory([list(s.q_rad) for s in path.samples], dwell_s=dwell_s)
            return _sim_ok(
                waypoints=len(waypoints),
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

    except LimitsExceeded as exc:
        return _sim_err(
            "LIMIT_VIOLATION",
            str(exc),
            violations=[v.to_dict() for v in exc.violations],
        )
    except Exception as e:
        return json.dumps({"error": str(e)})
