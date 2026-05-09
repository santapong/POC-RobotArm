"""Limits-aware path interpolator for vendor-neutral motion programs.

Produces a :class:`SampledPath` of :class:`Sample` tuples (t, q, flange_pose)
for any :class:`~src.motion.ir.Program`, with per-sample joint-velocity,
joint-acceleration, TCP-velocity, TCP-angular-velocity, and singularity checks.

Notes
-----
- All kinematics are in SI units (metres, radians, rad/s).
- Quaternions are (w, x, y, z). Re-canonicalised to w >= 0 after every slerp.
- ``spatialmath`` and ``roboticstoolbox`` are lazy-imported inside function
  bodies to keep the module importable without the full kinematics stack.
- Non-Move steps (IOOp, Wait, Comment) are silently skipped — document in
  calling code if you need to account for their durations.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import numpy as np

from src.motion.ir import (
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Program,
    check_quat,
)
from src.motion.limits import LimitViolation, assert_no_violations
from src.motion.manipulability import is_singular

if TYPE_CHECKING:  # pragma: no cover
    import roboticstoolbox as rtb


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sample:
    """A single timestep in a sampled path.

    Attributes
    ----------
    t_s:
        Time from the start of the path in seconds.
    q_rad:
        Joint positions in radians at this timestep.
    flange_xyz_m:
        Flange position (x, y, z) in metres in the robot base frame.
    flange_quat_wxyz:
        Flange orientation as a unit quaternion (w, x, y, z) in the robot base frame.
    flags:
        Optional string flags (e.g. ``"SINGULAR_NEAR"``).
    """

    t_s: float
    q_rad: tuple[float, ...]
    flange_xyz_m: tuple[float, float, float]
    flange_quat_wxyz: tuple[float, float, float, float]
    flags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if float(self.t_s) < 0.0:
            raise ValueError(f"Sample.t_s must be >= 0, got {self.t_s}")
        xyz_seq = tuple(self.flange_xyz_m)
        if len(xyz_seq) != 3:
            raise ValueError(
                f"Sample.flange_xyz_m must have 3 components (x, y, z), got {len(xyz_seq)}"
            )
        quat_seq = tuple(self.flange_quat_wxyz)
        if len(quat_seq) != 4:
            raise ValueError(
                f"Sample.flange_quat_wxyz must have 4 components (w, x, y, z), "
                f"got {len(quat_seq)}"
            )
        object.__setattr__(self, "q_rad", tuple(float(v) for v in self.q_rad))
        object.__setattr__(
            self,
            "flange_xyz_m",
            (float(xyz_seq[0]), float(xyz_seq[1]), float(xyz_seq[2])),
        )
        object.__setattr__(
            self,
            "flange_quat_wxyz",
            (
                float(quat_seq[0]),
                float(quat_seq[1]),
                float(quat_seq[2]),
                float(quat_seq[3]),
            ),
        )
        object.__setattr__(self, "flags", frozenset(self.flags))
        check_quat(self.flange_quat_wxyz, "Sample.flange_quat_wxyz")


@dataclass(frozen=True)
class SampledPath:
    """The output of :func:`interpolate_program`.

    Attributes
    ----------
    robot_name:
        Name of the robot model used.
    dt_s:
        Timestep between consecutive samples.
    samples:
        Ordered tuple of :class:`Sample` objects.
    move_boundaries:
        Index of the first sample belonging to each Move in the program.
    violations:
        Limit violations collected across all Moves.
    """

    robot_name: str
    dt_s: float
    samples: tuple[Sample, ...]
    move_boundaries: tuple[int, ...]
    violations: tuple[LimitViolation, ...] = ()

    def __post_init__(self) -> None:
        if float(self.dt_s) <= 0.0:
            raise ValueError(f"SampledPath.dt_s must be > 0, got {self.dt_s}")
        object.__setattr__(self, "samples", tuple(self.samples))
        object.__setattr__(self, "move_boundaries", tuple(self.move_boundaries))
        object.__setattr__(self, "violations", tuple(self.violations))
        for prev, nxt in zip(self.move_boundaries, self.move_boundaries[1:]):
            if nxt < prev:
                raise ValueError(
                    f"SampledPath.move_boundaries must be monotonic non-decreasing, "
                    f"got ..., {prev}, {nxt}, ..."
                )


# ---------------------------------------------------------------------------
# Trapezoidal profile
# ---------------------------------------------------------------------------


def _trapezoidal_profile(
    distance: float,
    v_max: float,
    a_max: float | None,
    dt_s: float,
) -> tuple[float, ...]:
    """Return a tuple of normalised arc-length values sampled at dt_s intervals.

    Computes the 1-D trapezoidal (or triangular) velocity profile for a move
    of the given ``distance`` at peak velocity ``v_max`` and optional
    acceleration ``a_max``. Returns a tuple of positions ``s[k]`` where
    ``s[0] = 0`` and ``s[-1] = distance``.

    Special case: ``distance == 0`` returns ``(0.0,)``.

    Args:
        distance: Total distance to travel.
        v_max: Peak velocity (same units as distance / second).
        a_max: Peak acceleration or ``None`` for constant-velocity profile.
        dt_s: Sampling interval in seconds.

    Returns:
        Tuple of arc-length samples from 0 to ``distance``.
    """
    if distance < 0.0:
        raise ValueError(f"_trapezoidal_profile: distance must be >= 0, got {distance}")
    if distance == 0.0:
        return (0.0,)

    if a_max is None:
        # Constant-velocity: pure ramp with no accel phase.
        T = distance / v_max
        n_steps = max(2, math.ceil(T / dt_s) + 1)
        out: list[float] = []
        for k in range(n_steps):
            t = k * dt_s
            s = min(v_max * t, distance)
            out.append(s)
        out[-1] = distance
        return tuple(out)

    t_acc = v_max / a_max
    d_acc = 0.5 * a_max * t_acc ** 2

    if 2.0 * d_acc <= distance:
        # Trapezoidal profile.
        t_cruise = (distance - 2.0 * d_acc) / v_max
        T = 2.0 * t_acc + t_cruise

        def _s(t: float) -> float:
            if t <= t_acc:
                return 0.5 * a_max * t ** 2
            elif t <= t_acc + t_cruise:
                return d_acc + v_max * (t - t_acc)
            else:
                return distance - 0.5 * a_max * (T - t) ** 2
    else:
        # Triangular profile — peak velocity never reached.
        v_peak = math.sqrt(distance * a_max)
        t_acc = v_peak / a_max
        T = 2.0 * t_acc

        def _s(t: float) -> float:  # type: ignore[misc]
            if t <= t_acc:
                return 0.5 * a_max * t ** 2
            else:
                return distance - 0.5 * a_max * (T - t) ** 2

    n_steps = max(2, math.ceil(T / dt_s) + 1)
    out = []
    for k in range(n_steps):
        t = k * dt_s
        s = max(0.0, min(distance, _s(t)))
        out.append(s)
    out[-1] = distance
    return tuple(out)


# ---------------------------------------------------------------------------
# Slerp
# ---------------------------------------------------------------------------


def _slerp_quat(
    q0: tuple[float, float, float, float],
    q1: tuple[float, float, float, float],
    t: float,
) -> tuple[float, float, float, float]:
    """Spherical linear interpolation between two unit quaternions.

    Canonicalises the result to w >= 0.

    Args:
        q0: Start quaternion (w, x, y, z).
        q1: End quaternion (w, x, y, z).
        t: Interpolation parameter in [0, 1].

    Returns:
        Interpolated quaternion (w, x, y, z) with w >= 0.
    """
    a0 = np.array(q0, dtype=float)
    a1 = np.array(q1, dtype=float)

    # Ensure shortest path.
    dot = float(np.dot(a0, a1))
    if dot < 0.0:
        a1 = -a1
        dot = -dot

    dot = min(1.0, dot)
    theta = math.acos(dot)

    if abs(theta) < 1e-12:
        result = a0 + t * (a1 - a0)
    else:
        s0 = math.sin((1.0 - t) * theta) / math.sin(theta)
        s1 = math.sin(t * theta) / math.sin(theta)
        result = s0 * a0 + s1 * a1

    # Normalise.
    norm = float(np.linalg.norm(result))
    if norm > 1e-12:
        result = result / norm

    w, x, y, z = float(result[0]), float(result[1]), float(result[2]), float(result[3])
    # Re-canonicalise to w >= 0.
    if w < 0.0:
        w, x, y, z = -w, -x, -y, -z
    return (w, x, y, z)


def _slerp_via(
    q0: tuple[float, float, float, float],
    q_via: tuple[float, float, float, float],
    q1: tuple[float, float, float, float],
    s: float,
    via_frac: float,
) -> tuple[float, float, float, float]:
    """Piecewise SLERP from q0 through q_via to q1.

    For s in [0, via_frac] interpolate q0 -> q_via; for s in (via_frac, 1]
    interpolate q_via -> q1. Used by ``_arc_fit_3pt`` so MOVE_C orientations
    actually pass through the via-point quaternion at its parametric arc
    fraction, matching ABB / KUKA / UR vendor semantics.
    """
    if s <= via_frac:
        local = s / via_frac if via_frac > 0.0 else 0.0
        return _slerp_quat(q0, q_via, local)
    span = 1.0 - via_frac
    local = (s - via_frac) / span if span > 0.0 else 1.0
    return _slerp_quat(q_via, q1, local)


# ---------------------------------------------------------------------------
# Arc fit for MOVE_C
# ---------------------------------------------------------------------------


def _arc_fit_3pt(
    p0: tuple[float, float, float],
    p_via: tuple[float, float, float],
    p1: tuple[float, float, float],
    q0: tuple[float, float, float, float],
    q_via: tuple[float, float, float, float],
    q1: tuple[float, float, float, float],
) -> tuple[Callable[[float], tuple[tuple[float, float, float], tuple[float, float, float, float]]], float]:
    """Fit a circular arc through three 3-D points and return a parametric curve.

    The curve is parameterised by normalised arc length s in [0, 1]:
    ``s=0`` -> p0/q0, ``s=0.5`` -> p_via/q_via (approximately), ``s=1`` -> p1/q1.

    Falls back to a linear blend if the points are collinear.

    Args:
        p0, p_via, p1: Three XYZ positions defining the arc.
        q0, q_via, q1: Corresponding quaternions for orientation slerp.

    Returns:
        A tuple of ``(curve_fn, arc_length)`` where ``curve_fn(s)`` returns
        ``(xyz, quat_wxyz)`` at normalised arc length ``s`` in [0, 1].
    """
    v0 = np.array(p0, dtype=float)
    v1 = np.array(p_via, dtype=float)
    v2 = np.array(p1, dtype=float)

    # Try to find the circle centre via circumscribed circle of the three points.
    a = v1 - v0
    b = v2 - v0
    cross = np.cross(a, b)
    cross_norm = float(np.linalg.norm(cross))

    if cross_norm < 1e-12:
        # Collinear: fall back to straight-line interpolation. Orientation
        # passes through q_via at the projected via fraction along the line.
        d_lin = float(np.linalg.norm(v2 - v0))
        if d_lin > 1e-12:
            via_frac = float(np.dot(v1 - v0, v2 - v0) / max(d_lin * d_lin, 1e-24))
            via_frac = min(1.0 - 1e-9, max(1e-9, via_frac))
        else:
            via_frac = 0.5

        def _linear(s: float) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
            xyz = tuple(float(v) for v in (v0 + s * (v2 - v0)))
            quat = _slerp_via(q0, q_via, q1, s, via_frac)
            return (xyz[0], xyz[1], xyz[2]), quat  # type: ignore[return-value]

        return _linear, max(d_lin, 1e-9)

    # Circumscribed circle centre in 3-D (on the plane of the three points).
    # Using the formula: centre = v0 + (|b|^2 * (a·b) * a - |a|^2 * (a·b) * b) / (2 |a×b|^2)
    # but the more robust approach is via linear system.
    # Normal to the plane.
    n = cross / cross_norm
    # Centre of circumscribed circle.
    aa = float(np.dot(a, a))
    bb = float(np.dot(b, b))
    ab = float(np.dot(a, b))
    denom = 2.0 * (aa * bb - ab * ab)
    if abs(denom) < 1e-24:
        d_lin = float(np.linalg.norm(v2 - v0))
        if d_lin > 1e-12:
            via_frac = float(np.dot(v1 - v0, v2 - v0) / max(d_lin * d_lin, 1e-24))
            via_frac = min(1.0 - 1e-9, max(1e-9, via_frac))
        else:
            via_frac = 0.5

        def _linear2(s: float) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
            xyz = tuple(float(v) for v in (v0 + s * (v2 - v0)))
            quat = _slerp_via(q0, q_via, q1, s, via_frac)
            return (xyz[0], xyz[1], xyz[2]), quat  # type: ignore[return-value]

        return _linear2, max(d_lin, 1e-9)

    mu = (bb * (aa - ab)) / denom
    lam = (aa * (bb - ab)) / denom
    centre = v0 + mu * a + lam * b
    radius = float(np.linalg.norm(v0 - centre))

    # Compute angles.
    r0 = v0 - centre
    r_via = v1 - centre
    r1 = v2 - centre

    theta_via = math.atan2(float(np.dot(np.cross(r0, r_via), n)), float(np.dot(r0, r_via)))
    theta_end = math.atan2(float(np.dot(np.cross(r0, r1), n)), float(np.dot(r0, r1)))

    # Ensure the arc sweeps through the via point.
    if theta_via < 0.0:
        theta_via += 2.0 * math.pi
    if theta_end <= 0.0:
        theta_end += 2.0 * math.pi

    arc_length = radius * abs(theta_end)
    if arc_length < 1e-9:
        arc_length = float(np.linalg.norm(v2 - v0))
        arc_length = max(arc_length, 1e-9)

    # Fraction of the parametric arc length at which the curve passes through
    # p_via — drives the piecewise SLERP transition for orientation.
    if abs(theta_end) > 1e-12:
        via_frac = float(theta_via / theta_end)
        via_frac = min(1.0 - 1e-9, max(1e-9, via_frac))
    else:
        via_frac = 0.5

    def _curve(s: float) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
        theta = s * theta_end
        # Rodrigues rotation of r0 by theta about n.
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        r = cos_t * r0 + sin_t * np.cross(n, r0) + (1.0 - cos_t) * float(np.dot(n, r0)) * n
        xyz = centre + r
        quat = _slerp_via(q0, q_via, q1, s, via_frac)
        return (float(xyz[0]), float(xyz[1]), float(xyz[2])), quat

    return _curve, arc_length


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fk_to_pose(robot: "rtb.Robot", q: np.ndarray) -> PoseTarget:
    """Run FK for robot at joint config q; return a PoseTarget in base frame."""
    T = robot.fkine(q)
    xyz = tuple(float(v) for v in T.t)
    from src.motion.frames import _rotmat_to_quat_wxyz
    quat = _rotmat_to_quat_wxyz(T.R)
    return PoseTarget(xyz_m=xyz, quat_wxyz=quat)


def _quat_angle(q0: tuple, q1: tuple) -> float:
    """Angle (radians) between two unit quaternions — in [0, pi]."""
    dot = abs(sum(a * b for a, b in zip(q0, q1)))
    dot = min(1.0, dot)
    return 2.0 * math.acos(dot)


def _time_sync(
    d_lin: float,
    v_lin: float,
    a_lin: float | None,
    d_ang: float,
    v_ang: float,
    a_ang: float | None,
    dt_s: float,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Compute time-synchronised profiles for linear and angular axes.

    The slower axis keeps its original limits; the faster axis is re-sampled
    at reduced v/a so both finish at the same time T_sync = max(T_lin, T_ang).

    Returns:
        (s_lin, s_ang) — two tuples of arc-length samples at dt_s intervals.
    """
    s_lin = _trapezoidal_profile(d_lin, v_lin, a_lin, dt_s)
    s_ang = _trapezoidal_profile(d_ang, v_ang, a_ang, dt_s)

    T_lin = (len(s_lin) - 1) * dt_s
    T_ang = (len(s_ang) - 1) * dt_s
    T_sync = max(T_lin, T_ang)

    if T_sync < dt_s:
        return s_lin, s_ang

    if T_lin < T_sync and d_lin > 0.0:
        scale = T_lin / T_sync
        v_lin_scaled = v_lin * scale
        a_lin_scaled = (a_lin * scale ** 2) if a_lin is not None else None
        s_lin = _trapezoidal_profile(d_lin, v_lin_scaled, a_lin_scaled, dt_s)

    if T_ang < T_sync and d_ang > 0.0:
        scale = T_ang / T_sync
        v_ang_scaled = v_ang * scale
        a_ang_scaled = (a_ang * scale ** 2) if a_ang is not None else None
        s_ang = _trapezoidal_profile(d_ang, v_ang_scaled, a_ang_scaled, dt_s)

    # Pad the shorter one to match length.
    n = max(len(s_lin), len(s_ang))
    if len(s_lin) < n:
        s_lin = s_lin + (d_lin,) * (n - len(s_lin))
    if len(s_ang) < n:
        s_ang = s_ang + (d_ang,) * (n - len(s_ang))

    return s_lin, s_ang


