"""Vendor-neutral robot driver layer.

Public API:

* :class:`Driver` — Protocol every backend implements.
* :class:`RobotState` — immutable state snapshot returned by ``Driver.get_state``.
* :class:`SimDriver` — adapter wrapping the existing PyBullet ``SimBridge``.
* :class:`RWSDriver` — online ABB Robot Web Services driver.
"""

from src.drivers.abb.rws_client import RWSDriver
from src.drivers.base import Driver, RobotState
from src.drivers.sim.sim_driver import SimDriver

__all__ = ["Driver", "RWSDriver", "RobotState", "SimDriver"]
