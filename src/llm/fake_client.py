"""Deterministic stand-in for ``OllamaClient`` — no Ollama, no network.

Maps a small set of canned utterances to scripted ``tool_calls`` so the
agent → tools → bridge → simulator path can be exercised end-to-end in
CI and from ``scripts/uat_run.py``. Anything that doesn't match a pattern
returns a polite "I don't know" reply (covers UAT US-9).

The client mirrors only the surface that ``RobotArmAgent`` uses:
    - ``chat(user_message: str) -> str``
    - ``reset() -> None``

Each ``chat`` call may invoke ``execute_tool`` zero or more times before
returning a final natural-language string, mimicking the real client's
tool-calling loop.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from .tools import execute_tool

_FLOAT = r"-?\d+(?:\.\d+)?"
_XYZ = re.compile(
    rf"(?:to|at|reach|position)\s*\(?\s*({_FLOAT})\s*[, ]\s*({_FLOAT})\s*[, ]\s*({_FLOAT})\)?"
)
_XYZ_KV = re.compile(
    rf"x\s*=\s*({_FLOAT}).*?y\s*=\s*({_FLOAT}).*?z\s*=\s*({_FLOAT})", re.IGNORECASE
)
_JOINT = re.compile(
    rf"joint\s+(\d+)[^-\d]*({_FLOAT})\s*deg", re.IGNORECASE
)


@dataclass
class FakeOllamaClient:
    """Drop-in replacement for OllamaClient backed by regex pattern-matching."""

    transcript: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------ public

    def chat(self, user_message: str) -> str:
        msg = user_message.strip().lower()
        self.transcript.append({"role": "user", "content": user_message})

        for matcher, handler in self._handlers():
            match = matcher(msg)
            if match:
                tool_name, tool_args, narration = handler(match)
                tool_result = execute_tool(tool_name, tool_args)
                reply = self._narrate(narration, tool_name, tool_result)
                self.transcript.append({"role": "assistant", "content": reply})
                return reply

        # No match: fall back to a polite refusal.
        reply = (
            "Sorry, I didn't recognise that command. Try something like "
            "'move to x=0.4 y=0.0 z=0.5', 'rotate joint 1 by -45 deg', "
            "'what's the simulator state?', or 'reset the arm'."
        )
        self.transcript.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        self.transcript.clear()

    def check_connection(self) -> bool:  # for parity with OllamaClient
        return True

    # ----------------------------------------------------------------- helpers

    def _handlers(self) -> list[tuple[Callable[[str], object], Callable]]:
        return [
            (lambda m: "state" in m and "sim" in m or m.startswith("what") and "state" in m, self._handle_state),
            (lambda m: "reset" in m, self._handle_reset),
            (lambda m: _XYZ_KV.search(m), self._handle_move_kv),
            (lambda m: _XYZ.search(m), self._handle_move),
            (lambda m: _JOINT.search(m), self._handle_joint),
            (lambda m: "list" in m and ("robot" in m or "available" in m), self._handle_list),
        ]

    @staticmethod
    def _handle_state(_match):
        return "sim_get_state", {}, "Here's the current simulator state."

    @staticmethod
    def _handle_reset(_match):
        return "sim_reset", {}, "Reset the simulator."

    @staticmethod
    def _handle_move_kv(match):
        x, y, z = (float(g) for g in match.groups())
        return "sim_move_to_xyz", {"x": x, "y": y, "z": z}, f"Moving the end-effector to ({x}, {y}, {z})."

    @staticmethod
    def _handle_move(match):
        x, y, z = (float(g) for g in match.groups())
        return "sim_move_to_xyz", {"x": x, "y": y, "z": z}, f"Moving the end-effector to ({x}, {y}, {z})."

    @staticmethod
    def _handle_joint(match):
        idx, deg = int(match.group(1)), float(match.group(2))
        # Some users say "joint 1" meaning the first joint (1-indexed).
        zero_based = max(0, idx - 1) if idx >= 1 else idx
        return "sim_set_joint", {"idx": zero_based, "angle_deg": deg}, f"Driving joint {idx} to {deg}°."

    @staticmethod
    def _handle_list(_match):
        return "list_available_robots", {}, "Robots known to the kinematics solver:"

    @staticmethod
    def _narrate(narration: str, tool_name: str, tool_result: str) -> str:
        try:
            payload = json.loads(tool_result)
        except json.JSONDecodeError:
            return f"{narration}\n{tool_result}"
        if isinstance(payload, dict) and payload.get("ok") is False:
            return (
                f"{narration} The simulator returned an error: "
                f"{payload.get('error_code', 'UNKNOWN')} — {payload.get('message', tool_result)}"
            )
        return f"{narration} (tool: {tool_name}) {tool_result}"
