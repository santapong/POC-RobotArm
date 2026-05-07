"""Vendor-neutral robot driver layer.

Public API:

* :class:`Driver` — Protocol every backend implements.
* :class:`RobotState` — immutable state snapshot returned by ``Driver.get_state``.
* :class:`SimDriver` — adapter wrapping the existing PyBullet ``SimBridge``.
"""

from src.drivers.base import Driver, RobotState
from src.drivers.sim.sim_driver import SimDriver

__all__ = ["Driver", "RobotState", "SimDriver"]
