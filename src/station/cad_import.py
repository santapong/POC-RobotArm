"""CAD import helpers for the station scene-graph.

This module wraps :mod:`trimesh` for STL / OBJ / PLY meshes and
:mod:`ezdxf` for DXF polylines. Both imports are deferred to function /
method scope so that importing :mod:`src.station.scene` (and the rest of
the station package) does not pull these heavy CAD dependencies. Tests
and headless tooling that don't need CAD therefore stay light.

DXF files are by convention millimetres; the loader converts to metres
to match the rest of the codebase, which is uniformly SI.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — type-check only
    import trimesh as _trimesh_types  # noqa: F401

# Recognised mesh extensions (lower-case, leading dot).
_MESH_EXTENSIONS: tuple[str, ...] = (".stl", ".obj", ".ply")
# DXF default unit is mm; we always convert to metres on read.
_MM_TO_M = 1.0e-3


def load_mesh(path: str) -> Any:
    """Load a triangle mesh from ``path`` and return a ``trimesh.Trimesh``.

    Supported file extensions: ``.stl``, ``.obj``, ``.ply``. The
    :mod:`trimesh` import is deferred so this module is safely importable
    even without trimesh installed.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If the extension is unsupported, or if trimesh returns a non-mesh
        result (e.g. a Scene or Path), which the caller likely did not
        expect.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Mesh file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in _MESH_EXTENSIONS:
        raise ValueError(
            f"Unsupported mesh extension {ext!r}; expected one of {_MESH_EXTENSIONS}"
        )

    import trimesh  # local import — keeps module import light

    mesh = trimesh.load_mesh(path)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(
            f"trimesh.load_mesh({path!r}) returned {type(mesh).__name__}, "
            "expected a Trimesh"
        )
    return mesh


def load_dxf(path: str) -> list[list[tuple[float, float]]]:
    """Load 2D polylines from a DXF file.

    Returns a list of polylines, each polyline being a list of
    ``(x_m, y_m)`` tuples in *metres*. DXF input is assumed to be in
    millimetres (the AutoCAD default for mechanical drawings) and is
    converted on the fly.

    Both ``LINE``, ``LWPOLYLINE``, and ``POLYLINE`` entities in modelspace
    are converted into polylines: a ``LINE`` becomes a 2-point polyline,
    while polylines are emitted with their full vertex list.

    The :mod:`ezdxf` import is deferred so this module is safely
    importable without ezdxf installed.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"DXF file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext != ".dxf":
        raise ValueError(f"Unsupported DXF extension {ext!r}; expected '.dxf'")

    import ezdxf  # local import — keeps module import light

    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    polylines: list[list[tuple[float, float]]] = []
    for entity in msp:
        kind = entity.dxftype()
        if kind == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            polylines.append(
                [
                    (float(start[0]) * _MM_TO_M, float(start[1]) * _MM_TO_M),
                    (float(end[0]) * _MM_TO_M, float(end[1]) * _MM_TO_M),
                ]
            )
        elif kind == "LWPOLYLINE":
            pts: list[tuple[float, float]] = []
            for x, y, *_rest in entity.get_points("xy"):
                pts.append((float(x) * _MM_TO_M, float(y) * _MM_TO_M))
            if entity.closed and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            if len(pts) >= 2:
                polylines.append(pts)
        elif kind == "POLYLINE":
            pts = []
            for vertex in entity.vertices:
                loc = vertex.dxf.location
                pts.append((float(loc[0]) * _MM_TO_M, float(loc[1]) * _MM_TO_M))
            if entity.is_closed and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            if len(pts) >= 2:
                polylines.append(pts)
        # Other DXF entity kinds (CIRCLE, ARC, SPLINE, ...) are ignored
        # in this Phase-1 importer — they need flattening into segments
        # which is out of scope here.

    return polylines


__all__ = ["load_dxf", "load_mesh"]
