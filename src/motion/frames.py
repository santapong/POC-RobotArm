"""TCP/RTCP-aware frame composition helpers.

Provides utilities for resolving Cartesian targets between tool, workobject,
and robot-base frames, with correct handling of both TCP (tool-on-robot) and
RTCP (tool-fixed, part-on-robot) motion modes.

Notes
-----
- ``FrameMode.TCP``:  standard — tool is robot-held, workobject is world-fixed.
- ``FrameMode.RTCP``: inverted — part/wobj is robot-held, tool is world-fixed.
- ``spatialmath`` is lazy-imported to keep the module importable in environments
  without the kinematics stack installed (import fails at call time, not at
  module load).
- ``resolve_frame_to_root`` adapts to ``Station.frames`` being a ``tuple``; it
  builds a name-keyed lookup dict internally.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from src.motion.ir import PoseTarget, ToolData, WObjData

if TYPE_CHECKING:
    from src.station.scene import Station


# ---------------------------------------------------------------------------
# Frame mode enum
# ---------------------------------------------------------------------------


class FrameMode(str, Enum):
    """Motion frame mode: TCP (tool on robot) or RTCP (part on robot)."""

    TCP = "TCP"
    RTCP = "RTCP"


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


def quat_wxyz_to_rotmat(q: Sequence[float]) -> np.ndarray:
    """Convert a unit-norm wxyz quaternion to a 3×3 rotation matrix.

    Uses Shepperd's method (closed-form, no branch singularities for unit
    quaternions).

    Args:
        q: Sequence of four floats ``(w, x, y, z)``.

    Returns:
        A ``(3, 3)`` float64 array.

    Raises:
        ValueError: if ``len(q) < 4``.
    """
    if len(q) < 4:
        raise ValueError("quaternion must have 4 components")
    w, x, y, z = (float(c) for c in q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def SE3_from_pose(target: PoseTarget) -> Any:
    """Build a spatialmath SE3 from a :class:`~src.motion.ir.PoseTarget`.

    Args:
        target: Cartesian target containing ``xyz_m`` and ``quat_wxyz``.

    Returns:
        A ``spatialmath.SE3`` instance.
    """
    from spatialmath import SE3

    R = quat_wxyz_to_rotmat(target.quat_wxyz)
    return SE3.Rt(R, np.asarray(target.xyz_m, dtype=float))


# ---------------------------------------------------------------------------
# Frame mode derivation
# ---------------------------------------------------------------------------


def derive_frame_mode(tool: ToolData, wobj: WObjData) -> FrameMode:
    """Infer the motion frame mode from ``tool.robhold`` and ``wobj.robhold``.

    Args:
        tool: Tool definition (see ``ToolData.robhold``).
        wobj: Workobject definition (see ``WObjData.robhold``).

    Returns:
        ``FrameMode.TCP`` when the tool is robot-held and the workobject is
        world-fixed; ``FrameMode.RTCP`` for the inverse configuration.

    Raises:
        ValueError: if both or neither of ``tool.robhold`` / ``wobj.robhold``
            are ``True``.
    """
    if tool.robhold and not wobj.robhold:
        return FrameMode.TCP
    if not tool.robhold and wobj.robhold:
        return FrameMode.RTCP
    if tool.robhold and wobj.robhold:
        raise ValueError(
            "Both tool and wobj are flagged robhold=True; "
            "exactly one of tool/wobj may be robot-held"
        )
    raise ValueError(
        "Neither tool nor wobj is flagged robhold; "
        "exactly one must be robot-held"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _rotmat_to_quat_wxyz(R: np.ndarray) -> tuple[float, float, float, float]:
    """Convert a 3×3 rotation matrix to a wxyz quaternion (w >= 0 canonical)."""
    # Standard formula via the trace.
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0.0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s

    # Canonicalise sign so w >= 0.
    if w < 0.0:
        w, x, y, z = -w, -x, -y, -z

    return (float(w), float(x), float(y), float(z))


def _check_ortho(R: np.ndarray, label: str) -> None:
    """Raise ValueError if R is not a proper rotation matrix (det≈1, R Rᵀ≈I)."""
    det_err = abs(float(np.linalg.det(R)) - 1.0)
    orth_err = float(np.linalg.norm(R @ R.T - np.eye(3)))
    if det_err > 1e-9 or orth_err > 1e-9:
        raise ValueError(
            f"{label} produced a non-orthogonal rotation; inputs may be malformed"
        )


# ---------------------------------------------------------------------------
# Pose resolution
# ---------------------------------------------------------------------------


def resolve_pose_to_base(
    pose: PoseTarget,
    wobj: WObjData,
    tool: ToolData,
    mode: FrameMode | None = None,
) -> PoseTarget:
    """Resolve a target expressed in the wobj/tool frame to the robot base frame.

    Computes the flange pose in the robot base frame given a Cartesian target
    ``pose`` expressed in the workobject's object frame.

    Derivation (TCP mode):

        ``T_base_flange = T_user * T_obj * T_pose * T_tool⁻¹``

    Derivation (RTCP mode) — fixed external tool, robot holds the part via the
    wobj chain.  Setting "held part in world via held-wobj chain" equal to
    "held part in world via fixed external tool" and solving for the flange pose:

        ``T_base_flange = T_user⁻¹ * T_obj⁻¹ * T_tool * T_pose``

    Args:
        pose: Target in object-frame coordinates.
        wobj: Workobject (defines user and object sub-frames).
        tool: Tool definition (TCP offset and robhold flag).
        mode: Override frame mode; auto-derived from ``tool``/``wobj`` if None.

    Returns:
        A new :class:`~src.motion.ir.PoseTarget` with ``xyz_m``/``quat_wxyz``
        expressed in the robot base frame; ``config`` and ``ext_axes_rad`` are
        forwarded unchanged from ``pose``.

    Raises:
        ValueError: if the computed rotation matrix is non-orthogonal (inputs
            malformed), or if ``derive_frame_mode`` fails.
    """
    from spatialmath import SE3

    if mode is None:
        mode = derive_frame_mode(tool, wobj)

    T_tool = SE3.Rt(quat_wxyz_to_rotmat(tool.tcp_quat_wxyz), np.asarray(tool.tcp_xyz_m, dtype=float))
    T_user = SE3.Rt(quat_wxyz_to_rotmat(wobj.user_quat_wxyz), np.asarray(wobj.user_xyz_m, dtype=float))
    T_obj = SE3.Rt(quat_wxyz_to_rotmat(wobj.base_quat_wxyz), np.asarray(wobj.base_xyz_m, dtype=float))
    T_pose = SE3_from_pose(pose)

    if mode is FrameMode.TCP:
        flange_T_base = T_user * T_obj * T_pose * T_tool.inv()
    else:  # RTCP
        flange_T_base = T_user.inv() * T_obj.inv() * T_tool * T_pose

    R = flange_T_base.R
    _check_ortho(R, "resolve_pose_to_base")

    xyz = tuple(float(v) for v in flange_T_base.t)
    quat = _rotmat_to_quat_wxyz(R)

    return PoseTarget(
        xyz_m=xyz,
        quat_wxyz=quat,
        config=pose.config,
        ext_axes_rad=pose.ext_axes_rad,
    )


def forward_resolve(
    flange_in_base: PoseTarget,
    wobj: WObjData,
    tool: ToolData,
    mode: FrameMode | None = None,
) -> PoseTarget:
    """Inverse of :func:`resolve_pose_to_base`: recover the object-frame target.

    Given the flange pose in the robot base frame, compute the corresponding
    target in the workobject's object frame.

    TCP:  ``T_pose = T_obj⁻¹ * T_user⁻¹ * T_flange * T_tool``
    RTCP: ``T_pose = T_tool⁻¹ * T_obj * T_user * T_flange``

    Args:
        flange_in_base: Flange pose expressed in the robot base frame.
        wobj: Workobject definition.
        tool: Tool definition.
        mode: Override frame mode; auto-derived if None.

    Returns:
        A new :class:`~src.motion.ir.PoseTarget` in object-frame coordinates.

    Raises:
        ValueError: if the computed rotation matrix is non-orthogonal.
    """
    from spatialmath import SE3

    if mode is None:
        mode = derive_frame_mode(tool, wobj)

    T_tool = SE3.Rt(quat_wxyz_to_rotmat(tool.tcp_quat_wxyz), np.asarray(tool.tcp_xyz_m, dtype=float))
    T_user = SE3.Rt(quat_wxyz_to_rotmat(wobj.user_quat_wxyz), np.asarray(wobj.user_xyz_m, dtype=float))
    T_obj = SE3.Rt(quat_wxyz_to_rotmat(wobj.base_quat_wxyz), np.asarray(wobj.base_xyz_m, dtype=float))
    T_flange = SE3_from_pose(flange_in_base)

    if mode is FrameMode.TCP:
        T_pose = T_obj.inv() * T_user.inv() * T_flange * T_tool
    else:  # RTCP
        T_pose = T_tool.inv() * T_obj * T_user * T_flange

    R = T_pose.R
    _check_ortho(R, "forward_resolve")

    xyz = tuple(float(v) for v in T_pose.t)
    quat = _rotmat_to_quat_wxyz(R)

    return PoseTarget(
        xyz_m=xyz,
        quat_wxyz=quat,
        config=flange_in_base.config,
        ext_axes_rad=flange_in_base.ext_axes_rad,
    )


# ---------------------------------------------------------------------------
# Scene-graph helper
# ---------------------------------------------------------------------------


def resolve_frame_to_root(
    scene: "Station",
    name: str,
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """Walk the scene-graph parent chain and return the frame's world pose.

    Accumulates SE3 transforms from the root of the chain down to the named
    frame, producing a single world-frame pose.

    Args:
        scene: Station containing the flat frame registry.
        name: Name of the frame to resolve.

    Returns:
        ``((x, y, z), (w, x, y, z))`` — translation in metres and unit
        quaternion, both canonicalised (w >= 0).

    Raises:
        ValueError: if ``name`` is not found, a referenced parent is missing,
            or the parent chain contains a cycle.
    """
    from spatialmath import SE3

    # Build a name-keyed lookup from the tuple.  Station.frames is a
    # ``tuple[Frame, ...]``; we build the dict lazily here rather than assuming
    # it is already a mapping (which it is not in the current schema).
    frames_dict = {f.name: f for f in scene.frames}

    if name not in frames_dict:
        raise ValueError(f"unknown frame {name!r}")

    visited: set[str] = set()
    chain = []
    cur = frames_dict.get(name)
    while cur is not None:
        if cur.name in visited:
            raise ValueError(f"cycle in scene graph at {cur.name!r}")
        visited.add(cur.name)
        chain.append(cur)
        if cur.parent is None:
            break
        nxt = frames_dict.get(cur.parent)
        if nxt is None:
            raise ValueError(
                f"frame {cur.name!r} references unknown parent {cur.parent!r}"
            )
        cur = nxt

    # Fold root-first: chain[-1] is the root, chain[0] is the target frame.
    T = SE3()  # identity
    for frame in reversed(chain):
        R = quat_wxyz_to_rotmat(frame.quat_wxyz)
        T = T * SE3.Rt(R, np.asarray(frame.xyz_m, dtype=float))

    xyz = (float(T.t[0]), float(T.t[1]), float(T.t[2]))
    quat = _rotmat_to_quat_wxyz(T.R)

    return (xyz, quat)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "FrameMode",
    "SE3_from_pose",
    "derive_frame_mode",
    "forward_resolve",
    "quat_wxyz_to_rotmat",
    "resolve_frame_to_root",
    "resolve_pose_to_base",
]
