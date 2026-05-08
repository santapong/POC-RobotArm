"""Toolpath operations — generate :class:`PoseTarget` waypoints from geometry.

Three primitives mirror the standard CAM operation taxonomy:

* :func:`polyline_follow` — trace an explicit 3D polyline (the user
  already chose the orientation; we just attach a constant approach quat).
* :func:`curve_on_surface` — sample a chain of mesh edges, with each
  waypoint's tool-Z aligned with the inward surface normal.
* :func:`surface_raster` — slice a mesh with parallel planes, stitch the
  resulting contours into a serpentine path, and align tool-Z with the
  inward normal.

All operations return ``list[PoseTarget]`` in the IR's SI units (meters /
unit-norm wxyz quaternions). The orientation convention is "tool points
into the work" — i.e. the tool +Z axis is anti-parallel to the outward
surface normal.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from src.motion.ir import PoseTarget

if TYPE_CHECKING:  # pragma: no cover - typing only
    import trimesh as _trimesh  # noqa: F401


# Numerical guards for vector normalization.
_EPS = 1.0e-9


# ---------------------------------------------------------------------------
# Quaternion helpers
# ---------------------------------------------------------------------------


def _rotmat_to_quat_wxyz(R: np.ndarray) -> tuple[float, float, float, float]:
    """Convert a 3x3 rotation matrix to a unit-norm ``(w, x, y, z)`` tuple.

    Implementation: Shepperd's method (numerically stable for any
    orientation). We keep this hand-rolled to avoid pulling scipy into
    the import path of every consumer of the toolpath package.
    """
    m00, m01, m02 = R[0, 0], R[0, 1], R[0, 2]
    m10, m11, m12 = R[1, 0], R[1, 1], R[1, 2]
    m20, m21, m22 = R[2, 0], R[2, 1], R[2, 2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif (m00 > m11) and (m00 > m22):
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm < _EPS:
        return (1.0, 0.0, 0.0, 0.0)
    return (w / norm, x / norm, y / norm, z / norm)


def _quat_from_tool_z(
    z_dir: Sequence[float],
    x_hint: Sequence[float] | None = None,
) -> tuple[float, float, float, float]:
    """Build a unit quaternion such that the tool-Z axis points along ``z_dir``.

    The returned orientation has its +X picked from ``x_hint`` (projected
    out of ``z``); when ``x_hint`` is parallel to ``z`` we fall back to a
    deterministic alternative axis. This keeps consecutive waypoints
    smoothly oriented.
    """
    z = np.asarray(z_dir, dtype=float)
    n = float(np.linalg.norm(z))
    if n < _EPS:
        # Degenerate — return identity rather than crash.
        return (1.0, 0.0, 0.0, 0.0)
    z = z / n

    if x_hint is None:
        # Pick a stable seed: world +X unless that's parallel to z.
        if abs(z[0]) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        else:
            seed = np.array([1.0, 0.0, 0.0])
    else:
        seed = np.asarray(x_hint, dtype=float)
        if np.linalg.norm(seed) < _EPS:
            seed = np.array([1.0, 0.0, 0.0])
        seed = seed / np.linalg.norm(seed)
        # Fall back if seed happens to be parallel to z.
        if abs(float(np.dot(seed, z))) > 1.0 - 1e-6:
            seed = np.array([0.0, 1.0, 0.0]) if abs(z[1]) < 0.9 else np.array([0.0, 0.0, 1.0])

    x_axis = seed - np.dot(seed, z) * z
    nx = float(np.linalg.norm(x_axis))
    if nx < _EPS:
        # Final fallback — should be unreachable given the seed selection.
        x_axis = np.array([1.0, 0.0, 0.0])
    else:
        x_axis = x_axis / nx
    y_axis = np.cross(z, x_axis)
    R = np.column_stack((x_axis, y_axis, z))
    return _rotmat_to_quat_wxyz(R)


# ---------------------------------------------------------------------------
# polyline_follow
# ---------------------------------------------------------------------------


def polyline_follow(
    points_m: Sequence[Sequence[float]],
    approach_quat_wxyz: Sequence[float] = (0.0, 0.0, 1.0, 0.0),
) -> list[PoseTarget]:
    """Convert a sequence of 3D points into Cartesian waypoints.

    Each waypoint shares the same orientation ``approach_quat_wxyz``
    (default points the tool-Z down: a 180-degree rotation about world X).

    Args:
        points_m: Iterable of ``(x, y, z)`` tuples in meters.
        approach_quat_wxyz: Constant orientation, unit-norm wxyz.

    Returns:
        A list of :class:`PoseTarget`, one per input point.

    Raises:
        ValueError: if any input point doesn't have 3 components.
    """
    quat = tuple(float(c) for c in approach_quat_wxyz)
    out: list[PoseTarget] = []
    for i, p in enumerate(points_m):
        coords = tuple(float(c) for c in p)
        if len(coords) != 3:
            raise ValueError(f"polyline_follow: point {i} must have 3 components, got {coords}")
        out.append(PoseTarget(xyz_m=coords, quat_wxyz=quat))
    return out


# ---------------------------------------------------------------------------
# curve_on_surface
# ---------------------------------------------------------------------------


def _normal_at_point(mesh: Any, point: np.ndarray) -> np.ndarray:
    """Return the (outward) face normal of the face closest to ``point``."""
    from trimesh.proximity import ProximityQuery
    pq = ProximityQuery(mesh)
    _, _, face_ids = pq.on_surface(point.reshape(1, 3))
    fid = int(face_ids[0])
    n = np.asarray(mesh.face_normals[fid], dtype=float)
    return n


def curve_on_surface(
    mesh: Any,
    edge_loop_indices: Sequence[int],
    samples: int,
    normal_offset_m: float = 0.0,
) -> list[PoseTarget]:
    """Sample a chain of mesh vertices and align tool-Z to the inward normal.

    Args:
        mesh: A :class:`trimesh.Trimesh`.
        edge_loop_indices: Ordered vertex indices defining the curve. Each
            consecutive pair forms an edge that is sampled; ``samples``
            controls the number of waypoints generated **across the
            entire chain** (not per edge).
        samples: Total number of waypoints to produce. Must be >= 2.
        normal_offset_m: Distance to offset along the outward normal at
            each waypoint (positive values move *away* from the surface,
            useful for non-contact processes like inspection or laser).

    Returns:
        A list of :class:`PoseTarget` with tool-Z anti-parallel to the
        outward face normal at each sample.

    Raises:
        ValueError: if the chain has fewer than 2 indices or if any
            index is out of bounds.
    """
    if samples < 2:
        raise ValueError(f"curve_on_surface: samples must be >= 2, got {samples}")
    indices = list(edge_loop_indices)
    if len(indices) < 2:
        raise ValueError("curve_on_surface: edge_loop_indices needs at least 2 vertices")

    verts = np.asarray(mesh.vertices, dtype=float)
    n_verts = len(verts)
    for v in indices:
        if v < 0 or v >= n_verts:
            raise ValueError(
                f"curve_on_surface: vertex index {v} out of range [0,{n_verts})"
            )

    # Compute cumulative arc length along the polyline of vertices.
    chain = verts[indices]
    seg = np.diff(chain, axis=0)
    seg_lens = np.linalg.norm(seg, axis=1)
    total = float(seg_lens.sum())
    if total < _EPS:
        raise ValueError("curve_on_surface: chain has zero length")
    cum = np.concatenate(([0.0], np.cumsum(seg_lens)))

    out: list[PoseTarget] = []
    prev_x_axis: np.ndarray | None = None
    for k in range(samples):
        s = (k / (samples - 1)) * total
        # Find segment containing arc-length s.
        j = int(np.searchsorted(cum, s, side="right") - 1)
        j = max(0, min(j, len(seg) - 1))
        seg_start = cum[j]
        seg_end = cum[j + 1]
        if seg_end - seg_start < _EPS:
            t_local = 0.0
        else:
            t_local = (s - seg_start) / (seg_end - seg_start)
        point = chain[j] * (1.0 - t_local) + chain[j + 1] * t_local
        normal = _normal_at_point(mesh, point)
        offset_pt = point + normal * float(normal_offset_m)
        # Tool +Z is the inward direction (-normal).
        tool_z = -normal
        # Use the previous X axis (projected) as a hint to keep continuity.
        hint = prev_x_axis if prev_x_axis is not None else None
        quat = _quat_from_tool_z(tool_z.tolist(), hint.tolist() if hint is not None else None)
        out.append(
            PoseTarget(
                xyz_m=tuple(float(v) for v in offset_pt),
                quat_wxyz=quat,
            )
        )
        # Record this waypoint's X axis for the next iteration.
        # Recover X by re-running the construction (cheap; few floats).
        z = tool_z / max(float(np.linalg.norm(tool_z)), _EPS)
        seed = (
            hint
            if hint is not None and abs(float(np.dot(hint, z))) < 1.0 - 1e-6
            else (np.array([1.0, 0.0, 0.0]) if abs(z[0]) <= 0.9 else np.array([0.0, 1.0, 0.0]))
        )
        x_axis = seed - np.dot(seed, z) * z
        nx = float(np.linalg.norm(x_axis))
        if nx >= _EPS:
            prev_x_axis = x_axis / nx
    return out


# ---------------------------------------------------------------------------
# surface_raster
# ---------------------------------------------------------------------------


def _stitch_alternate(rows: list[np.ndarray]) -> np.ndarray:
    """Stitch a list of per-row point arrays into a serpentine sequence.

    Each ``row`` is a ``(K, 3)`` array of ordered points. Even-indexed
    rows are kept as-is; odd-indexed rows are reversed so the path
    snakes back and forth — that's the canonical raster pattern.
    """
    out: list[np.ndarray] = []
    for i, row in enumerate(rows):
        if row.shape[0] == 0:
            continue
        out.append(row if (i % 2 == 0) else row[::-1])
    if not out:
        return np.empty((0, 3), dtype=float)
    return np.concatenate(out, axis=0)


def _order_segments_along_axis(
    segments: np.ndarray,
    axis: np.ndarray,
) -> np.ndarray:
    """Order intersection segments along an axis to form a continuous row.

    ``trimesh.intersections.mesh_plane`` returns an unordered set of line
    segments ``(N, 2, 3)`` for each slicing plane. For a convex slice
    they form a path; we sort the unique endpoints by their projection
    on the in-plane axis, which is good enough for the simple boxes /
    sheets used in the demo and unit tests.
    """
    if segments.size == 0:
        return np.empty((0, 3), dtype=float)
    # Flatten endpoints, dedupe within tolerance, then sort along axis.
    pts = segments.reshape(-1, 3)
    # Round to avoid floating-point noise when deduping.
    rounded = np.round(pts, 6)
    _, unique_idx = np.unique(rounded, axis=0, return_index=True)
    pts = pts[np.sort(unique_idx)]
    keys = pts @ axis
    order = np.argsort(keys)
    return pts[order]


def surface_raster(
    mesh: Any,
    plane_normal: Sequence[float],
    plane_origin: Sequence[float],
    step_m: float,
    normal_offset_m: float = 0.0,
) -> list[PoseTarget]:
    """Generate raster waypoints by slicing the mesh with parallel planes.

    The function slices ``mesh`` with planes perpendicular to
    ``plane_normal``, spaced ``step_m`` apart, spanning the mesh's
    extent along that direction. Each slice is reduced to an ordered
    polyline; alternate rows are reversed to produce a serpentine path.

    Args:
        mesh: :class:`trimesh.Trimesh`.
        plane_normal: 3-vector — the slicing plane's normal (also the
            raster step direction).
        plane_origin: 3-vector — a point on the *first* slicing plane.
        step_m: Distance between consecutive slicing planes (meters).
        normal_offset_m: Distance to offset each waypoint along the
            outward surface normal at that point (positive = away).

    Returns:
        A list of :class:`PoseTarget` along the raster path. Empty list
        if the mesh doesn't intersect any slicing plane.

    Raises:
        ValueError: ``step_m <= 0`` or ``plane_normal`` is degenerate.
    """
    if step_m <= 0.0:
        raise ValueError(f"surface_raster: step_m must be > 0, got {step_m}")
    n_dir = np.asarray(plane_normal, dtype=float)
    n_norm = float(np.linalg.norm(n_dir))
    if n_norm < _EPS:
        raise ValueError("surface_raster: plane_normal is zero")
    n_dir = n_dir / n_norm
    origin = np.asarray(plane_origin, dtype=float)

    import trimesh as _tm  # local: keeps top-of-file import cost low

    # Determine the slicing range along the plane normal from the mesh AABB.
    bounds = np.asarray(mesh.bounds, dtype=float)  # (2, 3): min, max
    corners = np.array(
        [
            [bounds[i, 0], bounds[j, 1], bounds[k, 2]]
            for i in (0, 1)
            for j in (0, 1)
            for k in (0, 1)
        ]
    )
    proj = (corners - origin) @ n_dir
    s_min = float(proj.min())
    s_max = float(proj.max())
    if s_max - s_min < _EPS:
        return []

    # Build the in-plane orthonormal frame for "ordering points along a row".
    seed = np.array([1.0, 0.0, 0.0]) if abs(n_dir[0]) <= 0.9 else np.array([0.0, 1.0, 0.0])
    u_axis = seed - np.dot(seed, n_dir) * n_dir
    nu = float(np.linalg.norm(u_axis))
    if nu < _EPS:
        u_axis = np.array([0.0, 1.0, 0.0])
    else:
        u_axis = u_axis / nu

    rows: list[np.ndarray] = []
    s = s_min
    while s <= s_max + _EPS:
        plane_org = origin + n_dir * s
        section = _tm.intersections.mesh_plane(
            mesh,
            plane_normal=n_dir,
            plane_origin=plane_org,
        )
        # ``mesh_plane`` may return a list of (2, 3) segments or an array.
        seg = np.asarray(section, dtype=float)
        ordered = _order_segments_along_axis(seg, u_axis)
        rows.append(ordered)
        s += step_m

    path = _stitch_alternate(rows)
    if path.shape[0] == 0:
        return []

    out: list[PoseTarget] = []
    prev_x_axis: np.ndarray | None = None
    for pt in path:
        normal = _normal_at_point(mesh, pt)
        offset_pt = pt + normal * float(normal_offset_m)
        tool_z = -normal
        quat = _quat_from_tool_z(
            tool_z.tolist(),
            prev_x_axis.tolist() if prev_x_axis is not None else None,
        )
        out.append(
            PoseTarget(
                xyz_m=tuple(float(v) for v in offset_pt),
                quat_wxyz=quat,
            )
        )
        z = tool_z / max(float(np.linalg.norm(tool_z)), _EPS)
        seed_x = (
            prev_x_axis
            if prev_x_axis is not None and abs(float(np.dot(prev_x_axis, z))) < 1.0 - 1e-6
            else (np.array([1.0, 0.0, 0.0]) if abs(z[0]) <= 0.9 else np.array([0.0, 1.0, 0.0]))
        )
        x_axis = seed_x - np.dot(seed_x, z) * z
        nx = float(np.linalg.norm(x_axis))
        if nx >= _EPS:
            prev_x_axis = x_axis / nx
    return out


__all__ = ["curve_on_surface", "polyline_follow", "surface_raster"]
