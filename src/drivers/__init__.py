"""Vendor-neutral robot driver layer.

Public API:

* :class:`Driver` — Protocol every backend implements.
* :class:`RobotState` — immutable state snapshot returned by ``Driver.get_state``.
* :class:`SimDriver` — adapter wrapping the existing PyBullet ``SimBridge``.
* :class:`SimSampledPathDriver` — proxy that routes moves through the path interpolator.
* :class:`RWSDriver` — online ABB Robot Web Services driver.
"""

from src.drivers.abb.rws_client import RWSDriver
from src.drivers.base import Driver, RobotState
from src.drivers.sim.sim_driver import SimDriver
from src.drivers.sim.sim_sampled_path import SimSampledPathDriver

__all__ = ["Driver", "RWSDriver", "RobotState", "SimDriver", "SimSampledPathDriver"]
