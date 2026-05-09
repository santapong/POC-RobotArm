"""Joint-space velocity and acceleration limit data model.

A frozen dataclass that captures per-joint speed caps sourced from robot
datasheets. Used by the limit-validation layer in ``src.motion.limits``.

Notes
-----
- All values are in SI units (rad/s, rad/s²).
- ``qdd_max_rad_s2`` is optional; many vendors publish only velocity limits.
- Validation is strict: every element must be strictly positive.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["JointLimits"]


@dataclass(frozen=True)
class JointLimits:
    """Per-joint velocity (and optionally acceleration) limits.

    Args:
        qd_max_rad_s: Maximum joint velocity for each joint (rad/s). Must be
            non-empty and all values strictly positive.
        qdd_max_rad_s2: Maximum joint acceleration for each joint (rad/s²).
            If provided, must match the length of ``qd_max_rad_s`` and all
            values must be strictly positive. ``None`` means limits are
            unspecified (not checked).
    """

    qd_max_rad_s: tuple[float, ...]
    qdd_max_rad_s2: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        # Coerce qd_max_rad_s to tuple of float via object.__setattr__ (frozen).
        coerced_qd = tuple(float(v) for v in self.qd_max_rad_s)
        object.__setattr__(self, "qd_max_rad_s", coerced_qd)

        if len(self.qd_max_rad_s) == 0:
            raise ValueError("JointLimits.qd_max_rad_s must not be empty")

        for i, v in enumerate(self.qd_max_rad_s):
            if v <= 0.0:
                raise ValueError(
                    f"JointLimits.qd_max_rad_s[{i}] must be > 0, got {v}"
                )

        if self.qdd_max_rad_s2 is not None:
            coerced_qdd = tuple(float(v) for v in self.qdd_max_rad_s2)
            object.__setattr__(self, "qdd_max_rad_s2", coerced_qdd)

            if len(self.qdd_max_rad_s2) != len(self.qd_max_rad_s):
                raise ValueError(
                    "JointLimits.qdd_max_rad_s2 length must match qd_max_rad_s"
                )

            for i, v in enumerate(self.qdd_max_rad_s2):
                if v <= 0:
                    raise ValueError(
                        f"JointLimits.qdd_max_rad_s2[{i}] must be > 0, got {v}"
                    )
