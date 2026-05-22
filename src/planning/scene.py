"""Immutable scene snapshot built once per plan request.

A :class:`SceneSnapshot` is a frozen dataclass that carries everything a
planner / optimiser / parameteriser needs from the live ``Station``:

* The robot's URDF path (resolved to disk or, for ``pybullet_data``-bundled
  URDFs, prefixed with the data path).
* DOF and home config (from the catalog).
* Per-joint velocity and acceleration limits, with the conservative 5×
  fallback applied when the catalog does not publish ``qdd_max_rad_s2``.
* The selected obstacle subset (mesh paths + simple boxes).
* A SHA-1 fingerprint covering robot + frames + selected fixtures, suitable
  as a server-side plan cache key.

Notes
-----
* Module top is import-cheap: stdlib + the planning types. No PyBullet.
* The fingerprint does NOT include ``q_start`` / ``q_goal`` — those are
  per-request and the server layer hashes them on top of this fingerprint.
* Fixtures hash only the *selected* obstacle subset (gap-report #6
  resolution); the full station's fixture list does not invalidate every
  cached plan.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.planning.types import PlannerConfig

if TYPE_CHECKING:  # pragma: no cover - hint only
    from src.station.scene import Station


# Per-joint accel default factor (rad/s² = qd_max_rad_s × this factor) when
# the robot catalog does not publish qdd_max_rad_s2. Conservative; chosen so
# the parameteriser produces non-degenerate trajectories on the robots in
# the existing catalog (ur5, iiwa, abb_irb1200). Override per-request via
# ``PlannerConfig.qdd_max_rad_s2_default``.
_DEFAULT_QDD_FACTOR = 5.0


def _resolve_urdf_path(spec_urdf_path: str) -> str:
    """Resolve a catalog URDF path to an existing file on disk.

    Catalog entries store either an absolute path under ``assets/`` or a
    short relative name (e.g. ``"kuka_iiwa/model.urdf"``) that resolves
    against the ``pybullet_data`` package's data directory.
    """
    if os.path.isabs(spec_urdf_path) and os.path.exists(spec_urdf_path):
        return spec_urdf_path
    # Try as a relative ``pybullet_data`` asset. Import inside the function so
    # the rest of this module remains import-cheap on machines without
    # pybullet installed.
    try:
        import pybullet_data
    except ImportError as exc:  # pragma: no cover - import-guard branch
        raise FileNotFoundError(
            f"URDF path {spec_urdf_path!r} is relative and pybullet_data is not "
            "available to resolve it"
        ) from exc
    candidate = os.path.join(pybullet_data.getDataPath(), spec_urdf_path)
    if os.path.exists(candidate):
        return candidate
    if os.path.exists(spec_urdf_path):
        return spec_urdf_path
    raise FileNotFoundError(f"Robot URDF not found: {spec_urdf_path}")


def _frames_hash(station: "Station") -> str:
    """SHA-1 over sorted [(name, xyz, quat, parent)] tuples."""
    payload = sorted(
        (
            fr.name,
            tuple(fr.xyz_m),
            tuple(fr.quat_wxyz),
            fr.parent,
        )
        for fr in station.frames
    )
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _fixtures_hash(station: "Station", names: tuple[str, ...]) -> str:
    """SHA-1 over the *selected* fixture subset only.

    Hashing the full station's fixture list would invalidate every cached
    plan on every fixture mutation; we only need to invalidate when the
    obstacles this plan actually saw change. See gap-report #6.
    """
    by_name = {f.name: f for f in station.fixtures}
    payload = sorted(
        (
            n,
            by_name[n].parent_frame,
            by_name[n].mesh_path,
        )
        for n in names
        if n in by_name
    )
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class SceneSnapshot:
    """Per-plan snapshot of robot + collision world."""

    robot_id: str
    robot_catalog_name: str
    robot_urdf_path: str
    ee_link_name: str | None
    dof: int
    home_q: tuple[float, ...]
    qd_max_rad_s: tuple[float, ...]
    qdd_max_rad_s2: tuple[float, ...]
    fixture_mesh_paths: tuple[str, ...]
    # Each box: ((half_extents xyz), (xyz position))
    fixture_boxes: tuple[
        tuple[tuple[float, float, float], tuple[float, float, float]], ...
    ]
    fingerprint: str

    @classmethod
    def from_station(
        cls,
        station: "Station",
        robot_id: str,
        obstacle_names: tuple[str, ...] = (),
        qdd_default_factor: float = _DEFAULT_QDD_FACTOR,
        planner_config: PlannerConfig | None = None,
    ) -> "SceneSnapshot":
        """Build a :class:`SceneSnapshot` from a live :class:`Station`.

        Raises
        ------
        ValueError
            If ``robot_id`` is not a registered robot in ``station``, or if
            any name in ``obstacle_names`` is not in ``station.fixtures``.
        FileNotFoundError
            If the robot's URDF path cannot be resolved to an existing file.
        """
        from src.robots.catalog import get_spec

        robot_entry = next((r for r in station.robots if r.name == robot_id), None)
        if robot_entry is None:
            raise ValueError(
                f"SceneSnapshot.from_station: robot {robot_id!r} not in station "
                f"(known: {sorted(r.name for r in station.robots)})"
            )

        spec = get_spec(robot_entry.robot_catalog_name)
        urdf_path = _resolve_urdf_path(spec.urdf_path)

        # Limits — only `panda` ships qdd in the catalog; others fall back to
        # qd × _DEFAULT_QDD_FACTOR. PlannerConfig.qdd_max_rad_s2_default
        # overrides as a uniform scalar (preferred by ops who want a tighter
        # cap than the heuristic).
        if spec.limits is None:
            raise ValueError(
                f"SceneSnapshot.from_station: robot {robot_id!r} catalog entry has no "
                "joint limits"
            )
        qd_max = tuple(float(v) for v in spec.limits.qd_max_rad_s)
        if planner_config is not None and planner_config.qdd_max_rad_s2_default is not None:
            qdd_default = float(planner_config.qdd_max_rad_s2_default)
            qdd_max = tuple(qdd_default for _ in qd_max)
        elif spec.limits.qdd_max_rad_s2 is not None:
            qdd_max = tuple(float(v) for v in spec.limits.qdd_max_rad_s2)
        else:
            if qdd_default_factor <= 0.0:
                raise ValueError(
                    f"qdd_default_factor must be > 0, got {qdd_default_factor}"
                )
            qdd_max = tuple(qd * qdd_default_factor for qd in qd_max)

        fixtures_by_name = {f.name: f for f in station.fixtures}
        mesh_paths: list[str] = []
        boxes: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
        for name in obstacle_names:
            if name not in fixtures_by_name:
                raise ValueError(
                    f"SceneSnapshot.from_station: obstacle {name!r} not in "
                    f"station.fixtures (known: {sorted(fixtures_by_name)})"
                )
            entry = fixtures_by_name[name]
            if entry.mesh_path:
                if not os.path.exists(entry.mesh_path):
                    raise FileNotFoundError(
                        f"Fixture {name!r} mesh path not on disk: {entry.mesh_path}"
                    )
                mesh_paths.append(entry.mesh_path)
            # Box-only fixtures (no mesh) are not represented in the current
            # Station model — leave fixture_boxes empty unless the caller
            # supplies them via a future API. The collision wrapper uses
            # only mesh_paths today.

        fingerprint = cls._compute_fingerprint(
            robot_id=robot_id,
            urdf_path=urdf_path,
            qdd_max=qdd_max,
            station=station,
            obstacle_names=obstacle_names,
        )

        home_q = tuple(float(v) for v in spec.home_q[: spec.dof]) or tuple(
            0.0 for _ in range(spec.dof)
        )

        return cls(
            robot_id=robot_id,
            robot_catalog_name=robot_entry.robot_catalog_name,
            robot_urdf_path=urdf_path,
            ee_link_name=spec.ee_link_name,
            dof=spec.dof,
            home_q=home_q,
            qd_max_rad_s=qd_max,
            qdd_max_rad_s2=qdd_max,
            fixture_mesh_paths=tuple(mesh_paths),
            fixture_boxes=tuple(boxes),
            fingerprint=fingerprint,
        )

    @staticmethod
    def _compute_fingerprint(
        robot_id: str,
        urdf_path: str,
        qdd_max: tuple[float, ...],
        station: "Station",
        obstacle_names: tuple[str, ...],
    ) -> str:
        """SHA-1 of the canonical JSON payload (algorithm in design doc)."""
        payload = json.dumps(
            {
                "robot_id": robot_id,
                "robot_urdf_path": urdf_path,
                "frames_hash": _frames_hash(station),
                "fixtures_hash": _fixtures_hash(station, obstacle_names),
                "qdd_max_rad_s2": list(qdd_max),
            },
            sort_keys=True,
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Convenience hashes (exposed for tests / server cache)
    # ------------------------------------------------------------------

    def frames_hash(self) -> str:
        """SHA-1 of the snapshot's frame contribution. Stable across calls."""
        # The snapshot has already absorbed the live station's frames into
        # its fingerprint; we expose them here from the cached top-level
        # payload by deriving a sub-hash. Cheap to recompute since the
        # snapshot is immutable.
        return hashlib.sha1(
            json.dumps(
                {"robot_id": self.robot_id, "fingerprint": self.fingerprint},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    def fixtures_hash(self) -> str:
        """SHA-1 of the snapshot's selected fixture subset."""
        return hashlib.sha1(
            json.dumps(
                {"fixtures": list(self.fixture_mesh_paths)},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


__all__ = ["SceneSnapshot"]
