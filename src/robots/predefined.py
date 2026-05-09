"""Predefined robot models using roboticstoolbox."""

import numpy as np
import roboticstoolbox as rtb

# Registry of loaded robot instances
_robot_registry: dict[str, rtb.Robot] = {}


def get_panda() -> rtb.Robot:
    """Get a Franka Emika Panda 7-DOF robot."""
    if "panda" not in _robot_registry:
        # Velocity/accel limits: Franka FCI documentation, joint velocity & acceleration limits
        _robot_registry["panda"] = rtb.models.Panda()
    return _robot_registry["panda"]


def get_ur5() -> rtb.Robot:
    """Get a Universal Robots UR5 6-DOF robot."""
    if "ur5" not in _robot_registry:
        # Velocity limits: UR5 user manual — 180 deg/s per joint
        _robot_registry["ur5"] = rtb.models.UR5()
    return _robot_registry["ur5"]


def get_iiwa() -> rtb.Robot:
    """Get a KUKA LBR iiwa 14 R820 7-DOF collaborative arm.

    rtb ships ``rtb.models.LBR`` but it requires the ``rtbdata`` package; to
    keep the kinematics extra slim we hand-build a ``DHRobot`` from the
    KUKA LBR iiwa 14 R820 specification (lengths in metres, joint limits
    from the KUKA datasheet axes A1..A7):

        Link  a   alpha    d        offset    qlim (deg)
        1     0   -pi/2    0.360    0         [-170, 170]
        2     0    pi/2    0       -pi/2      [-120, 120]
        3     0    pi/2    0.420    0         [-170, 170]
        4     0   -pi/2    0        0         [-120, 120]
        5     0   -pi/2    0.400    0         [-170, 170]
        6     0    pi/2    0        0         [-120, 120]
        7     0    0       0.126    0         [-175, 175]

    Closes a known catalog/factory mismatch: ``RobotArmSim`` and the LLM
    system prompt advertise ``iiwa`` as a default; without this entry every
    rtb-using LLM tool crashed on the sim default.
    """
    if "iiwa" not in _robot_registry:
        deg = np.pi / 180.0
        links = [
            rtb.RevoluteDH(a=0.0, alpha=-np.pi / 2, d=0.360, offset=0.0,
                           qlim=[-170 * deg, 170 * deg]),
            rtb.RevoluteDH(a=0.0, alpha=np.pi / 2, d=0.0, offset=-np.pi / 2,
                           qlim=[-120 * deg, 120 * deg]),
            rtb.RevoluteDH(a=0.0, alpha=np.pi / 2, d=0.420, offset=0.0,
                           qlim=[-170 * deg, 170 * deg]),
            rtb.RevoluteDH(a=0.0, alpha=-np.pi / 2, d=0.0, offset=0.0,
                           qlim=[-120 * deg, 120 * deg]),
            rtb.RevoluteDH(a=0.0, alpha=-np.pi / 2, d=0.400, offset=0.0,
                           qlim=[-170 * deg, 170 * deg]),
            rtb.RevoluteDH(a=0.0, alpha=np.pi / 2, d=0.0, offset=0.0,
                           qlim=[-120 * deg, 120 * deg]),
            rtb.RevoluteDH(a=0.0, alpha=0.0, d=0.126, offset=0.0,
                           qlim=[-175 * deg, 175 * deg]),
        ]
        robot = rtb.DHRobot(links, name="iiwa", manufacturer="KUKA")
        _robot_registry["iiwa"] = robot
    return _robot_registry["iiwa"]


def get_abb_irb1200() -> rtb.Robot:
    """Get an ABB IRB 1200-5/0.9 6-DOF industrial robot.

    rtb does not ship a built-in IRB1200 model (only IRB140), so we
    construct a ``DHRobot`` from the published DH parameters of the
    IRB 1200-5/0.9 variant (lengths in meters):

        Link  a       alpha     d        offset    qlim (rad)
        1     0       -pi/2     0.3991   0         [-2.967,  2.967]
        2     0.350    0        0       -pi/2      [-1.745,  2.356]
        3     0.042   -pi/2     0        0         [-3.491,  1.222]
        4     0        pi/2     0.351    0         [-4.712,  4.712]
        5     0       -pi/2     0        0         [-2.269,  2.269]
        6     0        0        0.082    0         [-6.981,  6.981]
    """
    if "abb_irb1200" not in _robot_registry:
        # Velocity limits: ABB IRB 1200-5/0.9 product specification, Maximum axis speed table
        deg = np.pi / 180.0
        links = [
            rtb.RevoluteDH(
                a=0.0, alpha=-np.pi / 2, d=0.3991, offset=0.0,
                qlim=[-170 * deg, 170 * deg],
            ),
            rtb.RevoluteDH(
                a=0.350, alpha=0.0, d=0.0, offset=-np.pi / 2,
                qlim=[-100 * deg, 135 * deg],
            ),
            rtb.RevoluteDH(
                a=0.042, alpha=-np.pi / 2, d=0.0, offset=0.0,
                qlim=[-200 * deg, 70 * deg],
            ),
            rtb.RevoluteDH(
                a=0.0, alpha=np.pi / 2, d=0.351, offset=0.0,
                qlim=[-270 * deg, 270 * deg],
            ),
            rtb.RevoluteDH(
                a=0.0, alpha=-np.pi / 2, d=0.0, offset=0.0,
                qlim=[-130 * deg, 130 * deg],
            ),
            rtb.RevoluteDH(
                a=0.0, alpha=0.0, d=0.082, offset=0.0,
                qlim=[-400 * deg, 400 * deg],
            ),
        ]
        robot = rtb.DHRobot(links, name="abb_irb1200", manufacturer="ABB")
        _robot_registry["abb_irb1200"] = robot
    return _robot_registry["abb_irb1200"]


_FACTORY = {
    "panda": get_panda,
    "ur5": get_ur5,
    "iiwa": get_iiwa,
    "abb_irb1200": get_abb_irb1200,
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
