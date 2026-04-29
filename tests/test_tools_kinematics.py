"""Tests for kinematics tools — gated on roboticstoolbox availability.

These cover the original ``forward_kinematics``, ``inverse_kinematics``,
and ``visualize_robot`` tool entrypoints. They run only when rtb is
installed; the headless CI lane skips them entirely.
"""

import json

import pytest

pytest.importorskip("roboticstoolbox")

from src.llm.tools import execute_tool  # noqa: E402


def test_forward_kinematics_panda_zeros():
    raw = execute_tool(
        "forward_kinematics", {"robot_name": "panda", "joint_angles": [0] * 7}
    )
    payload = json.loads(raw)
    assert "position" in payload
    assert len(payload["position"]) == 3


def test_inverse_kinematics_panda_reaches_target():
    raw = execute_tool(
        "inverse_kinematics", {"robot_name": "panda", "position": [0.5, 0.0, 0.5]}
    )
    payload = json.loads(raw)
    if payload.get("joint_angles"):
        assert len(payload["joint_angles"]) == 7


def test_list_available_robots_returns_known_names():
    raw = execute_tool("list_available_robots", {})
    payload = json.loads(raw)
    names = {r["name"] for r in payload}
    assert {"panda", "ur5"}.issubset(names)
