"""Tempdir-backed asset import storage and URDF path resolution.

Notes
-----
- Uploaded meshes / DXF files are written to a per-process ``tempfile.mkdtemp``
  directory; they persist for the process lifetime.
- ``resolve_urdf_path`` handles both project robots (served from
  ``<repo_root>/assets/urdf/<robot>/``) and bundled robots (served from
  ``pybullet_data.getDataPath()/<robot>/``).
- Path traversal is rejected with ``FileNotFoundError`` — caller turns it into
  404 ``ASSET_NOT_FOUND``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# Repo root: server/services/assets.py → server/ → repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
_ASSETS_URDF_ROOT = _REPO_ROOT / "assets" / "urdf"

# One tempdir for the whole process lifetime.
_ASSET_TEMPDIR = Path(tempfile.mkdtemp(prefix="poc_robotarm_assets_"))

# Short names of robots whose URDFs live inside pybullet_data.
_BUNDLED_ROBOTS: frozenset[str] = frozenset({"panda", "iiwa"})

# Map from robot name → the URDF filename (relative to their directory).
_BUNDLED_URDF_FILES: dict[str, str] = {
    "panda": "franka_panda/panda.urdf",
    "iiwa": "kuka_iiwa/model.urdf",
}


def get_asset_tempdir() -> Path:
    """Return the per-process asset staging directory."""
    return _ASSET_TEMPDIR


def resolve_urdf_path(robot_name: str, file_rel: str) -> Path:
    """Resolve a URDF-related file path for ``robot_name``.

    For project robots (``ur5``, ``abb_irb1200``), the file is served from
    ``<repo_root>/assets/urdf/<robot_name>/<file_rel>``.

    For bundled robots (``panda``, ``iiwa``), it is resolved via
    ``pybullet_data.getDataPath()``.

    Raises ``FileNotFoundError`` if the path resolves outside the expected
    root (directory traversal) or the file does not exist.
    """
    robot_name = robot_name.lower().strip()

    if robot_name in _BUNDLED_ROBOTS:
        try:
            import pybullet_data
        except ImportError as exc:
            raise FileNotFoundError(
                f"pybullet_data not installed; cannot serve bundled robot {robot_name!r}"
            ) from exc
        data_root = Path(pybullet_data.getDataPath()).resolve()
        candidate = (data_root / file_rel).resolve()
        if not str(candidate).startswith(str(data_root)):
            raise FileNotFoundError(
                f"Attempted path traversal for bundled robot {robot_name!r}: {file_rel!r}"
            )
    else:
        robot_dir = (_ASSETS_URDF_ROOT / robot_name).resolve()
        candidate = (robot_dir / file_rel).resolve()
        if not str(candidate).startswith(str(robot_dir)):
            raise FileNotFoundError(
                f"Attempted path traversal for robot {robot_name!r}: {file_rel!r}"
            )

    if not candidate.is_file():
        raise FileNotFoundError(f"URDF asset not found: {candidate}")
    return candidate


def urdf_url_for(robot_name: str) -> str:
    """Return the browser-accessible URL for a robot's primary URDF file.

    The URL always goes through ``GET /api/assets/urdf/{robot}/{file:path}``
    regardless of whether the robot is project-local or bundled.
    """
    robot_name = robot_name.lower().strip()
    if robot_name in _BUNDLED_ROBOTS:
        urdf_rel = _BUNDLED_URDF_FILES.get(robot_name, f"{robot_name}.urdf")
        # urdf_rel may include a subdirectory, e.g. "franka_panda/panda.urdf"
        return f"/api/assets/urdf/{robot_name}/{urdf_rel}"
    # Project robots: file is directly in assets/urdf/<robot>/
    urdf_file = _find_project_urdf(robot_name)
    return f"/api/assets/urdf/{robot_name}/{urdf_file}"


def _find_project_urdf(robot_name: str) -> str:
    """Return the URDF filename inside ``assets/urdf/<robot_name>/``."""
    robot_dir = _ASSETS_URDF_ROOT / robot_name
    if robot_dir.is_dir():
        for f in sorted(robot_dir.iterdir()):
            if f.suffix.lower() == ".urdf":
                return f.name
    return f"{robot_name}.urdf"


__all__ = ["get_asset_tempdir", "resolve_urdf_path", "urdf_url_for"]
