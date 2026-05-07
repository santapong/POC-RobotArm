"""Ollama client wrapper for local LLM interaction with tool calling."""

import json

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from .tools import TOOL_DEFINITIONS, execute_tool

DEFAULT_MODEL = "llama3.1"

SYSTEM_PROMPT = """You are a robotics kinematics assistant. You help users work with robot arms by computing:

- **Forward Kinematics (FK)**: Given joint angles, find the end-effector position and orientation.
- **Inverse Kinematics (IK)**: Given a target position/orientation, find the joint angles to reach it.

You have access to predefined robots (Panda 7-DOF, UR5 6-DOF) and can create custom robots from DH parameters.

You ALSO have access to a live 3D simulator (PyBullet) when one is running. Use the
``sim_*`` tools to drive it:
- ``sim_get_state``: see current joint angles, end-effector pose, connection status.
- ``sim_move_to_xyz``: solve IK and command the EE to a target position.
- ``sim_set_joint`` / ``sim_set_joints``: drive joints directly.
- ``sim_play_trajectory``: run a non-blocking joint-space trajectory.
- ``sim_reset``: return to the home pose.

When users ask about robot poses, positions, or movements, use the appropriate tools to compute the answer.
Always explain the results in a clear, educational way.

Important:
- Joint angles for ``forward_kinematics``/``inverse_kinematics`` and ``sim_set_joints`` are in RADIANS. Convert if the user gives degrees.
- ``sim_set_joint`` takes DEGREES for ergonomics.
- Positions are in METRES.
- The simulator can load these robots: ``panda`` (7 DOF, default), ``ur5`` (6 DOF), ``iiwa`` (7 DOF). The kinematics tools also know ``panda`` and ``ur5``.
- ``sim_*`` tools may return ``{"ok": false, "error_code": "..."}`` — read the error and explain it; common codes: SIM_DISCONNECTED, IK_UNREACHABLE, JOINT_LIMIT_CLAMPED, SIM_TIMEOUT, INVALID_ARG.
"""


class OllamaClient:
    """Client for interacting with a local Ollama LLM with tool calling."""

    def __init__(self, model: str = DEFAULT_MODEL):
        if not OLLAMA_AVAILABLE:
            raise ImportError(
                "The 'ollama' package is not installed. "
                "Install it with: pip install ollama"
            )
        self.model = model
        self.messages: list[dict] = []
        self.client = ollama.Client()

    def check_connection(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            models = self.client.list()
            available = [m.model for m in models.models]
            # Check if our model (or a variant) is available
            for m in available:
                if self.model in m:
                    return True
            print(f"Model '{self.model}' not found. Available models: {available}")
            print(f"Pull it with: ollama pull {self.model}")
            return False
        except Exception as e:
            print(f"Cannot connect to Ollama: {e}")
            print("Make sure Ollama is running: https://ollama.ai")
            return False

    def chat(self, user_message: str) -> str:
        """Send a message and get a response, handling tool calls automatically.

        Args:
            user_message: The user's natural language message.

        Returns:
            The assistant's final text response.
        """
        self.messages.append({"role": "user", "content": user_message})

        # Send to Ollama with tools
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + self.messages,
            tools=TOOL_DEFINITIONS,
        )

        message = response.message

        # Handle tool calls in a loop (LLM may call multiple tools)
        max_iterations = 10
        iteration = 0
        while message.tool_calls and iteration < max_iterations:
            iteration += 1

            # Add assistant message with tool calls
            self.messages.append(message.model_dump())

            # Execute each tool call
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = tool_call.function.arguments

                print(f"  [Tool] {func_name}({json.dumps(func_args, indent=2)})")

                result = execute_tool(func_name, func_args)
                print(f"  [Result] {result[:200]}...")

                # Add tool result to messages
                self.messages.append({
                    "role": "tool",
                    "content": result,
                })

            # Get next response from LLM (it may call more tools or give final answer)
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + self.messages,
                tools=TOOL_DEFINITIONS,
            )
            message = response.message

        # Final text response
        assistant_text = message.content or "(No response)"
        self.messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text

    def reset(self):
        """Clear conversation history."""
        self.messages.clear()
