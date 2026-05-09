"""URDF catalog for the 3D simulator.

This module is intentionally free of ``roboticstoolbox`` so the simulator
path can be exercised on machines that haven't installed the kinematics
stack. It maps short robot names to:
  - the URDF path (either a ``pybullet_data`` relative name or an absolute
    path under ``assets/``),
  - the end-effector link name (so PyBullet's IK targets the correct frame),
  - the home joint configuration (radians).

If a name listed here also has a ``roboticstoolbox`` model in
``predefined.py`` it should match dimensionally — the LLM advertises the
union of names.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Optional

from src.robots.limits import JointLimits

# Resolve the repo root from this file's location: src/robots/catalog.py -> repo/
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


@dataclass(frozen=True)
class RobotURDFSpec:
    name: str
    urdf_path: str
    ee_link_name: Optional[str] = None
    dof: int = 0
    home_q: tuple[float, ...] = field(default_factory=tuple)
    description: str = ""
    limits: JointLimits | None = field(default=None, kw_only=True)


CATALOG: dict[str, RobotURDFSpec] = {
    "panda": RobotURDFSpec(
        name="panda",
        urdf_path="franka_panda/panda.urdf",  # bundled with pybullet_data
        ee_link_name="panda_grasptarget",  # gripper tip frame
        dof=7,  # 7 arm joints; finger joints are filtered out
        home_q=(0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785),
        description="Franka Emika Panda — 7-DOF research arm.",
        # Franka Emika Panda — Franka FCI documentation, joint velocity & acceleration limits
        limits=JointLimits(
            qd_max_rad_s=(2.1750, 2.1750, 2.1750, 2.1750, 2.6100, 2.6100, 2.6100),
            qdd_max_rad_s2=(15.0, 7.5, 10.0, 12.5, 15.0, 20.0, 20.0),
        ),
    ),
    "ur5": RobotURDFSpec(
        name="ur5",
        urdf_path=os.path.join(_REPO_ROOT, "assets", "urdf", "ur5", "ur5.urdf"),
        ee_link_name="ee_link",  # the fixed tool frame, not wrist_3
        dof=6,
        home_q=(0.0, -1.571, 0.0, -1.571, 0.0, 0.0),
        description="Universal Robots UR5 — 6-DOF industrial arm (primitive-shape URDF).",
        # UR5 user manual — 180 deg/s per joint; UR publishes joint torque, not angular accel
        limits=JointLimits(
            qd_max_rad_s=(math.radians(180),) * 6,
            qdd_max_rad_s2=None,
        ),
    ),
    "iiwa": RobotURDFSpec(
        name="iiwa",
        urdf_path="kuka_iiwa/model.urdf",  # bundled with pybullet_data
        ee_link_name=None,
        dof=7,
        home_q=(0.0,) * 7,
        description="KUKA LBR iiwa — 7-DOF collaborative arm (default fallback).",
        # KUKA LBR iiwa 14 R820 specification, axes A1..A7
        limits=JointLimits(
            qd_max_rad_s=(
                math.radians(85),
                math.radians(85),
                math.radians(100),
                math.radians(75),
                math.radians(130),
                math.radians(135),
                math.radians(135),
            ),
            qdd_max_rad_s2=None,
        ),
    ),
    "abb_irb1200": RobotURDFSpec(
        name="abb_irb1200",
        urdf_path=os.path.join(_REPO_ROOT, "assets", "urdf", "abb_irb1200", "irb1200.urdf"),
        ee_link_name="ee_link",
        dof=6,
        home_q=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        description="ABB IRB 1200-5/0.9 industrial 6-DOF arm (primitive-shape URDF).",
        # ABB IRB 1200-5/0.9 product specification, Maximum axis speed table
        limits=JointLimits(
            qd_max_rad_s=(
                math.radians(288),
                math.radians(240),
                math.radians(297),
                math.radians(400),
                math.radians(405),
                math.radians(600),
            ),
            qdd_max_rad_s2=None,
        ),
    ),
}


def get_spec(name: str) -> RobotURDFSpec:
    key = name.lower().strip()
    if key not in CATALOG:
        raise ValueError(
            f"Unknown robot '{name}'. Known: {sorted(CATALOG.keys())}"
        )
    return CATALOG[key]


def list_names() -> list[str]:
    return sorted(CATALOG.keys())


def list_specs() -> list[RobotURDFSpec]:
    return [CATALOG[k] for k in list_names()]
