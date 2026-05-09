"""Manipulability metrics for robot kinematics.

Provides the Yoshikawa manipulability index and a singularity test derived
from it. These are extracted from the optimizer to be reusable across the
path-calculation pipeline.

Notes
-----
- The Yoshikawa index is ``sqrt(det(J Jᵀ))`` for a full-rank Jacobian.
- Returns ``0.0`` on any degenerate or non-finite input rather than raising, so
  callers can treat 0.0 uniformly as "singular / degenerate".
- ``is_singular`` uses a configurable threshold defaulting to 0.01.
"""

from __future__ import annotations

import math

import numpy as np

_DEFAULT_MANIPULABILITY_THRESHOLD: float = 0.01

__all__ = ["is_singular", "yoshikawa"]


def yoshikawa(jacobian: np.ndarray) -> float:
    """Compute the Yoshikawa manipulability index.

    Args:
        jacobian: The (m × n) robot Jacobian matrix.

    Returns:
        ``sqrt(det(J Jᵀ))``, or ``0.0`` if the Jacobian is degenerate, empty,
        not 2-dimensional, or produces a non-finite or non-positive determinant.

    Example::

        >>> import numpy as np
        >>> J = np.eye(3)
        >>> yoshikawa(J)  # doctest: +ELLIPSIS
        1.0...
    """
    J = np.asarray(jacobian, dtype=float)
    if J.ndim != 2 or 0 in J.shape:
        return 0.0
    M = J @ J.T
    det = float(np.linalg.det(M))
    if not math.isfinite(det) or det <= 0.0:
        return 0.0
    return math.sqrt(det)


def is_singular(
    jacobian: np.ndarray,
    threshold: float = _DEFAULT_MANIPULABILITY_THRESHOLD,
) -> bool:
    """Return True if the Jacobian is (near-)singular.

    Args:
        jacobian: The robot Jacobian matrix.
        threshold: Manipulability values below this are treated as singular.
            Defaults to :data:`_DEFAULT_MANIPULABILITY_THRESHOLD` (0.01).

    Returns:
        ``True`` when ``yoshikawa(jacobian) < threshold``.

    Example::

        >>> import numpy as np
        >>> is_singular(np.zeros((3, 3)))
        True
    """
    return yoshikawa(jacobian) < threshold
