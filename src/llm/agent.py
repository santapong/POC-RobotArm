"""Main LLM-powered robot arm agent."""

import json
from .ollama_client import OllamaClient, OLLAMA_AVAILABLE
from .tools import execute_tool


class RobotArmAgent:
    """Conversational agent for robot arm kinematics.

    Uses a local Ollama LLM to interpret natural language commands
    and call FK/IK/visualization tools.

    Falls back to a simple command parser if Ollama is not available.
    """

    def __init__(self, model: str = "llama3.1"):
        self.model = model
        self.ollama_client: OllamaClient | None = None
        self._llm_available = False

        if OLLAMA_AVAILABLE:
            try:
                self.ollama_client = OllamaClient(model=model)
                self._llm_available = self.ollama_client.check_connection()
            except Exception:
                self._llm_available = False

        if not self._llm_available:
            print("LLM not available. Using direct command mode.")
            print("Commands: fk, ik, list, info, plot, custom, help")

    @property
    def is_llm_mode(self) -> bool:
        return self._llm_available

    def process(self, user_input: str) -> str:
        """Process user input and return a response.

        If LLM is available, use natural language processing.
        Otherwise, fall back to direct command parsing.
        """
        if self._llm_available and self.ollama_client:
            return self.ollama_client.chat(user_input)
        else:
            return self._direct_command(user_input)

    def _direct_command(self, text: str) -> str:
        """Simple command parser as fallback when LLM is not available."""
        parts = text.strip().split()
        if not parts:
            return "Empty command. Type 'help' for available commands."

        cmd = parts[0].lower()

        if cmd == "help":
            return (
                "Available commands:\n"
                "  list                          - List available robots\n"
                "  info <robot>                  - Get robot details\n"
                "  fk <robot> <angles...>        - Forward kinematics\n"
                "  ik <robot> <x> <y> <z>        - Inverse kinematics\n"
                "  plot <robot> <angles...>       - Visualize robot\n"
                "  help                          - Show this help\n"
                "\nExamples:\n"
                "  fk panda 0 0 0 0 0 0 0\n"
                "  ik panda 0.5 0.0 0.5\n"
                "  plot ur5 0 -1.57 1.57 0 0 0\n"
            )

        elif cmd == "list":
            result = execute_tool("list_available_robots", {})
            return f"Available robots:\n{result}"

        elif cmd == "info" and len(parts) >= 2:
            result = execute_tool("get_robot_details", {"robot_name": parts[1]})
            return result

        elif cmd == "fk" and len(parts) >= 3:
            robot_name = parts[1]
            angles = [float(a) for a in parts[2:]]
            result = execute_tool("forward_kinematics", {
                "robot_name": robot_name,
                "joint_angles": angles,
            })
            return f"Forward Kinematics Result:\n{result}"

        elif cmd == "ik" and len(parts) >= 5:
            robot_name = parts[1]
            position = [float(parts[2]), float(parts[3]), float(parts[4])]
            orientation = None
            if len(parts) >= 8:
                orientation = [float(parts[5]), float(parts[6]), float(parts[7])]
            args = {"robot_name": robot_name, "position": position}
            if orientation:
                args["orientation"] = orientation
            result = execute_tool("inverse_kinematics", args)
            return f"Inverse Kinematics Result:\n{result}"

        elif cmd == "plot" and len(parts) >= 3:
            robot_name = parts[1]
            angles = [float(a) for a in parts[2:]]
            result = execute_tool("visualize_robot", {
                "robot_name": robot_name,
                "joint_angles": angles,
            })
            return f"Visualization:\n{result}"

        else:
            return f"Unknown command '{cmd}'. Type 'help' for available commands."
