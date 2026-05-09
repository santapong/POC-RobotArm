"""Tests for Yoshikawa manipulability index and is_singular helper."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from src.motion.manipulability import (  # noqa: E402
    _DEFAULT_MANIPULABILITY_THRESHOLD,
    is_singular,
    yoshikawa,
)

# ---------------------------------------------------------------------------
# yoshikawa
# ---------------------------------------------------------------------------


def test_yoshikawa_identity_jacobian_returns_one():
    """6×6 identity → det(I·Iᵀ) = det(I) = 1 → sqrt(1) = 1."""
    result = yoshikawa(np.eye(6))
    assert abs(result - 1.0) <= 1e-12


def test_yoshikawa_zero_jacobian_returns_zero():
    result = yoshikawa(np.zeros((6, 6)))
    assert result == 0.0


def test_yoshikawa_rank_deficient_returns_zero():
    """Two equal rows → rank deficient → det = 0 → yoshikawa = 0."""
    J = np.zeros((3, 6))
    J[0] = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    J[1] = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # duplicate row
    J[2] = [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    result = yoshikawa(J)
    assert result == 0.0


def test_yoshikawa_nonsquare_well_conditioned():
    """3×6 Jacobian with full row rank → positive finite manipulability."""
    rng = np.random.default_rng(42)
    J = rng.standard_normal((3, 6))
    result = yoshikawa(J)
    assert result > 0.0
    assert math.isfinite(result)


def test_yoshikawa_empty_returns_zero():
    result = yoshikawa(np.zeros((0, 0)))
    assert result == 0.0


def test_yoshikawa_one_dim_returns_zero():
    """1-D array is not 2-D → returns 0.0 defensively."""
    result = yoshikawa(np.array([1.0, 2.0, 3.0]))
    assert result == 0.0


# ---------------------------------------------------------------------------
# is_singular
# ---------------------------------------------------------------------------


def test_is_singular_above_threshold_returns_false():
    """Eye(6) → yoshikawa = 1.0, threshold = 0.5 → not singular."""
    assert is_singular(np.eye(6), threshold=0.5) is False


def test_is_singular_below_threshold_returns_true():
    """Scaled identity: yoshikawa(0.1 * I6) = 0.1^6 = 1e-6 < 0.01 → singular."""
    J = np.eye(6) * 0.1
    result = yoshikawa(J)
    assert result < 0.01
    assert is_singular(J) is True


def test_is_singular_default_threshold_value():
    """The internal constant must equal 0.01 (optimizer compatibility)."""
    assert _DEFAULT_MANIPULABILITY_THRESHOLD == 0.01
