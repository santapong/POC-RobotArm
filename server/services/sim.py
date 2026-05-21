"""SimRuntime — wraps headless PyBullet + SimBridge with asyncio tasks.

Lifecycle
---------
``SimRuntime`` is created lazily when the first robot is spawned
(``POST /api/station/robots``). It owns:

* One ``RobotArmSim(use_gui=False)`` PyBullet client.
* One ``SimBridge`` (singleton) ticked by a background asyncio task at ~60 Hz.
* A second async task that fans out the bridge snapshot to subscribed
  ``/ws/telemetry`` queues at ~30 Hz.

All ``p.*`` calls happen on the same worker thread via
``asyncio.to_thread(bridge.tick, ...)``, preserving PyBullet's thread affinity.

Notes
-----
- ``stop()`` cancels both tasks and disconnects PyBullet.
- ``SimBridge.shutdown()`` is called on stop so a fresh ``SimRuntime`` can
  be created later (e.g. after deleting the robot).
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

_TICK_INTERVAL = 1 / 60  # ~60 Hz
_TELEMETRY_INTERVAL = 1 / 30  # ~30 Hz


class SimRuntime:
    """Headless PyBullet wrapper with asyncio tick + telemetry pub/sub.

    Args:
        catalog_name: Robot name from the catalog (e.g. ``"abb_irb1200"``).
    """

    def __init__(self, catalog_name: str) -> None:
        # Import at construction time — not at module import time — so the
        # module is importable without pybullet installed.
        from src.robots.catalog import get_spec
        from src.simulation.bridge import SimBridge
        from src.simulation.engine import RobotArmSim

        spec = get_spec(catalog_name)
        self.catalog_name = catalog_name
        self.dof = spec.dof

        self.sim = RobotArmSim(robot_name=catalog_name, use_gui=False)
        # SimBridge is a singleton; clear any previous instance first.
        SimBridge.shutdown()
        self.bridge = SimBridge.initialize(self.sim)

        self._telemetry_subscribers: set[asyncio.Queue] = set()
        self._tick_task: Optional[asyncio.Task] = None
        self._telemetry_task: Optional[asyncio.Task] = None

    # -------------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Schedule the background tick and telemetry tasks on the running loop."""
        loop = asyncio.get_event_loop()
        self._tick_task = loop.create_task(self._tick_loop(), name="sim_tick")
        self._telemetry_task = loop.create_task(
            self._telemetry_loop(), name="sim_telemetry"
        )

    async def stop(self) -> None:
        """Cancel background tasks and disconnect PyBullet."""
        for task in (self._tick_task, self._telemetry_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        from src.simulation.bridge import SimBridge

        SimBridge.shutdown()
        try:
            self.sim.disconnect()
        except Exception:  # noqa: BLE001
            pass

    # -------------------------------------------------------------- tasks

    async def _tick_loop(self) -> None:
        """Run bridge.tick() at ~60 Hz on a worker thread."""
        while True:
            try:
                await asyncio.to_thread(self.bridge.tick)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(_TICK_INTERVAL)

    async def _telemetry_loop(self) -> None:
        """Push snapshot to all subscribed WS queues at ~30 Hz."""
        while True:
            await asyncio.sleep(_TELEMETRY_INTERVAL)
            if not self._telemetry_subscribers:
                continue
            try:
                snap = await asyncio.to_thread(self.bridge.snapshot)
                traj = snap.get("trajectory", {})
                angles = snap.get("joint_angles", [])
                ee_pos = snap.get("ee_position", [0.0, 0.0, 0.0])
                ee_orn = snap.get("ee_orientation", [0.0, 0.0, 0.0, 1.0])
                # ee_orientation from PyBullet is xyzw; convert to wxyz
                tcp_quat_wxyz = (
                    float(ee_orn[3]),
                    float(ee_orn[0]),
                    float(ee_orn[1]),
                    float(ee_orn[2]),
                )
                run_state = None
                if traj.get("active"):
                    run_state = {
                        "run_id": None,  # filled in by session if available
                        "index": traj.get("index", 0),
                        "total": traj.get("total", 0),
                        "active": True,
                    }
                frame = {
                    "robot_id": self.catalog_name,
                    "joints_rad": [float(a) for a in angles],
                    "tcp_xyz_m": [float(v) for v in ee_pos[:3]],
                    "tcp_quat_wxyz": list(tcp_quat_wxyz),
                    "run_state": run_state,
                    "monotonic_s": time.monotonic(),
                }
                dead: list[asyncio.Queue] = []
                for q in list(self._telemetry_subscribers):
                    try:
                        q.put_nowait(frame)
                    except asyncio.QueueFull:
                        dead.append(q)
                for q in dead:
                    self._telemetry_subscribers.discard(q)
            except Exception:  # noqa: BLE001
                pass

    # -------------------------------------------------------------- pub/sub

    def subscribe_telemetry(self, queue: asyncio.Queue) -> None:
        """Add a queue to receive telemetry frames."""
        self._telemetry_subscribers.add(queue)

    def unsubscribe_telemetry(self, queue: asyncio.Queue) -> None:
        """Remove a queue from telemetry broadcasts."""
        self._telemetry_subscribers.discard(queue)

    # -------------------------------------------------------------- snapshot

    def snapshot(self) -> dict:
        """Return a thread-safe snapshot of the current bridge state."""
        return self.bridge.snapshot()


__all__ = ["SimRuntime"]
