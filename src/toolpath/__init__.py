"""Toolpath module — CAD intake, operations, and joint optimization.

This package implements a Robotmaster-style CAM pipeline:

1. ``intake`` — load STL/OBJ/PLY/COLLADA via trimesh, DXF polylines via ezdxf.
2. ``operations`` — generate :class:`~src.motion.ir.PoseTarget` waypoints from
   geometry: ``polyline_follow``, ``surface_raster``, ``curve_on_surface``.
3. ``optimizer`` — dynamic-programming redundancy resolution: per-waypoint
   joint candidates fanned around the tool-Z axis, with a trellis search that
   minimises ``||Δq||_W + λ/manipulability`` along the path.

Outputs are vendor-neutral SI units, ready to drop into a
:class:`~src.motion.ir.Program` and feed to any post-processor.
"""

from __future__ import annotations

from src.toolpath.intake import load_dxf_polylines, load_mesh
from src.toolpath.operations import (
    curve_on_surface,
    polyline_follow,
    surface_raster,
)
from src.toolpath.optimizer import optimize_joints

__all__ = [
    "curve_on_surface",
    "load_dxf_polylines",
    "load_mesh",
    "optimize_joints",
    "polyline_follow",
    "surface_raster",
]
