"""Vendor-neutral robot Driver Protocol.

This module defines the contract that every robot backend (PyBullet sim,
ABB IRC5, future vendors) must satisfy. Call-site code in motion planning,
post-processing, and the LLM tool layer should depend on the ``Driver``
Protocol rather than any concrete class so that swapping sim for real
hardware is a one-line change.

Design notes
------------
* ``Driver`` is a :pep:`544` ``Protocol`` (not an ABC). Any object whose
  attributes and methods match the structural interface satisfies it,
  which keeps duck-typed adapters simple. The ``@runtime_checkable``
  decorator additionally enables ``isinstance(obj, Driver)`` checks for
  defensive call-sites.
* Pose conventions: positions in metres, angles in radians, quaternions in
  ``(w, x, y, z)`` order in the robot base frame. This is the canonical
  internal format; backends translate to/from their native representation
  (e.g. PyBullet uses ``xyzw``, ABB uses ``[w, x, y, z]`` already).
* Motion args (``speed_frac``, ``blend_m``) are honoured by real drivers
  and tolerated by the simulator (which simply ignores them).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class RobotState:
    """Immutable snapshot of a robot's instantaneous state.

    Attributes
    ----------
    joints_rad:
        Tuple of joint positions in radians, length equal to the robot's DOF.
    tcp_xyz_m:
        Tool-centre-point position ``(x, y, z)`` in metres, expressed in the
        robot base frame.
    tcp_quat_wxyz:
        Tool-centre-point orientation as a unit quaternion in ``(w, x, y, z)``
        order, expressed in the robot base frame.
    moving:
        ``True`` if the robot is currently executing a motion (queued
        trajectory, blended path, single move-in-progress).
    error:
        Vendor error string when the controller has latched a fault, else
        ``None``. The format is backend-specific; consumers should treat it
        as opaque diagnostic text.
    """

    joints_rad: tuple[float, ...]
    tcp_xyz_m: tuple[float, float, float]
    tcp_quat_wxyz: tuple[float, float, float, float]
    moving: bool
    error: Optional[str] = None


@runtime_checkable
class Driver(Protocol):
    """Vendor-neutral robot interface. Same calls work for sim and real hardware."""

    name: str
    """Stable identifier, e.g. ``"sim:panda"`` or ``"abb:irb1200@192.168.0.10"``."""

    dof: int
    """Number of controllable joints (excludes gripper / fingers)."""

    def connect(self) -> None:
        """Establish the connection to the controller (or attach to the sim)."""
        ...

    def disconnect(self) -> None:
        """Tear down the controller connection cleanly. Idempotent."""
        ...

    def is_connected(self) -> bool:
        """Return ``True`` once :meth:`connect` has succeeded and the link is live."""
        ...

    def get_state(self) -> RobotState:
        """Return the current :class:`RobotState` snapshot in canonical units."""
        ...

    def move_joint(
        self,
        q_rad: Sequence[float],
        speed_frac: float = 0.5,
        blend_m: float = 0.0,
        wait: bool = True,
    ) -> None:
        """Command a joint-space move to ``q_rad`` (one entry per joint, radians).

        ``speed_frac`` is a 0..1 fraction of the controller's vmax, ``blend_m``
        is the blend-zone radius in metres (0 means a fine stop). When ``wait``
        is ``True`` this method blocks until motion completes.
        """
        ...

    def move_linear(
        self,
        xyz_m: Sequence[float],
        quat_wxyz: Sequence[float],
        speed_m_s: float = 0.1,
        blend_m: float = 0.0,
        wait: bool = True,
    ) -> None:
        """Command a Cartesian linear move to the given pose at ``speed_m_s`` m/s.

        Orientation is supplied as a ``(w, x, y, z)`` quaternion. ``blend_m``
        and ``wait`` semantics match :meth:`move_joint`.
        """
        ...

    def run_program(self, source: str, name: str = "main") -> None:
        """Upload and run a vendor program (e.g. RAPID source for ABB).

        Sim drivers raise :class:`NotImplementedError`; programs only make
        sense on real controllers.
        """
        ...

    def stop(self) -> None:
        """Abort any in-flight motion or trajectory and bring the robot to rest."""
        ...


__all__ = ["Driver", "RobotState"]
