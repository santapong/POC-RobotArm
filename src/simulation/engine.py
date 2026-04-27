"""PyBullet-backed 3D robot arm simulator.

Loads a URDF, exposes joint control, forward/inverse kinematics, and a
target marker. Use ``use_gui=True`` for the native OpenGL viewer (RViz-like)
or ``use_gui=False`` for headless mode (tests, batch jobs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import pybullet as p
import pybullet_data

from src.robots.catalog import RobotURDFSpec, get_spec


@dataclass
class JointInfo:
    index: int
    name: str
    lower: float
    upper: float


class RobotArmSim:
    """Thin wrapper over PyBullet for arm simulation."""

    DEFAULT_ROBOT = "iiwa"

    def __init__(
        self,
        urdf_path: Optional[str] = None,
        robot_name: Optional[str] = None,
        ee_link_name: Optional[str] = None,
        use_gui: bool = True,
        gravity: float = -9.81,
        load_plane: bool = True,
    ) -> None:
        """Initialize the simulator.

        ``robot_name`` and ``urdf_path`` are mutually exclusive. If neither
        is provided the default robot from the catalog is loaded. When
        ``robot_name`` is used, the catalog also supplies the end-effector
        link name and home configuration; ``urdf_path`` callers may pass
        ``ee_link_name`` explicitly.
        """
        if urdf_path is not None and robot_name is not None:
            raise ValueError("Pass urdf_path OR robot_name, not both.")

        spec: Optional[RobotURDFSpec] = None
        if urdf_path is None:
            spec = get_spec(robot_name or self.DEFAULT_ROBOT)
            urdf_path = spec.urdf_path
            if ee_link_name is None:
                ee_link_name = spec.ee_link_name

        self.spec = spec
        self.use_gui = use_gui
        self.client = p.connect(p.GUI if use_gui else p.DIRECT)
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=self.client)
        p.setGravity(0, 0, gravity, physicsClientId=self.client)

        if use_gui:
            # Trim PyBullet's default panels for a cleaner viewport.
            p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0, physicsClientId=self.client)
            p.resetDebugVisualizerCamera(
                cameraDistance=1.6,
                cameraYaw=45,
                cameraPitch=-25,
                cameraTargetPosition=[0, 0, 0.4],
                physicsClientId=self.client,
            )

        if load_plane:
            p.loadURDF("plane.urdf", physicsClientId=self.client)

        self.urdf_path = urdf_path
        self.robot_id = p.loadURDF(
            self.urdf_path, useFixedBase=True, physicsClientId=self.client
        )
        self.joints = self._collect_movable_joints()
        if not self.joints:
            raise RuntimeError(f"No movable joints found in URDF: {self.urdf_path}")
        # When loaded via the catalog, trim to the arm DOF (drops gripper /
        # finger joints that share the URDF — e.g. Panda's two finger joints).
        if spec is not None and spec.dof and spec.dof < len(self.joints):
            self.joints = self.joints[: spec.dof]
        self.ee_link_name = ee_link_name
        self.end_effector_index = self._resolve_ee_index(ee_link_name)
        if spec is not None and spec.home_q:
            home = list(spec.home_q)[: len(self.joints)]
            self.reset_joint_angles(home + [0.0] * max(0, len(self.joints) - len(home)))

    # ------------------------------------------------------------------ joints

    def _collect_movable_joints(self) -> list[JointInfo]:
        out: list[JointInfo] = []
        for i in range(p.getNumJoints(self.robot_id, physicsClientId=self.client)):
            info = p.getJointInfo(self.robot_id, i, physicsClientId=self.client)
            joint_type = info[2]
            if joint_type == p.JOINT_FIXED:
                continue
            lower, upper = info[8], info[9]
            if upper <= lower:
                lower, upper = -3.14159, 3.14159
            out.append(
                JointInfo(index=i, name=info[1].decode(), lower=lower, upper=upper)
            )
        return out

    def _resolve_ee_index(self, ee_link_name: Optional[str]) -> int:
        """Find the joint index whose child link is the end-effector.

        If ``ee_link_name`` is given, search every joint (including fixed)
        for the matching link. Otherwise default to the last movable joint
        — matching the historical behavior of this class.
        """
        if ee_link_name is not None:
            for i in range(p.getNumJoints(self.robot_id, physicsClientId=self.client)):
                info = p.getJointInfo(self.robot_id, i, physicsClientId=self.client)
                if info[12].decode() == ee_link_name:
                    return i
            raise ValueError(
                f"ee_link_name='{ee_link_name}' not found in URDF {self.urdf_path}"
            )
        return self.joints[-1].index

    @property
    def num_joints(self) -> int:
        return len(self.joints)

    @property
    def joint_indices(self) -> list[int]:
        return [j.index for j in self.joints]

    def get_joint_angles(self) -> list[float]:
        return [
            p.getJointState(self.robot_id, j.index, physicsClientId=self.client)[0]
            for j in self.joints
        ]

    def reset_joint_angles(self, angles: Sequence[float]) -> None:
        """Teleport joints to the given angles (no physics)."""
        for j, a in zip(self.joints, angles):
            p.resetJointState(self.robot_id, j.index, a, physicsClientId=self.client)

    def set_joint_targets(self, angles: Sequence[float], force: float = 200.0) -> None:
        """Drive joints to the given angles via position control (with physics)."""
        for j, a in zip(self.joints, angles):
            p.setJointMotorControl2(
                self.robot_id,
                j.index,
                p.POSITION_CONTROL,
                targetPosition=a,
                force=force,
                physicsClientId=self.client,
            )

    # ----------------------------------------------------------- kinematics

    def get_end_effector_pose(self) -> tuple[list[float], list[float]]:
        state = p.getLinkState(
            self.robot_id, self.end_effector_index, physicsClientId=self.client
        )
        return list(state[0]), list(state[1])  # position, orientation (xyzw)

    def solve_ik(
        self,
        target_position: Sequence[float],
        target_orientation: Optional[Sequence[float]] = None,
        max_iterations: int = 200,
        residual_threshold: float = 1e-5,
    ) -> list[float]:
        """Inverse kinematics via PyBullet's damped least-squares solver."""
        kwargs = dict(
            maxNumIterations=max_iterations,
            residualThreshold=residual_threshold,
            physicsClientId=self.client,
        )
        if target_orientation is not None:
            sol = p.calculateInverseKinematics(
                self.robot_id,
                self.end_effector_index,
                list(target_position),
                list(target_orientation),
                **kwargs,
            )
        else:
            sol = p.calculateInverseKinematics(
                self.robot_id,
                self.end_effector_index,
                list(target_position),
                **kwargs,
            )
        return list(sol)[: self.num_joints]

    # --------------------------------------------------------------- markers

    def add_target_marker(
        self,
        position: Sequence[float],
        rgba: Sequence[float] = (1.0, 0.2, 0.2, 0.9),
        radius: float = 0.04,
    ) -> int:
        vis = p.createVisualShape(
            p.GEOM_SPHERE,
            radius=radius,
            rgbaColor=list(rgba),
            physicsClientId=self.client,
        )
        return p.createMultiBody(
            baseMass=0,
            baseVisualShapeIndex=vis,
            basePosition=list(position),
            physicsClientId=self.client,
        )

    def remove_body(self, body_id: int) -> None:
        p.removeBody(body_id, physicsClientId=self.client)

    # ---------------------------------------------------------------- runtime

    def step(self) -> None:
        p.stepSimulation(physicsClientId=self.client)

    def is_connected(self) -> bool:
        return p.isConnected(self.client)

    def disconnect(self) -> None:
        if p.isConnected(self.client):
            p.disconnect(self.client)

    def __enter__(self) -> "RobotArmSim":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()
