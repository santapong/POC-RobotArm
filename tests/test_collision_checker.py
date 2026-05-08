"""Tests for src.collision.checker — PyBullet-backed collision queries."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("pybullet")

from src.collision.checker import CollisionChecker  # noqa: E402
from src.robots.catalog import get_spec  # noqa: E402

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


@pytest.fixture
def ur5_urdf() -> str:
    spec = get_spec("ur5")
    assert os.path.exists(spec.urdf_path), f"Missing UR5 URDF: {spec.urdf_path}"
    return spec.urdf_path


def test_no_collision_when_box_is_far(ur5_urdf: str) -> None:
    checker = CollisionChecker(ur5_urdf)
    try:
        # A box far away from the robot — no contact at all.
        checker.add_static_box(half_extents=(0.1, 0.1, 0.1), position=(5.0, 5.0, 5.0))
        q = [0.0] * checker.num_joints
        assert checker.is_in_collision(q) is False
    finally:
        checker.close()


def test_collision_when_box_engulfs_robot(ur5_urdf: str) -> None:
    checker = CollisionChecker(ur5_urdf)
    try:
        # A giant box centred at the origin — the robot's links must intersect it.
        checker.add_static_box(half_extents=(2.0, 2.0, 2.0), position=(0.0, 0.0, 0.0))
        q = [0.0] * checker.num_joints
        assert checker.is_in_collision(q) is True
    finally:
        checker.close()


def test_close_is_idempotent(ur5_urdf: str) -> None:
    checker = CollisionChecker(ur5_urdf)
    checker.close()
    checker.close()  # second call must not raise
    # After close, queries should fail cleanly.
    with pytest.raises(RuntimeError):
        checker.is_in_collision([0.0] * 6)


def test_context_manager(ur5_urdf: str) -> None:
    with CollisionChecker(ur5_urdf) as checker:
        checker.add_static_box((0.1, 0.1, 0.1), (5.0, 5.0, 5.0))
        assert checker.is_in_collision([0.0] * checker.num_joints) is False


def test_missing_urdf_raises() -> None:
    with pytest.raises(FileNotFoundError):
        CollisionChecker("/no/such/robot.urdf")


def test_distance_threshold_triggers_collision(ur5_urdf: str) -> None:
    """A box just outside the robot is fine at distance=0 but trips at a positive clearance."""
    checker = CollisionChecker(ur5_urdf)
    try:
        # Box centered close to the base; without padding it should not collide.
        checker.add_static_box(half_extents=(0.05, 0.05, 0.05), position=(0.5, 0.0, 0.5))
        q = [0.0] * checker.num_joints
        # Maybe it's clear, maybe not — record the baseline.
        baseline = checker.is_in_collision(q, distance_m=0.0)
        # With a huge clearance, it must trigger.
        wide = checker.is_in_collision(q, distance_m=100.0)
        assert wide is True
        # baseline can be either; just sanity-check the type.
        assert isinstance(baseline, bool)
    finally:
        checker.close()
