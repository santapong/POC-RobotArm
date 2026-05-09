"""CAD intake — load meshes (STL/OBJ/PLY/COLLADA) and DXF polylines.

This module is intentionally thin: it adapts the third-party loaders
(``trimesh`` for meshes, ``ezdxf`` for vector drawings) to the units and
shapes the rest of the pipeline expects.

Conventions:

* All output coordinates are in **meters** (the IR's SI base). DXF files
  are conventionally millimeters in mechanical design, so the
  :func:`load_dxf_polylines` helper converts mm to m before returning.
* Meshes returned by :func:`load_mesh` are kept in their native units —
  trimesh does not enforce unit metadata, so callers must scale when
  needed (the toolpath operations don't reinterpret mesh units).

Both loaders raise informative ``FileNotFoundError`` / ``ValueError``
exceptions instead of propagating opaque library errors so the CAM
pipeline can react at a single boundary.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import trimesh as _trimesh  # noqa: F401


# Default DXF unit: millimeters. The function accepts an override for
# odd files but defaults to the convention used by 99% of mechanical
# CAD packages.
_MM_TO_M = 1.0e-3


def load_mesh(path: str) -> Any:
    """Load a triangular mesh from disk.

    Supports the formats ``trimesh.load_mesh`` understands: STL, OBJ,
    PLY, COLLADA (.dae), GLB, etc. Returns a single :class:`trimesh.Trimesh`
    — if the file contains a scene with multiple geometries they are
    concatenated.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: if the loaded geometry isn't a triangular mesh.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Mesh file not found: {path}")

    import trimesh  # local import: keeps the toolpath package importable
    # in environments without trimesh installed.

    obj = trimesh.load_mesh(path)
    # ``load_mesh`` may return a Scene if the file has multiple meshes;
    # collapse to a single Trimesh for the rest of the pipeline.
    if isinstance(obj, trimesh.Scene):
        if len(obj.geometry) == 0:
            raise ValueError(f"Mesh file contains no geometry: {path}")
        meshes = [g for g in obj.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError(f"Mesh file contains no triangle meshes: {path}")
        obj = trimesh.util.concatenate(meshes)

    if not isinstance(obj, trimesh.Trimesh):
        raise ValueError(
            f"Loaded geometry is not a Trimesh ({type(obj).__name__}): {path}"
        )
    return obj


def load_dxf_polylines(
    path: str,
    unit_scale: float = _MM_TO_M,
) -> list[list[tuple[float, float]]]:
    """Load 2D polylines from a DXF file.

    Recognised entities: ``LWPOLYLINE``, ``POLYLINE``, ``LINE``. Each is
    converted to a list of ``(x, y)`` tuples. The DXF unit is assumed to
    be millimeters and converted to meters by ``unit_scale``.

    Args:
        path: DXF file path.
        unit_scale: Multiplier applied to the raw DXF coordinates. The
            default ``1e-3`` converts mm to m. Pass ``1.0`` if your DXF
            is already in meters.

    Returns:
        A list of polylines. Each polyline is a list of ``(x, y)``
        tuples. Empty list if the modelspace contains no recognised
        polyline entities.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: if the DXF cannot be parsed.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"DXF file not found: {path}")

    import ezdxf  # local import; lets tests skip when ezdxf is absent.

    try:
        doc = ezdxf.readfile(path)
    except Exception as exc:  # ezdxf raises a variety of nested errors
        raise ValueError(f"Failed to parse DXF {path}: {exc}") from exc

    msp = doc.modelspace()
    polylines: list[list[tuple[float, float]]] = []
    for entity in msp:
        kind = entity.dxftype()
        if kind == "LWPOLYLINE":
            # get_points returns (x, y, start_width, end_width, bulge).
            pts = [
                (float(p[0]) * unit_scale, float(p[1]) * unit_scale)
                for p in entity.get_points()
            ]
            if len(pts) >= 2:
                polylines.append(pts)
        elif kind == "POLYLINE":
            pts = [
                (float(v.dxf.location.x) * unit_scale, float(v.dxf.location.y) * unit_scale)
                for v in entity.vertices
            ]
            if len(pts) >= 2:
                polylines.append(pts)
        elif kind == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            polylines.append(
                [
                    (float(start.x) * unit_scale, float(start.y) * unit_scale),
                    (float(end.x) * unit_scale, float(end.y) * unit_scale),
                ]
            )
    return polylines


__all__ = ["load_dxf_polylines", "load_mesh"]
