"""``SimDriver`` — a thin adapter from :class:`SimBridge` to the
vendor-neutral :class:`Driver` Protocol.

The simulator's bridge is already thread-safe and owns the only PyBullet
client. ``SimDriver`` adds zero new behaviour on top: it simply translates
between the high-level Protocol calls (``move_joint``, ``get_state`` ...)
and the bridge's ``submit`` / ``snapshot`` mechanics that the existing
LLM tool layer also uses.

Notes
-----
* Sim moves are effectively instantaneous — the bridge snaps joints with
  ``reset_joint_angles`` and then holds them via ``set_joint_targets``.
  ``speed_frac`` and ``blend_m`` arguments are accepted for API parity
  but ignored.
* Cartesian linear moves degrade to "IK + snap": the orientation argument
  is honoured if supplied (PyBullet expects ``xyzw`` so we reorder from the
  canonical ``wxyz``), but interpolation along the path is not modelled in
  this slice.
* Programs are a real-controller concept; ``run_program`` raises
  ``NotImplementedError`` on this driver intentionally.
"""

from __future__ import annotations

import time
import warnings
from typing import TYPE_CHECKING, Sequence

from src.drivers.base import RobotState
from src.motion.ir import check_quat

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from src.simulation.bridge import SimBridge


# Sim moves complete within a tick; this is the upper bound we'll wait
# for the bridge's "moving" flag to clear before raising.
_WAIT_TIMEOUT_S = 30.0
_WAIT_POLL_S = 0.02


class SimDriver:
    """Adapter exposing a :class:`SimBridge` through the :class:`Driver` Protocol."""

    def __init__(self, bridge: "SimBridge", robot_name: str, dof: int) -> None:
        self._bridge = bridge
        self.name = f"sim:{robot_name}"
        self.dof = int(dof)
        # The sim is "always on" once the GUI loop owns the bridge; the
        # caller still has to opt-in via ``connect()`` so the lifecycle
        # mirrors a real driver.
        self._connected = False

    # ------------------------------------------------------------- lifecycle

    def connect(self) -> None:
        """Mark the driver as connected. The underlying sim is already live."""
        self._connected = True

    def disconnect(self) -> None:
        """Detach from the sim. Idempotent — safe to call repeatedly."""
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ---------------------------------------------------------------- state

    def get_state(self) -> RobotState:
        """Translate the bridge's snapshot dict into a :class:`RobotState`."""
        snap = self._bridge.snapshot()
        joints = tuple(float(a) for a in snap.get("joint_angles", ()))
        ee_pos = list(snap.get("ee_position", [0.0, 0.0, 0.0]))
        if len(ee_pos) < 3:
            ee_pos = ee_pos + [0.0] * (3 - len(ee_pos))
        # Bridge stores PyBullet's xyzw quaternion; canonical Protocol form
        # is wxyz, so reorder once at the boundary.
        ee_orn = list(snap.get("ee_orientation", [0.0, 0.0, 0.0, 1.0]))
        if len(ee_orn) < 4:
            ee_orn = ee_orn + [0.0] * (4 - len(ee_orn))
        x, y, z, w = ee_orn[0], ee_orn[1], ee_orn[2], ee_orn[3]

        traj = snap.get("trajectory", {}) or {}
        moving = bool(traj.get("active", False))

        connected = bool(snap.get("connected", False))
        error = None if connected else "sim_disconnected"

        return RobotState(
            joints_rad=joints,
            tcp_xyz_m=(float(ee_pos[0]), float(ee_pos[1]), float(ee_pos[2])),
            tcp_quat_wxyz=(float(w), float(x), float(y), float(z)),
            moving=moving,
            error=error,
        )

    # ----------------------------------------------------------- motion API

    def move_joint(
        self,
        q_rad: Sequence[float],
        speed_frac: float = 0.5,
        blend_m: float = 0.0,
        wait: bool = True,
    ) -> None:
        """Drive the simulator's joints to ``q_rad``. ``speed_frac``/``blend_m`` ignored."""
        del speed_frac, blend_m  # accepted for API parity; sim ignores
        targets = [float(a) for a in q_rad]
        if len(targets) != self.dof:
            raise ValueError(
                f"move_joint expected {self.dof} joint angles, got {len(targets)}"
            )

        def _apply(sim) -> None:
            if len(targets) != sim.num_joints:
                raise ValueError(
                    f"sim has {sim.num_joints} joints but {len(targets)} targets supplied"
                )
            # Snap-and-hold matches the existing tool-layer pattern so the
            # GUI updates immediately and physics keeps the pose.
            sim.reset_joint_angles(targets)
            sim.set_joint_targets(targets)

        self._bridge.submit(_apply)
        if wait:
            self._wait_until_idle()

    def move_linear(
        self,
        xyz_m: Sequence[float],
        quat_wxyz: Sequence[float],
        speed_m_s: float = 0.1,
        blend_m: float = 0.0,
        wait: bool = True,
    ) -> None:
        """Solve IK for the target pose and snap the sim to that joint solution."""
        del speed_m_s, blend_m  # accepted for API parity; sim ignores
        position = [float(v) for v in xyz_m]
        if len(position) != 3:
            raise ValueError(f"move_linear expected 3 xyz components, got {len(position)}")

        target_xyzw = None
        if quat_wxyz is not None:
            quat = tuple(float(v) for v in quat_wxyz)
            # check_quat enforces both length and unit-norm; matches the
            # invariant the IR's PoseTarget enforces internally so a bad quat
            # cannot reach PyBullet's IK and silently scale the orientation.
            check_quat(quat, "quat_wxyz")
            # Canonical wxyz -> PyBullet's xyzw.
            w, x, y, z = quat
            target_xyzw = [x, y, z, w]
        else:
            warnings.warn(
                "SimDriver.move_linear called without orientation; sim will use "
                "position-only IK in this slice.",
                stacklevel=2,
            )

        def _solve_and_apply(sim) -> None:
            sol = sim.solve_ik(position, target_xyzw)
            sol = list(sol)[: sim.num_joints]
            sim.reset_joint_angles(sol)
            sim.set_joint_targets(sol)

        self._bridge.submit(_solve_and_apply, timeout=10.0)
        if wait:
            self._wait_until_idle()

    def run_program(self, source: str, name: str = "main") -> None:
        """Sim has no program execution; raise to make the misuse loud and clear."""
        del source, name
        raise NotImplementedError(
            "sim driver does not execute programs; use post-processor + run_program "
            "on a real driver"
        )

    def stop(self) -> None:
        """Cancel any active trajectory; subsequent ``get_state().moving`` is ``False``."""
        self._bridge.cancel_trajectory()

    # -------------------------------------------------------------- helpers

    def _wait_until_idle(self) -> None:
        """Block until the bridge reports no active trajectory.

        Sim joint moves are effectively instantaneous (snap + hold), so this
        is mostly a no-op. It only matters for trajectories started elsewhere
        (e.g. the LLM ``sim_play_trajectory`` tool) that the caller wants to
        wait out before issuing the next command.
        """
        deadline = time.monotonic() + _WAIT_TIMEOUT_S
        while time.monotonic() < deadline:
            if not self.get_state().moving:
                return
            time.sleep(_WAIT_POLL_S)
        raise TimeoutError(
            f"SimDriver.move_*: robot still moving after {_WAIT_TIMEOUT_S:.1f}s"
        )


__all__ = ["SimDriver"]
