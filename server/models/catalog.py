"""Pydantic v2 model for the robot catalog entry exposed to the browser."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class RobotCatalogEntry(BaseModel):
    """Browser-facing representation of a robot from the catalog.

    Notes
    -----
    - ``vendor`` is derived from the robot name by a prefix-matching map in
      the catalog router (panda→Franka, ur5→Universal Robots, etc.).
    - ``urdf_url`` is the browser ``GET`` URL for the robot's URDF; served via
      ``GET /api/assets/urdf/{robot}/{file:path}``.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    dof: int
    vendor: str
    urdf_url: str
    ee_link_name: Optional[str]
    home_q: tuple[float, ...]
    description: str
    qd_max_rad_s: tuple[float, ...] | None
    qdd_max_rad_s2: tuple[float, ...] | None


__all__ = ["RobotCatalogEntry"]
