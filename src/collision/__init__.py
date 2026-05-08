"""Collision-checking utilities backed by PyBullet.

This package exposes a single class — :class:`CollisionChecker` — that
spawns a headless PyBullet client, loads a robot URDF and a list of
static scene meshes, and answers binary collision queries for given
joint configurations.

Use it from the toolpath pipeline to filter out joint configurations
that would graze the workpiece, fixtures, or other parts of the cell.
"""

from __future__ import annotations

from src.collision.checker import CollisionChecker

__all__ = ["CollisionChecker"]
