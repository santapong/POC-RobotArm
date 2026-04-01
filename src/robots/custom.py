"""Custom robot definition from DH parameters."""

import numpy as np
import roboticstoolbox as rtb
from roboticstoolbox import RevoluteDH, PrismaticDH

from .predefined import register_robot


class CustomRobot:
    """Build a custom robot arm from DH parameters.

    Each joint is specified as a dict with keys:
        - a: link length (meters)
        - alpha: link twist (radians)
        - d: link offset (meters)
        - theta: joint angle offset (radians), used for revolute home position
        - joint_type: "revolute" or "prismatic" (default: "revolute")

    Example:
        params = [
            {"a": 0, "alpha": 0, "d": 0.333, "theta": 0},
            {"a": 0, "alpha": -np.pi/2, "d": 0, "theta": 0},
            {"a": 0, "alpha": np.pi/2, "d": 0.316, "theta": 0},
        ]
        robot = CustomRobot("my_arm", params)
    """

    def __init__(self, name: str, dh_params: list[dict], register: bool = True):
        self.name = name
        self.dh_params = dh_params
        self.robot = self._build(name, dh_params)
        if register:
            register_robot(name, self.robot)

    @staticmethod
    def _build(name: str, dh_params: list[dict]) -> rtb.DHRobot:
        links = []
        for i, p in enumerate(dh_params):
            a = float(p.get("a", 0))
            alpha = float(p.get("alpha", 0))
            d = float(p.get("d", 0))
            theta = float(p.get("theta", 0))
            joint_type = p.get("joint_type", "revolute").lower()

            if joint_type == "revolute":
                links.append(RevoluteDH(d=d, a=a, alpha=alpha, offset=theta))
            elif joint_type == "prismatic":
                links.append(PrismaticDH(theta=theta, a=a, alpha=alpha, offset=d))
            else:
                raise ValueError(
                    f"Joint {i}: unknown type '{joint_type}'. Use 'revolute' or 'prismatic'."
                )

        return rtb.DHRobot(links, name=name)

    def get_robot(self) -> rtb.DHRobot:
        return self.robot

    @staticmethod
    def validate_dh_params(dh_params: list[dict]) -> list[str]:
        """Validate DH parameters and return a list of errors (empty if valid)."""
        errors = []
        if not dh_params:
            errors.append("DH parameters list is empty.")
            return errors

        required_keys = {"a", "alpha", "d"}
        for i, p in enumerate(dh_params):
            if not isinstance(p, dict):
                errors.append(f"Joint {i}: expected a dict, got {type(p).__name__}")
                continue
            missing = required_keys - set(p.keys())
            if missing:
                errors.append(f"Joint {i}: missing keys {missing}")
            for key in ["a", "alpha", "d", "theta"]:
                if key in p:
                    try:
                        float(p[key])
                    except (TypeError, ValueError):
                        errors.append(f"Joint {i}: '{key}' must be numeric, got {p[key]!r}")
            jt = p.get("joint_type", "revolute")
            if jt not in ("revolute", "prismatic"):
                errors.append(f"Joint {i}: joint_type must be 'revolute' or 'prismatic', got '{jt}'")

        return errors
