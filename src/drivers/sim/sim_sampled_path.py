"""``SimSampledPathDriver`` — a proxy driver that routes moves through the path interpolator.

Wraps a :class:`~src.drivers.sim.sim_driver.SimDriver` (or any sim driver with a
``_bridge`` / ``bridge`` attribute) and replaces the direct snap-and-hold motion
calls with a limits-checked, time-sampled trajectory computed by
:func:`~src.motion.path.interpolate_program`.

Notes
-----
- Driver Protocol methods (``connect``, ``disconnect``, ``is_connected``, ``get_state``,
  ``stop``, ``run_program``) are delegated unchanged to the inner driver.
- ``move_joint`` and ``move_linear`` each build a single-Move
  :class:`~src.motion.ir.Program`, run it through ``interpolate_program``, and
  replay the resulting :class:`~src.motion.path.SampledPath` via
  ``bridge.start_trajectory``.
- ``play_program`` accepts a full :class:`~src.motion.ir.Program` and replays
  the entire path, returning the :class:`~src.motion.path.SampledPath`.
- The ``wait`` argument on ``move_joint`` / ``move_linear`` mirrors the
  :class:`~src.drivers.sim.sim_driver.SimDriver` behaviour: when ``True``, the
  method blocks until the bridge's trajectory is no longer active.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # pragma: no cover
    from src.motion.path import SampledPath
    from src.simulation.bridge import SimBridge


_WAIT_TIMEOUT_S = 30.0
_WAIT_POLL_S = 0.02


class SimSampledPathDriver:
    """Proxy implementing the Driver Protocol with interpolated trajectories.

    Args:
        inner: An existing sim driver instance that exposes a ``_bridge`` or
            ``bridge`` attribute pointing to the :class:`~src.simulation.bridge.SimBridge`.
        robot: A roboticstoolbox :class:`~roboticstoolbox.Robot` used for FK/IK.
        dt_s: Timestep for trajectory sampling (default 0.01 s).

    Raises:
        ValueError: if ``inner`` does not expose a ``_bridge`` or ``bridge``
            attribute.
    """

    def __init__(self, inner, robot, *, dt_s: float = 0.01) -> None:
        # Resolve the bridge from the inner driver.
        if hasattr(inner, "_bridge"):
            bridge: "SimBridge" = inner._bridge
        elif hasattr(inner, "bridge"):
            bridge = inner.bridge
        else:
            raise ValueError(
                "SimSampledPathDriver requires a sim driver with a _bridge attribute"
            )
        self._inner = inner
        self._bridge = bridge
        self._robot = robot
        self._dt_s = dt_s

        # Expose Driver Protocol attributes mirroring the inner driver.
        self.name: str = getattr(inner, "name", "sim_sampled_path")
        self.dof: int = getattr(inner, "dof", robot.n)

    # ---------------------------------------------------------------- lifecycle

    def connect(self) -> None:
        """Delegate to the inner driver."""
        self._inner.connect()

    def disconnect(self) -> None:
        """Delegate to the inner driver."""
        self._inner.disconnect()

    def is_connected(self) -> bool:
        """Delegate to the inner driver."""
        return self._inner.is_connected()

    # ----------------------------------------------------------------- state

    def get_state(self):
        """Delegate to the inner driver."""
        return self._inner.get_state()

    # ----------------------------------------------------------------- control

    def stop(self) -> None:
        """Delegate to the inner driver."""
        self._inner.stop()

    def run_program(self, source: str, name: str = "main") -> None:
        """Delegate to the inner driver (raises NotImplementedError for sim)."""
        self._inner.run_program(source, name)

    # ----------------------------------------------------------------- motion

    def move_joint(
        self,
        q_rad: Sequence[float],
        speed_frac: float = 0.5,
        blend_m: float = 0.0,
        wait: bool = True,
    ) -> None:
        """Interpolate a joint-space move and replay it through the bridge.

        Builds a single-Move ``MOVE_ABS_J`` :class:`~src.motion.ir.Program`,
        calls :func:`~src.motion.path.interpolate_program`, and feeds the
        sampled trajectory to ``bridge.start_trajectory``.

        Args:
            q_rad: Target joint configuration in radians.
            speed_frac: Ignored (accepted for API parity with Driver Protocol).
            blend_m: Ignored.
            wait: If ``True``, block until the trajectory finishes.
        """
        del speed_frac, blend_m

        prog = _one_move_program_joint(list(q_rad))
        from src.motion.path import interpolate_program

        path = interpolate_program(prog, self._robot, dt_s=self._dt_s, raise_on_violation=False)
        waypoints = [list(s.q_rad) for s in path.samples]
        # PyBullet has strict thread affinity to the GUI thread; route the
        # bridge mutation through bridge.submit so set_joint_targets is called
        # on the right thread.
        self._bridge.submit(
            lambda sim: self._bridge.start_trajectory(waypoints, self._dt_s)
        )
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
        """Interpolate a Cartesian linear move and replay it through the bridge.

        Builds a single-Move ``MOVE_L`` :class:`~src.motion.ir.Program`,
        calls :func:`~src.motion.path.interpolate_program`, and feeds the
        sampled trajectory to ``bridge.start_trajectory``.

        Args:
            xyz_m: Target Cartesian position ``(x, y, z)`` in metres.
            quat_wxyz: Target orientation ``(w, x, y, z)`` unit quaternion.
            speed_m_s: TCP linear speed in metres per second.
            blend_m: Ignored.
            wait: If ``True``, block until the trajectory finishes.
        """
        del blend_m

        prog = _one_move_program_linear(list(xyz_m), list(quat_wxyz), speed_m_s=speed_m_s)
        from src.motion.path import interpolate_program

        path = interpolate_program(prog, self._robot, dt_s=self._dt_s, raise_on_violation=False)
        waypoints = [list(s.q_rad) for s in path.samples]
        self._bridge.submit(
            lambda sim: self._bridge.start_trajectory(waypoints, self._dt_s)
        )
        if wait:
            self._wait_until_idle()

    def play_program(self, prog, procedure_name: str = "main") -> "SampledPath":
        """Interpolate an entire :class:`~src.motion.ir.Program` and replay it.

        Args:
            prog: Vendor-neutral motion program to play.
            procedure_name: Procedure to execute (currently always ``"main"``).

        Returns:
            The :class:`~src.motion.path.SampledPath` produced by the interpolator.
        """
        from src.motion.path import interpolate_program

        path = interpolate_program(prog, self._robot, dt_s=self._dt_s, raise_on_violation=False)
        waypoints = [list(s.q_rad) for s in path.samples]
        self._bridge.submit(
            lambda sim: self._bridge.start_trajectory(waypoints, self._dt_s)
        )
        return path

    # -------------------------------------------------------------- helpers

    def _wait_until_idle(self) -> None:
        """Block until the bridge reports no active trajectory."""
        deadline = time.monotonic() + _WAIT_TIMEOUT_S
        while time.monotonic() < deadline:
            state = self._inner.get_state()
            if not state.moving:
                return
            time.sleep(_WAIT_POLL_S)
        raise TimeoutError(
            f"SimSampledPathDriver: robot still moving after {_WAIT_TIMEOUT_S:.1f}s"
        )


# ---------------------------------------------------------------------------
# Program builders
# ---------------------------------------------------------------------------


def _default_tool():
    from src.motion.ir import ToolData
    return ToolData(name="tool0", mass_kg=0.001, tcp_xyz_m=(0.0, 0.0, 0.0), tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0))


def _default_wobj():
    from src.motion.ir import WObjData
    return WObjData(name="wobj0", base_xyz_m=(0.0, 0.0, 0.0), base_quat_wxyz=(1.0, 0.0, 0.0, 0.0))


def _one_move_program_joint(q_rad: list[float]):
    """Build a single-MOVE_ABS_J Program for ``move_joint``."""
    from src.motion.ir import (
        JointTarget,
        Move,
        MoveKind,
        Procedure,
        Program,
        SpeedData,
        ZoneData,
    )

    move = Move(
        kind=MoveKind.MOVE_ABS_J,
        target=JointTarget(q_rad=tuple(float(v) for v in q_rad)),
        speed=SpeedData(v_tcp_mm_s=100.0),
        zone=ZoneData.fine(),
        tool=_default_tool(),
        wobj=_default_wobj(),
    )
    proc = Procedure(name="main", body=(move,))
    return Program(name="move_joint", procedures=(proc,))


def _one_move_program_linear(xyz_m: list[float], quat_wxyz: list[float], *, speed_m_s: float = 0.1):
    """Build a single-MOVE_L Program for ``move_linear``."""
    from src.motion.ir import (
        Move,
        MoveKind,
        PoseTarget,
        Procedure,
        Program,
        SpeedData,
        ZoneData,
    )

    move = Move(
        kind=MoveKind.MOVE_L,
        target=PoseTarget(
            xyz_m=tuple(float(v) for v in xyz_m),
            quat_wxyz=tuple(float(v) for v in quat_wxyz),
        ),
        speed=SpeedData(v_tcp_mm_s=speed_m_s * 1000.0),
        zone=ZoneData.fine(),
        tool=_default_tool(),
        wobj=_default_wobj(),
    )
    proc = Procedure(name="main", body=(move,))
    return Program(name="move_linear", procedures=(proc,))


__all__: list[str] = ["SimSampledPathDriver"]
