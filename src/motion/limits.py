"""Structured limit-validation layer for robot motion.

Validates joint positions and singularity proximity for motion IR instructions.
Emits structured :class:`LimitViolation` records which are aggregated into
:class:`LimitsExceeded` exceptions.

Notes
-----
- PR-A validates: joint position bounds (MOVE_ABS_J / MOVE_J with JointTarget),
  and singularity (when ``jacobian_fn`` is provided and a JointTarget is available).
- Joint-velocity projection for MOVE_L is reserved for PR-B.
- Error codes are validated against ``_VALID_CODES`` so PR-B can add new codes
  without changing the base dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.motion.ir import JointTarget, MoveKind, PoseTarget

__all__ = [
    "LimitViolation",
    "LimitsExceeded",
    "assert_no_violations",
    "validate_move",
]

# ---------------------------------------------------------------------------
# Valid error codes (PR-A + slots reserved for PR-B)
# ---------------------------------------------------------------------------

_VALID_CODES: frozenset[str] = frozenset(
    {
        "JOINT_POSITION",
        "JOINT_VELOCITY",
        "JOINT_ACCEL",
        "TCP_VELOCITY",
        "TCP_ANGULAR_VELOCITY",
        "TCP_ACCEL",
        "SINGULARITY",
        "RTCP_INVALID",
        "TCP_INVALID",
    }
)

_VALID_AXES: frozenset[str | None] = frozenset({None, "linear", "angular"})


# ---------------------------------------------------------------------------
# LimitViolation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LimitViolation:
    """A single limit violation record.

    Args:
        error_code: One of the strings in ``_VALID_CODES``.
        message: Human-readable description of the violation.
        joint_index: Which joint triggered the violation, or ``None`` for
            whole-move violations (singularity, TCP speed, etc.).
        axis: ``None``, ``"linear"``, or ``"angular"`` — discriminates between
            translational and rotational limit types where applicable.
        requested: The actual value that violated the limit (in SI or IR units).
        allowed: The limit value that was exceeded.
    """

    error_code: str
    message: str
    joint_index: int | None = None
    axis: str | None = None
    requested: float | None = None
    allowed: float | None = None

    def __post_init__(self) -> None:
        if self.error_code not in _VALID_CODES:
            raise ValueError(
                f"LimitViolation.error_code {self.error_code!r} is not a recognised code; "
                f"valid codes: {sorted(_VALID_CODES)}"
            )
        if self.axis not in _VALID_AXES:
            raise ValueError(
                f"LimitViolation.axis must be None, 'linear', or 'angular'; "
                f"got {self.axis!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict, including ``None`` values."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "joint_index": self.joint_index,
            "axis": self.axis,
            "requested": self.requested,
            "allowed": self.allowed,
        }


# ---------------------------------------------------------------------------
# LimitsExceeded
# ---------------------------------------------------------------------------


class LimitsExceeded(Exception):
    """Raised when one or more limit violations are detected.

    Args:
        violations: Non-empty sequence of :class:`LimitViolation` records.

    The ``str()`` representation joins individual violation messages with
    ``"; "``.
    """

    def __init__(self, violations: list[LimitViolation]) -> None:
        self._violations: list[LimitViolation] = list(violations)
        super().__init__(str(self))

    @property
    def violations(self) -> list[LimitViolation]:
        """Shallow copy of the violation list."""
        return list(self._violations)

    def __str__(self) -> str:
        return "; ".join(v.message for v in self._violations)


# ---------------------------------------------------------------------------
# validate_move
# ---------------------------------------------------------------------------


def validate_move(
    move_kind: str,
    target: JointTarget | PoseTarget,
    robot_qlim: list[tuple[float, float]] | None = None,
    speed: Any = None,
    robot_limits: Any = None,
    jacobian_fn: Callable[[tuple[float, ...]], Any] | None = None,
    singularity_threshold: float = 0.01,
) -> list[LimitViolation]:
    """Validate a single move instruction and return any violations found.

    PR-A checks (in order):

    1. **Joint position** — for ``MOVE_ABS_J`` and ``MOVE_J`` with a
       :class:`~src.motion.ir.JointTarget`, verify each joint lies within
       ``robot_qlim``.  A joint-count mismatch emits a single
       ``JOINT_POSITION`` violation and skips per-joint checks.
    2. **Singularity** — when ``jacobian_fn`` is provided and a
       :class:`~src.motion.ir.JointTarget` is available, compute the
       Yoshikawa index and flag if below ``singularity_threshold``.

    PR-B reserved slots (JOINT_VELOCITY, JOINT_ACCEL, TCP_VELOCITY,
    TCP_ANGULAR_VELOCITY, TCP_ACCEL, RTCP_INVALID, TCP_INVALID) are present in
    ``_VALID_CODES`` but not checked here.

    Args:
        move_kind: One of the :class:`~src.motion.ir.MoveKind` string values
            (e.g. ``"MOVE_ABS_J"``, ``"MOVE_J"``, ``"MOVE_L"``).
        target: The move target — a :class:`~src.motion.ir.JointTarget` or
            :class:`~src.motion.ir.PoseTarget`.
        robot_qlim: Per-joint ``(min_rad, max_rad)`` pairs.  ``None`` means
            position checks are skipped entirely.
        speed: :class:`~src.motion.ir.SpeedData` (reserved for PR-B; ignored
            in PR-A).
        robot_limits: :class:`~src.robots.limits.JointLimits` (reserved for
            PR-B; ignored in PR-A).
        jacobian_fn: Callable that takes a joint-position tuple ``(q_rad,)``
            and returns the Jacobian matrix.  ``None`` skips singularity checks.
        singularity_threshold: Yoshikawa index below which the configuration is
            considered singular.  Defaults to 0.01.

    Returns:
        A (possibly empty) list of :class:`LimitViolation` records.
    """
    from src.motion.manipulability import yoshikawa

    violations: list[LimitViolation] = []

    # Determine whether we have a JointTarget to validate.
    joint_target: JointTarget | None = None
    if isinstance(target, JointTarget):
        joint_target = target

    mk = move_kind  # shorthand

    # ------------------------------------------------------------------
    # 1. Joint position checks (MOVE_ABS_J and MOVE_J with JointTarget)
    # ------------------------------------------------------------------
    if mk in (MoveKind.MOVE_ABS_J.value, MoveKind.MOVE_J.value) and joint_target is not None:
        if robot_qlim is not None:
            n_move = len(joint_target.q_rad)
            n_robot = len(robot_qlim)
            if n_move != n_robot:
                violations.append(
                    LimitViolation(
                        error_code="JOINT_POSITION",
                        message=(
                            f"joint count mismatch: move has {n_move} joints, "
                            f"robot expects {n_robot}"
                        ),
                        joint_index=None,
                    )
                )
            else:
                for i, (q, (lo, hi)) in enumerate(zip(joint_target.q_rad, robot_qlim)):
                    if q < lo or q > hi:
                        violations.append(
                            LimitViolation(
                                error_code="JOINT_POSITION",
                                message=(
                                    f"joint {i} position {q:.6f} rad out of limits "
                                    f"[{lo:.6f}, {hi:.6f}] rad"
                                ),
                                joint_index=i,
                                requested=q,
                                allowed=hi if q > hi else lo,
                            )
                        )

    # ------------------------------------------------------------------
    # 2. Singularity check
    # ------------------------------------------------------------------
    if jacobian_fn is not None and joint_target is not None:
        try:
            J = jacobian_fn(joint_target.q_rad)
            m = yoshikawa(J)
            if m < singularity_threshold:
                violations.append(
                    LimitViolation(
                        error_code="SINGULARITY",
                        message=(
                            f"configuration is near-singular "
                            f"(manipulability={m:.6f} < threshold={singularity_threshold})"
                        ),
                        joint_index=None,
                        requested=m,
                        allowed=singularity_threshold,
                    )
                )
        except Exception:
            # Jacobian computation failure is not a limit violation; propagate
            # only if the caller explicitly wants errors to surface.
            pass

    return violations


# ---------------------------------------------------------------------------
# assert_no_violations
# ---------------------------------------------------------------------------


def assert_no_violations(violations: list[LimitViolation]) -> None:
    """Raise :class:`LimitsExceeded` if the violation list is non-empty.

    Args:
        violations: Result of :func:`validate_move` (or a manually assembled
            list).

    Raises:
        LimitsExceeded: when ``len(violations) > 0``.
    """
    if violations:
        raise LimitsExceeded(violations)
