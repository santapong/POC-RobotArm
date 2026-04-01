"""Predefined robot models using roboticstoolbox."""

import roboticstoolbox as rtb
import numpy as np

# Registry of loaded robot instances
_robot_registry: dict[str, rtb.Robot] = {}


def get_panda() -> rtb.Robot:
    """Get a Franka Emika Panda 7-DOF robot."""
    if "panda" not in _robot_registry:
        _robot_registry["panda"] = rtb.models.Panda()
    return _robot_registry["panda"]


def get_ur5() -> rtb.Robot:
    """Get a Universal Robots UR5 6-DOF robot."""
    if "ur5" not in _robot_registry:
        _robot_registry["ur5"] = rtb.models.UR5()
    return _robot_registry["ur5"]


_FACTORY = {
    "panda": get_panda,
    "ur5": get_ur5,
}


def list_robots() -> list[dict]:
    """List all available robot models (predefined + custom)."""
    robots = []
    for name, factory in _FACTORY.items():
        robot = factory()
        robots.append({
            "name": name,
            "dof": robot.n,
            "description": str(robot),
        })
    # Include any custom robots that have been registered
    for name, robot in _robot_registry.items():
        if name not in _FACTORY:
            robots.append({
                "name": name,
                "dof": robot.n,
                "description": str(robot),
            })
    return robots


def get_robot(name: str) -> rtb.Robot:
    """Get a robot by name (predefined or custom)."""
    name = name.lower().strip()
    if name in _robot_registry:
        return _robot_registry[name]
    if name in _FACTORY:
        return _FACTORY[name]()
    available = list(_FACTORY.keys()) + [
        k for k in _robot_registry if k not in _FACTORY
    ]
    raise ValueError(
        f"Unknown robot '{name}'. Available: {available}"
    )


def register_robot(name: str, robot: rtb.Robot) -> None:
    """Register a custom robot in the global registry."""
    _robot_registry[name.lower().strip()] = robot


def get_robot_info(name: str) -> dict:
    """Get detailed information about a robot."""
    robot = get_robot(name)
    info = {
        "name": name,
        "dof": robot.n,
        "joint_types": [],
        "joint_limits": [],
    }
    for i, link in enumerate(robot.links):
        if hasattr(link, 'qlim') and link.qlim is not None:
            limits = link.qlim.tolist()
        else:
            limits = [None, None]
        info["joint_limits"].append({
            "joint": i,
            "min": limits[0] if len(limits) > 0 else None,
            "max": limits[1] if len(limits) > 1 else None,
        })
    return info