def _check_limits_for_samples(
    samples_list: list[Sample],
    robot: "rtb.Robot",
    dt_s: float,
    check_tcp: bool,
    v_tcp_limit: float | None,
    v_ang_limit: float | None,
) -> tuple[list[Sample], list[LimitViolation]]:
    """Apply per-sample velocity/accel/singularity checks; return updated samples and violations."""
    from src.robots.limits import JointLimits

    robot_limits: JointLimits | None = getattr(getattr(robot, "spec", None), "limits", None)

    violations: list[LimitViolation] = []
    updated = list(samples_list)

    n = len(updated)
    if n < 2:
        return updated, violations

    # Precompute joint velocity arrays.
    q_arr = np.array([s.q_rad for s in updated], dtype=float)

    for k in range(n - 1):
        dq = (q_arr[k + 1] - q_arr[k]) / dt_s  # per-joint velocity

        # JOINT_VELOCITY
        if robot_limits is not None:
            for i, (qdi, lim) in enumerate(zip(dq, robot_limits.qd_max_rad_s)):
                if abs(qdi) > lim * (1.0 + 1e-9):
                    violations.append(
                        LimitViolation(
                            error_code="JOINT_VELOCITY",
                            message=(
                                f"joint {i} velocity {qdi:.6f} rad/s exceeds limit "
                                f"{lim:.6f} rad/s at t={updated[k].t_s:.4f}s"
                            ),
                            joint_index=i,
                            requested=abs(qdi),
                            allowed=lim,
                        )
                    )

        # JOINT_ACCEL (requires k >= 1 so we have a previous velocity)
        if k >= 1 and robot_limits is not None and robot_limits.qdd_max_rad_s2 is not None:
            dq_prev = (q_arr[k] - q_arr[k - 1]) / dt_s
            ddq = (dq - dq_prev) / dt_s
            for i, (ddqi, lim) in enumerate(zip(ddq, robot_limits.qdd_max_rad_s2)):
                if abs(ddqi) > lim * (1.0 + 1e-9):
                    violations.append(
                        LimitViolation(
                            error_code="JOINT_ACCEL",
                            message=(
                                f"joint {i} acceleration {ddqi:.6f} rad/s² exceeds limit "
                                f"{lim:.6f} rad/s² at t={updated[k].t_s:.4f}s"
                            ),
                            joint_index=i,
                            requested=abs(ddqi),
                            allowed=lim,
                        )
                    )

        # TCP_VELOCITY
        if check_tcp and v_tcp_limit is not None:
            xyz_k = np.array(updated[k].flange_xyz_m)
            xyz_k1 = np.array(updated[k + 1].flange_xyz_m)
            v_lin = float(np.linalg.norm(xyz_k1 - xyz_k)) / dt_s
            if v_lin > v_tcp_limit * (1.0 + 1e-9):
                violations.append(
                    LimitViolation(
                        error_code="TCP_VELOCITY",
                        message=(
                            f"TCP linear velocity {v_lin:.6f} m/s exceeds limit "
                            f"{v_tcp_limit:.6f} m/s at t={updated[k].t_s:.4f}s"
                        ),
                        joint_index=None,
                        axis="linear",
                        requested=v_lin,
                        allowed=v_tcp_limit,
                    )
                )

        # TCP_ANGULAR_VELOCITY
        if check_tcp and v_ang_limit is not None:
            angle = _quat_angle(updated[k].flange_quat_wxyz, updated[k + 1].flange_quat_wxyz)
            v_ang = angle / dt_s
            if v_ang > v_ang_limit * (1.0 + 1e-9):
                violations.append(
                    LimitViolation(
                        error_code="TCP_ANGULAR_VELOCITY",
                        message=(
                            f"TCP angular velocity {v_ang:.6f} rad/s exceeds limit "
                            f"{v_ang_limit:.6f} rad/s at t={updated[k].t_s:.4f}s"
                        ),
                        joint_index=None,
                        axis="angular",
                        requested=v_ang,
                        allowed=v_ang_limit,
                    )
                )

    # SINGULARITY — check all samples. Catch only the numerical-failure
    # exception types we expect from rtb / numpy; let real bugs (AttributeError,
    # TypeError, etc.) propagate so they surface in tests rather than being
    # silently dropped.
    for k, s in enumerate(updated):
        q_k = np.array(s.q_rad, dtype=float)
        try:
            J = robot.jacob0(q_k)
        except (ValueError, np.linalg.LinAlgError):
            continue
        if is_singular(J, threshold=0.01):
            violations.append(
                LimitViolation(
                    error_code="SINGULARITY",
                    message=(
                        f"near-singular configuration at t={s.t_s:.4f}s "
                        f"(sample index {k})"
                    ),
                    joint_index=None,
                )
            )
            # Tag the sample.
            updated[k] = dataclasses.replace(s, flags=s.flags | {"SINGULAR_NEAR"})

    return updated, violations


