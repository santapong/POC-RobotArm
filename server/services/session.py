"""Module-level Session singleton for the POC-RobotArm FastAPI server.

Phase 1 is single-operator: all REST handlers share one ``Session`` instance.
The ``lock`` serialises mutating operations; reads are allowed without the lock
since Python's GIL protects simple attribute reads.

Notes
-----
- ``get_session()`` is a FastAPI dependency — inject it with ``Depends(get_session)``.
- The ``Session`` is created by the lifespan context manager in ``server/main.py``
  and torn down on shutdown.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from server.models.runtime import RunRecord
from server.services.sim import SimRuntime
from src.station.scene import Frame, Station

if TYPE_CHECKING:
    from server.services.io import IoRuntime
    from server.services.planning import PlanningRuntime
    from server.services.vision import VisionRuntime


def _empty_station() -> Station:
    return Station(
        name="untitled_station",
        frames=(Frame("world", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent=None),),
    )


class _AssetRecord:
    """In-memory record of an imported asset."""

    def __init__(
        self,
        asset_id: str,
        kind: str,
        filename: str,
        path: str,
        summary: str,
    ) -> None:
        self.asset_id = asset_id
        self.kind = kind
        self.filename = filename
        self.path = path
        self.summary = summary


class Session:
    """Per-process global state container.

    Attributes
    ----------
    station:
        The current scene-graph, mutated by REST operations.
    station_path:
        The last-saved path (mirrors ``_station_path`` in the desktop UI).
    sim_runtime:
        Headless PyBullet wrapper; ``None`` until the first robot is spawned.
    runs:
        Map of ``run_id → RunRecord`` for program-run tracking.
    assets:
        Map of ``asset_id → _AssetRecord`` for imported CAD files.
    lock:
        Asyncio lock that serialises mutating REST operations.
    _events:
        Async queue feeding ``/ws/events`` subscribers.
    """

    def __init__(self) -> None:
        self.station: Station = _empty_station()
        self.station_path: Optional[str] = None
        self.sim_runtime: Optional[SimRuntime] = None
        self.vision_runtime: Optional["VisionRuntime"] = None
        self.planning_runtime: Optional["PlanningRuntime"] = None
        self.io_runtime: Optional["IoRuntime"] = None
        self.runs: dict[str, RunRecord] = {}
        self.run_tasks: dict[str, asyncio.Task] = {}
        self.assets: dict[str, _AssetRecord] = {}
        self.lock: asyncio.Lock = asyncio.Lock()
        self._events: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
        self._event_subscribers: set[asyncio.Queue] = set()

    async def push_event(self, event: dict) -> None:
        """Broadcast an event dict to all subscribed ``/ws/events`` clients."""
        for q in list(self._event_subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe_events(self, queue: asyncio.Queue) -> None:
        self._event_subscribers.add(queue)

    def unsubscribe_events(self, queue: asyncio.Queue) -> None:
        self._event_subscribers.discard(queue)


# Module-level singleton — initialised in lifespan.
_SESSION: Optional[Session] = None


def init_session() -> Session:
    """Create and store the global Session. Called once from lifespan."""
    global _SESSION
    _SESSION = Session()
    return _SESSION


def get_session() -> Session:
    """FastAPI dependency — returns the singleton Session."""
    if _SESSION is None:
        raise RuntimeError("Session not initialised — lifespan error")
    return _SESSION


__all__ = ["Session", "_AssetRecord", "get_session", "init_session"]
