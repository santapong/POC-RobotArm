"""Thread-safe bridge between LLM tools (worker thread) and the simulator.

PyBullet is thread-bound to whichever thread called ``p.connect``. The GUI
loop owns that thread. The LLM REPL runs on a worker thread and submits
``Command`` callables that the GUI thread executes on its next tick. Results
flow back via ``concurrent.futures.Future``.

A read-only state snapshot is updated after every tick so that
``sim_get_state``-style tools never have to wait on the GUI.
"""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .engine import RobotArmSim

CommandFn = Callable[[RobotArmSim], Any]


@dataclass
class _Command:
    fn: CommandFn
    future: Future


@dataclass
class _Trajectory:
    waypoints: list[list[float]]
    dwell_s: float
    index: int = 0
    last_advance: float = 0.0


class SimBridge:
    """Singleton bridge owning a ``RobotArmSim`` and a command queue."""

    _instance: Optional["SimBridge"] = None
    _class_lock = threading.Lock()

    def __init__(self, sim: RobotArmSim) -> None:
        self.sim = sim
        self.queue: "queue.Queue[_Command]" = queue.Queue()
        self._snapshot_lock = threading.Lock()
        self._snapshot: dict = {}
        self._trajectory: Optional[_Trajectory] = None
        self._update_snapshot()

    # ----------------------------------------------------------- singleton

    @classmethod
    def initialize(cls, sim: RobotArmSim) -> "SimBridge":
        with cls._class_lock:
            if cls._instance is not None:
                raise RuntimeError("SimBridge already initialized")
            cls._instance = cls(sim)
            return cls._instance

    @classmethod
    def shutdown(cls) -> None:
        with cls._class_lock:
            cls._instance = None

    @classmethod
    def instance(cls) -> "SimBridge":
        with cls._class_lock:
            if cls._instance is None:
                raise RuntimeError("SimBridge not initialized")
            return cls._instance

    @classmethod
    def is_initialized(cls) -> bool:
        with cls._class_lock:
            return cls._instance is not None

    # ----------------------------------------------------------- worker API

    def submit(self, fn: CommandFn, timeout: float = 5.0) -> Any:
        """Queue ``fn`` for the GUI thread and block until it completes."""
        fut: Future = Future()
        self.queue.put(_Command(fn=fn, future=fut))
        return fut.result(timeout=timeout)

    def snapshot(self) -> dict:
        with self._snapshot_lock:
            return dict(self._snapshot)

    # ---------------------------------------------------------- trajectory

    def start_trajectory(self, waypoints: list[list[float]], dwell_s: float) -> None:
        """Install a non-blocking waypoint trajectory; advanced by ``tick``."""
        self._trajectory = _Trajectory(
            waypoints=[list(w) for w in waypoints],
            dwell_s=max(0.05, float(dwell_s)),
            index=0,
            last_advance=time.monotonic(),
        )
        # Move to the first waypoint immediately.
        if waypoints:
            self.sim.set_joint_targets(waypoints[0])

    def trajectory_status(self) -> dict:
        if self._trajectory is None:
            return {"active": False}
        t = self._trajectory
        return {
            "active": True,
            "index": t.index,
            "total": len(t.waypoints),
            "dwell_s": t.dwell_s,
        }

    def cancel_trajectory(self) -> None:
        self._trajectory = None

    # ------------------------------------------------------------- GUI tick

    def tick(self, max_commands: int = 32) -> int:
        """Called from the GUI/main thread on every loop iteration."""
        n = 0
        while n < max_commands:
            try:
                cmd = self.queue.get_nowait()
            except queue.Empty:
                break
            try:
                cmd.future.set_result(cmd.fn(self.sim))
            except Exception as e:
                cmd.future.set_exception(e)
            n += 1

        self._advance_trajectory()
        self._update_snapshot()
        return n

    def _advance_trajectory(self) -> None:
        t = self._trajectory
        if t is None:
            return
        now = time.monotonic()
        if now - t.last_advance < t.dwell_s:
            return
        t.index += 1
        if t.index >= len(t.waypoints):
            self._trajectory = None
            return
        self.sim.set_joint_targets(t.waypoints[t.index])
        t.last_advance = now

    def _update_snapshot(self) -> None:
        try:
            connected = bool(self.sim.is_connected())
            angles = self.sim.get_joint_angles() if connected else []
            ee_pos, ee_orn = (
                self.sim.get_end_effector_pose()
                if connected
                else ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0])
            )
            num_joints = self.sim.num_joints if connected else 0
        except Exception:
            connected = False
            angles, ee_pos, ee_orn, num_joints = [], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0], 0

        with self._snapshot_lock:
            self._snapshot = {
                "connected": connected,
                "num_joints": num_joints,
                "joint_angles": list(angles),
                "ee_position": list(ee_pos),
                "ee_orientation": list(ee_orn),
                "trajectory": self.trajectory_status(),
            }


__all__ = ["SimBridge", "FuturesTimeoutError"]
