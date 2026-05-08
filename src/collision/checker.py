"""Headless collision checking on top of PyBullet's narrow-phase.

The :class:`CollisionChecker` provides a small, easy-to-test API:

* construct it with a robot URDF and an optional list of static scene
  meshes;
* call :meth:`is_in_collision` with a joint configuration to get a
  boolean answer (within an optional clearance distance);
* call :meth:`close` (or use the context-manager protocol) to release
  the PyBullet client.

Internally we use PyBullet's ``DIRECT`` mode so no graphics context is
needed, ``getClosestPoints`` for both robot↔scene and self-collision
checks, and skip the trivially-adjacent link pairs (parent / child) to
avoid the spurious contacts caused by shared joint axes.
"""

from __future__ import annotations

import os
from typing import Sequence

import pybullet as p


class CollisionChecker:
    """Headless PyBullet collision queries for a robot + static scene.

    Args:
        robot_urdf_path: Path to the robot's URDF.
        scene_meshes: Iterable of paths to static mesh files (STL, OBJ,
            etc.) to load as fixed scene colliders. Each mesh is loaded
            via PyBullet's ``GEOM_MESH`` collision shape — concave
            shapes will use trimesh-built convex hulls if available.
        adjacency_skip: Skip self-collision checks between immediate
            parent/child link pairs (default ``True``). They almost
            always overlap by design.
    """

    def __init__(
        self,
        robot_urdf_path: str,
        scene_meshes: Sequence[str] = (),
        adjacency_skip: bool = True,
    ) -> None:
        if not os.path.exists(robot_urdf_path):
            raise FileNotFoundError(f"Robot URDF not found: {robot_urdf_path}")

        self._client = p.connect(p.DIRECT)
        # No gravity — we never call stepSimulation here, but it's good hygiene
        # in case someone subclasses and adds physics. Also no plane.urdf so
        # the user's scene_meshes are the only static colliders.
        self._robot_id = p.loadURDF(
            robot_urdf_path, useFixedBase=True, physicsClientId=self._client
        )
        self._joint_indices = self._collect_movable_joints()

        self._scene_ids: list[int] = []
        for mesh_path in scene_meshes:
            self._scene_ids.append(self._load_scene_mesh(mesh_path))

        # Pre-compute the set of self-pairs to skip (immediate parent/child).
        self._skip_pairs: set[tuple[int, int]] = set()
        if adjacency_skip:
            n_joints = p.getNumJoints(self._robot_id, physicsClientId=self._client)
            for i in range(n_joints):
                info = p.getJointInfo(self._robot_id, i, physicsClientId=self._client)
                parent_idx = info[16]  # parentIndex (link index)
                # Pair is (parent_link, this_link). Encode as sorted tuple.
                a, b = sorted((parent_idx, i))
                self._skip_pairs.add((a, b))

        self._closed = False

    # ------------------------------------------------------------------ setup

    def _collect_movable_joints(self) -> list[int]:
        out: list[int] = []
        for i in range(p.getNumJoints(self._robot_id, physicsClientId=self._client)):
            info = p.getJointInfo(self._robot_id, i, physicsClientId=self._client)
            if info[2] != p.JOINT_FIXED:
                out.append(i)
        return out

    def _load_scene_mesh(self, mesh_path: str) -> int:
        """Load a mesh as a static collider. Returns the body id."""
        if not os.path.exists(mesh_path):
            raise FileNotFoundError(f"Scene mesh not found: {mesh_path}")
        col = p.createCollisionShape(
            p.GEOM_MESH,
            fileName=mesh_path,
            physicsClientId=self._client,
        )
        if col < 0:
            raise RuntimeError(f"Failed to create collision shape for: {mesh_path}")
        body = p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=col,
            basePosition=[0.0, 0.0, 0.0],
            physicsClientId=self._client,
        )
        return body

    def add_static_box(
        self,
        half_extents: Sequence[float],
        position: Sequence[float] = (0.0, 0.0, 0.0),
    ) -> int:
        """Convenience: spawn a static box collider in the scene."""
        col = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=list(half_extents),
            physicsClientId=self._client,
        )
        body = p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=col,
            basePosition=list(position),
            physicsClientId=self._client,
        )
        self._scene_ids.append(body)
        return body

    # ----------------------------------------------------------------- query

    def is_in_collision(
        self,
        q: Sequence[float],
        distance_m: float = 0.0,
    ) -> bool:
        """Return ``True`` if the robot at config ``q`` is in collision.

        ``distance_m`` is the clearance threshold passed to
        ``getClosestPoints``: any contact whose signed distance is below
        this value triggers a collision (positive values can be used to
        require a minimum clearance).
        """
        if self._closed:
            raise RuntimeError("CollisionChecker is closed")
        # Reset joints (no physics step needed; getClosestPoints is geometric).
        for idx, val in zip(self._joint_indices, q):
            p.resetJointState(self._robot_id, idx, float(val), physicsClientId=self._client)

        # Robot vs. each scene body.
        for sid in self._scene_ids:
            pts = p.getClosestPoints(
                self._robot_id, sid, distance=float(distance_m), physicsClientId=self._client
            )
            for pt in pts:
                if pt[8] <= distance_m:
                    return True

        # Self-collision: every link pair excluding skip set.
        n_joints = p.getNumJoints(self._robot_id, physicsClientId=self._client)
        for i in range(-1, n_joints):  # -1 is the base link
            for j in range(i + 1, n_joints):
                pair = (i, j)
                if pair in self._skip_pairs:
                    continue
                pts = p.getClosestPoints(
                    self._robot_id,
                    self._robot_id,
                    distance=float(distance_m),
                    linkIndexA=i,
                    linkIndexB=j,
                    physicsClientId=self._client,
                )
                for pt in pts:
                    if pt[8] <= distance_m:
                        return True
        return False

    # ----------------------------------------------------------------- cleanup

    def close(self) -> None:
        if self._closed:
            return
        try:
            if p.isConnected(self._client):
                p.disconnect(self._client)
        finally:
            self._closed = True

    def __enter__(self) -> "CollisionChecker":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - GC fallback
        try:
            self.close()
        except Exception:
            pass

    # ----------------------------------------------------------------- info

    @property
    def robot_id(self) -> int:
        return self._robot_id

    @property
    def scene_ids(self) -> list[int]:
        return list(self._scene_ids)

    @property
    def num_joints(self) -> int:
        return len(self._joint_indices)


def _safe_close_clients() -> None:  # pragma: no cover - test helper
    """Disconnect all dangling PyBullet clients (best-effort)."""
    for cid in range(16):
        try:
            if p.isConnected(cid):
                p.disconnect(cid)
        except Exception:
            pass


__all__ = ["CollisionChecker"]
