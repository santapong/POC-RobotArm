"""Robot models.

Top-level imports kept minimal so the simulator path (``src.robots.catalog``)
is importable without the heavyweight ``roboticstoolbox`` dependency. Use
``from src.robots.predefined import ...`` to reach the rtb-backed code.
"""

from src.robots.limits import JointLimits

__all__ = ["JointLimits"]