# ---------------------------------------------------------------------------
# Per-move interpolator
# ---------------------------------------------------------------------------


def interpolate_move(
    move: Move,
    q_seed: np.ndarray,
    robot: "rtb.Robot",
    prev_pose: PoseTarget | None = None,
    *,
    dt_s: float,
    qd_default_rad_s: float | None = None,
) -> tuple[tuple[Sample, ...], list[LimitViolation]]:
    """Interpolate a single :class:`~src.motion.ir.Move` into time-sampled joint poses.

    Args:
        move: The Move instruction to interpolate.
        q_seed: Joint configuration seed for IK, shape ``(n,)``.
        robot: roboticstoolbox Robot instance.
        prev_pose: Flange pose at the end of the previous Move (base frame).
            Used as the start pose for MOVE_L / MOVE_C.
        dt_s: Sampling interval in seconds.
        qd_default_rad_s: Fallback joint velocity limit when the robot has no
            speed limits configured.

    Returns:
        A ``(samples, violations)`` pair.  ``samples`` may be empty if IK fails.
    """
    speed = move.speed
    v_tcp = speed.v_tcp_mm_s / 1000.0       # m/s
    a_tcp = (speed.a_tcp_mm_s2 / 1000.0) if speed.a_tcp_mm_s2 is not None else None
    v_ori = math.radians(speed.v_ori_deg_s)
    a_ori = math.radians(speed.a_ori_deg_s2) if speed.a_ori_deg_s2 is not None else None

    violations: list[LimitViolation] = []

    # ------------------------------------------------------------------
    # MOVE_ABS_J / MOVE_J with JointTarget
    # ------------------------------------------------------------------
    if move.kind == MoveKind.MOVE_ABS_J or (
        move.kind == MoveKind.MOVE_J and isinstance(move.target, JointTarget)
    ):
        target_q = np.array(move.target.q_rad, dtype=float)  # type: ignore[union-attr]
        start_q = q_seed
        n = robot.n

        # Per-joint trapezoidal profiles; pick slowest joint's time, time-stretch others.
        from src.robots.limits import JointLimits
        robot_limits: JointLimits | None = getattr(getattr(robot, "spec", None), "limits", None)

        deltas = np.abs(target_q - start_q)

        # Determine joint velocity limits.
        if robot_limits is not None:
            qd_lims = list(robot_limits.qd_max_rad_s)
            qdd_lims = (
                list(robot_limits.qdd_max_rad_s2) if robot_limits.qdd_max_rad_s2 is not None else None
            )
        elif qd_default_rad_s is not None:
            qd_lims = [qd_default_rad_s] * n
            qdd_lims = None
        else:
            # Use v_ori as a fallback for joint speed.
            qd_lims = [v_ori] * n
            qdd_lims = None

        # Compute per-joint profile durations.
        T_joints: list[float] = []
        for i, (delta, qd_i) in enumerate(zip(deltas, qd_lims)):
            if delta < 1e-12:
                T_joints.append(0.0)
                continue
            a_i = qdd_lims[i] if qdd_lims is not None else None
            s = _trapezoidal_profile(delta, qd_i, a_i, dt_s)
            T_joints.append((len(s) - 1) * dt_s)

        T = max(T_joints) if T_joints else 0.0

        if T < dt_s:
            # Instantaneous move — one sample at target.
            T_val = robot.fkine(target_q)
            from src.motion.frames import _rotmat_to_quat_wxyz
            quat = _rotmat_to_quat_wxyz(T_val.R)
            xyz = (float(T_val.t[0]), float(T_val.t[1]), float(T_val.t[2]))
            s0 = Sample(t_s=0.0, q_rad=tuple(float(v) for v in target_q), flange_xyz_m=xyz, flange_quat_wxyz=quat)
            return (s0,), violations

        # Build time-stretched profiles for each joint.
        n_steps = max(2, math.ceil(T / dt_s) + 1)
        q_traj = np.zeros((n_steps, n), dtype=float)
        for i, (delta, qd_i) in enumerate(zip(deltas, qd_lims)):
            a_i = qdd_lims[i] if qdd_lims is not None else None
            if T_joints[i] < 1e-12:
                # Joint doesn't move.
                q_traj[:, i] = target_q[i]
                continue
            scale = T_joints[i] / T
            v_scaled = qd_i * scale
            a_scaled = (a_i * scale ** 2) if a_i is not None else None
            s_i = _trapezoidal_profile(delta, v_scaled, a_scaled, dt_s)
            # Pad to n_steps.
            s_arr = list(s_i)
            while len(s_arr) < n_steps:
                s_arr.append(s_arr[-1])
            # Map arc length to actual joint position.
            direction = 1.0 if target_q[i] >= start_q[i] else -1.0
            for k in range(n_steps):
                q_traj[k, i] = start_q[i] + direction * s_arr[k]

        from src.motion.frames import _rotmat_to_quat_wxyz

        samples_list: list[Sample] = []
        for k in range(n_steps):
            q_k = q_traj[k]
            t_k = k * dt_s
            T_val = robot.fkine(q_k)
            quat = _rotmat_to_quat_wxyz(T_val.R)
            xyz = (float(T_val.t[0]), float(T_val.t[1]), float(T_val.t[2]))
            samples_list.append(
                Sample(
                    t_s=t_k,
                    q_rad=tuple(float(v) for v in q_k),
                    flange_xyz_m=xyz,
                    flange_quat_wxyz=quat,
                )
            )

        samples_list, viol = _check_limits_for_samples(
            samples_list, robot, dt_s, check_tcp=False, v_tcp_limit=None, v_ang_limit=None
        )
        violations.extend(viol)
        return tuple(samples_list), violations

    # ------------------------------------------------------------------
    # MOVE_J with PoseTarget — resolve to joint space via IK then joint ramp.
    # ------------------------------------------------------------------
    if move.kind == MoveKind.MOVE_J and isinstance(move.target, PoseTarget):
        from src.motion.frames import SE3_from_pose, resolve_pose_to_base

        resolved = resolve_pose_to_base(move.target, move.wobj, move.tool)
        T_target = SE3_from_pose(resolved)
        sol = robot.ikine_LM(T_target, q0=q_seed)
        if not sol.success:
            violations.append(
                LimitViolation(
                    error_code="JOINT_POSITION",
                    message="IK failed for MOVE_J target",
                    joint_index=None,
                )
            )
            return (), violations
        q_ik = np.array(sol.q, dtype=float)
        # Delegate to joint-space ramp by creating a synthetic MOVE_ABS_J.
        from src.motion.ir import Move as IRMove
        synthetic = IRMove(
            kind=MoveKind.MOVE_ABS_J,
            target=JointTarget(q_rad=tuple(float(v) for v in q_ik)),
            speed=move.speed,
            zone=move.zone,
            tool=move.tool,
            wobj=move.wobj,
        )
        return interpolate_move(synthetic, q_seed, robot, prev_pose=prev_pose, dt_s=dt_s,
                                qd_default_rad_s=qd_default_rad_s)

    # ------------------------------------------------------------------
    # MOVE_L — Cartesian linear interpolation.
    # ------------------------------------------------------------------
    if move.kind == MoveKind.MOVE_L:
        from src.motion.frames import SE3_from_pose, _rotmat_to_quat_wxyz, resolve_pose_to_base

        # Resolve start and target to base frame.
        start_pose = prev_pose if prev_pose is not None else _fk_to_pose(robot, q_seed)
        target_resolved = resolve_pose_to_base(move.target, move.wobj, move.tool)  # type: ignore[arg-type]

        xyz_start = np.array(start_pose.xyz_m, dtype=float)
        xyz_end = np.array(target_resolved.xyz_m, dtype=float)
        q_start = start_pose.quat_wxyz
        q_end = target_resolved.quat_wxyz

        d_lin = float(np.linalg.norm(xyz_end - xyz_start))
        d_ang = _quat_angle(q_start, q_end)

        s_lin, s_ang = _time_sync(d_lin, v_tcp, a_tcp, d_ang, v_ori, a_ori, dt_s)
        n_steps = max(len(s_lin), len(s_ang))

        # Normalise both to same length.
        if len(s_lin) < n_steps:
            s_lin = s_lin + (d_lin,) * (n_steps - len(s_lin))
        if len(s_ang) < n_steps:
            s_ang = s_ang + (d_ang,) * (n_steps - len(s_ang))

        from src.motion.ir import Move as IRMove
        samples_list = []
        q_prev = q_seed.copy()

        for k in range(n_steps):
            alpha_lin = (s_lin[k] / d_lin) if d_lin > 1e-12 else 1.0
            alpha_ang = (s_ang[k] / d_ang) if d_ang > 1e-12 else 1.0
            xyz_k = xyz_start + alpha_lin * (xyz_end - xyz_start)
            quat_k = _slerp_quat(q_start, q_end, alpha_ang)

            target_k = PoseTarget(
                xyz_m=(float(xyz_k[0]), float(xyz_k[1]), float(xyz_k[2])),
                quat_wxyz=quat_k,
            )
            T_k = SE3_from_pose(target_k)
            sol = robot.ikine_LM(T_k, q0=q_prev)
            if not sol.success:
                violations.append(
                    LimitViolation(
                        error_code="JOINT_POSITION",
                        message=f"IK failed during MOVE_L at t={k * dt_s:.4f}s (sample {k})",
                        joint_index=None,
                    )
                )
                break
            q_k = np.array(sol.q, dtype=float)
            q_prev = q_k
            samples_list.append(
                Sample(
                    t_s=k * dt_s,
                    q_rad=tuple(float(v) for v in q_k),
                    flange_xyz_m=(float(xyz_k[0]), float(xyz_k[1]), float(xyz_k[2])),
                    flange_quat_wxyz=quat_k,
                )
            )

        samples_list, viol = _check_limits_for_samples(
            samples_list, robot, dt_s,
            check_tcp=True,
            v_tcp_limit=v_tcp,
            v_ang_limit=v_ori,
        )
        violations.extend(viol)
        return tuple(samples_list), violations

    # ------------------------------------------------------------------
    # MOVE_C — circular arc.
    # ------------------------------------------------------------------
    if move.kind == MoveKind.MOVE_C:
        from src.motion.frames import SE3_from_pose, _rotmat_to_quat_wxyz, resolve_pose_to_base

        start_pose = prev_pose if prev_pose is not None else _fk_to_pose(robot, q_seed)
        via_resolved = resolve_pose_to_base(move.circ_via, move.wobj, move.tool)  # type: ignore[arg-type]
        target_resolved = resolve_pose_to_base(move.target, move.wobj, move.tool)  # type: ignore[arg-type]

        curve_fn, arc_length = _arc_fit_3pt(
            start_pose.xyz_m,
            via_resolved.xyz_m,
            target_resolved.xyz_m,
            start_pose.quat_wxyz,
            via_resolved.quat_wxyz,
            target_resolved.quat_wxyz,
        )

        q_start_quat = start_pose.quat_wxyz
        q_end_quat = target_resolved.quat_wxyz
        d_ang = _quat_angle(q_start_quat, q_end_quat)

        s_lin, s_ang = _time_sync(arc_length, v_tcp, a_tcp, d_ang, v_ori, a_ori, dt_s)
        n_steps = max(len(s_lin), len(s_ang))
        if len(s_lin) < n_steps:
            s_lin = s_lin + (arc_length,) * (n_steps - len(s_lin))
        if len(s_ang) < n_steps:
            s_ang = s_ang + (d_ang,) * (n_steps - len(s_ang))

        samples_list = []
        q_prev = q_seed.copy()

        for k in range(n_steps):
            s_norm = (s_lin[k] / arc_length) if arc_length > 1e-12 else 1.0
            xyz_k, quat_k = curve_fn(s_norm)

            target_k = PoseTarget(xyz_m=xyz_k, quat_wxyz=quat_k)
            T_k = SE3_from_pose(target_k)
            sol = robot.ikine_LM(T_k, q0=q_prev)
            if not sol.success:
                violations.append(
                    LimitViolation(
                        error_code="JOINT_POSITION",
                        message=f"IK failed during MOVE_C at t={k * dt_s:.4f}s (sample {k})",
                        joint_index=None,
                    )
                )
                break
            q_k = np.array(sol.q, dtype=float)
            q_prev = q_k
            samples_list.append(
                Sample(
                    t_s=k * dt_s,
                    q_rad=tuple(float(v) for v in q_k),
                    flange_xyz_m=xyz_k,
                    flange_quat_wxyz=quat_k,
                )
            )

        samples_list, viol = _check_limits_for_samples(
            samples_list, robot, dt_s,
            check_tcp=True,
            v_tcp_limit=v_tcp,
            v_ang_limit=v_ori,
        )
        violations.extend(viol)
        return tuple(samples_list), violations

    # Should not happen — IR validates move kinds.
    raise ValueError(f"Unsupported MoveKind in interpolate_move: {move.kind}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Program-level interpolator
# ---------------------------------------------------------------------------


def interpolate_program(
    prog: Program,
    robot: "rtb.Robot",
    *,
    dt_s: float = 0.01,
    qd_default_rad_s: float | None = None,
    raise_on_violation: bool = True,
) -> SampledPath:
    """Interpolate an entire :class:`~src.motion.ir.Program` into a :class:`SampledPath`.

    Walks the ``"main"`` procedure of ``prog``, interpolating each Move and
    collecting violations. Non-Move steps (IOOp, Wait, Comment) are skipped.

    Args:
        prog: The program to interpolate.
        robot: roboticstoolbox Robot used for FK, IK, and Jacobian queries.
        dt_s: Sampling interval in seconds. Must be > 0.
        qd_default_rad_s: Fallback joint velocity limit when the robot has no
            limits configured. Pass ``None`` to use the speed from the Move.
        raise_on_violation: If ``True`` (default), raise :class:`LimitsExceeded`
            when any violations are collected. If ``False``, return them in
            :attr:`SampledPath.violations`.

    Returns:
        A :class:`SampledPath` with all samples concatenated.

    Raises:
        ValueError: if ``dt_s <= 0`` or the program has no ``"main"`` procedure.
        LimitsExceeded: if violations are found and ``raise_on_violation=True``.

    Example::

        >>> path = interpolate_program(prog, robot, dt_s=0.02)
        >>> print(f"{len(path.samples)} samples, {path.samples[-1].t_s:.2f}s total")
    """
    if dt_s <= 0.0:
        raise ValueError(f"dt_s must be > 0, got {dt_s}")

    # Locate the "main" procedure.
    proc_map = {p.name: p for p in prog.procedures}
    if "main" not in proc_map:
        raise KeyError("Program has no 'main' procedure")
    procedure = proc_map["main"]

    # Seed joint configuration from robot.q if non-zero.
    if np.any(robot.q != 0.0):
        current_q = np.array(robot.q, dtype=float)
    else:
        current_q = np.zeros(robot.n, dtype=float)

    current_flange_pose: PoseTarget | None = None

    all_samples: list[Sample] = []
    move_boundaries: list[int] = []
    all_violations: list[LimitViolation] = []
    t_offset = 0.0

    for step in procedure.body:
        if not isinstance(step, Move):
            # IOOp, Wait, Comment — silently skipped; their durations are not modelled.
            continue

        samples, viols = interpolate_move(
            step,
            current_q,
            robot,
            prev_pose=current_flange_pose,
            dt_s=dt_s,
            qd_default_rad_s=qd_default_rad_s,
        )

        if samples:
            boundary = len(all_samples)
            move_boundaries.append(boundary)

            for s in samples:
                all_samples.append(
                    dataclasses.replace(s, t_s=s.t_s + t_offset)
                )

            last = all_samples[-1]
            current_q = np.array(last.q_rad, dtype=float)
            current_flange_pose = PoseTarget(
                xyz_m=last.flange_xyz_m,
                quat_wxyz=last.flange_quat_wxyz,
            )
            t_offset = last.t_s + dt_s

        all_violations.extend(viols)

    path = SampledPath(
        robot_name=robot.name,
        dt_s=dt_s,
        samples=tuple(all_samples),
        move_boundaries=tuple(move_boundaries),
        violations=tuple(all_violations),
    )

    if raise_on_violation and all_violations:
        assert_no_violations(list(all_violations))

    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "Sample",
    "SampledPath",
    "_arc_fit_3pt",
    "_slerp_quat",
    "_trapezoidal_profile",
    "interpolate_move",
    "interpolate_program",
]
