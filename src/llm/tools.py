"""Tool definitions for the LLM agent to call kinematics functions."""

import json
import numpy as np

from src.robots.predefined import get_robot, list_robots, get_robot_info, register_robot
from src.robots.custom import CustomRobot
from src.kinematics.forward import solve_fk, solve_fk_all_joints
from src.kinematics.inverse import solve_ik
from src.visualization.plotter import plot_robot

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
            robot = get_robot(arguments["robot_name"])
            result = solve_fk(robot, arguments["joint_angles"])
            # Round for readability
            result["position"] = [round(v, 6) for v in result["position"]]
            result["euler_angles"] = [round(v, 6) for v in result["euler_angles"]]
            return json.dumps(result, indent=2)

        elif name == "inverse_kinematics":
            robot = get_robot(arguments["robot_name"])
            orientation = arguments.get("orientation")
            method = arguments.get("method", "LM")
            result = solve_ik(robot, arguments["position"], orientation, method)
            if result["joint_angles"]:
                result["joint_angles"] = [round(v, 6) for v in result["joint_angles"]]
            return json.dumps(result, indent=2)

        elif name == "list_available_robots":
            result = list_robots()
            return json.dumps(result, indent=2)

        elif name == "get_robot_details":
            result = get_robot_info(arguments["robot_name"])
            return json.dumps(result, indent=2)

        elif name == "visualize_robot":
            robot = get_robot(arguments["robot_name"])
            save_path = arguments.get("save_path", "robot_plot.png")
            path = plot_robot(robot, arguments["joint_angles"], save_path=save_path)
            return json.dumps({"saved_to": path, "message": f"Plot saved to {path}"})

        elif name == "create_custom_robot":
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
