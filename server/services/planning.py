"""PlanningRuntime — per-session motion-planning service.

One ``PlanningRuntime`` is created lazily when the first plan request
arrives (via ``POST /api/planning/plans`` or indirectly from a program run
with ``planner="rrt"``). It owns:

* A ``ThreadPoolExecutor(max_workers=2)`` for blocking planner work — the
  heavy C-extension calls (OMPL, Drake, toppra) never run on the event loop.
* An asyncio ``lock`` that serialises record mutations.
* A ``set[asyncio.Queue]`` for WebSocket progress subscribers; frames are
  published via ``loop.call_soon_threadsafe`` (mandatory: asyncio.Queue is
  not thread-safe from worker threads).
* An ``OrderedDict`` plan-cache (cap 32) keyed by scene + request fingerprint.

Notes
-----
- ``stop()`` sets all outstanding cancel tokens, shuts down the executor, and
  cancels the heartbeat task.
- PyBullet / OMPL / Drake / toppra are imported lazily so this module is
  importable on Windows (``PlanningUnavailable`` is raised at first
  ``__init__`` call on those platforms).
- ``asyncio.get_running_loop()`` is used throughout, never the deprecated
  ``asyncio.get_event_loop()``.
"""

from __future__ import annotations

import asyncio
import collections
import concurrent.futures
import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from server.models.planning import (
    PlanProgressFrame,
    PlanStageModel,
    PlanStatusModel,
)

if TYPE_CHECKING:
    from src.planning.budgets import CancelToken
    from src.planning.collision import CollisionChecker
    from src.planning.ik import IKSolver
    from src.planning.optimizer import TrajectoryOptimizer
    from src.planning.parameteriser import TimeParameteriser
    from src.planning.samplers import Planner
    from src.planning.types import PlanRequest, PlanResult, TimedTrajectory
    from src.station.scene import Station

# ---------------------------------------------------------------------------
# Lazy planning imports (mirrors vision.py pattern)
# ---------------------------------------------------------------------------

try:
    from src.planning.budgets import CancelToken as _CancelToken  # noqa: F401 (used below)
    from src.planning.collision import CollisionChecker as _CollisionChecker
    from src.planning.ik import IKSolver as _IKSolver
    from src.planning.optimizer import DrakeOptimizer as _DrakeOptimizer
    from src.planning.optimizer import TrajectoryOptimizer as _TrajectoryOptimizer
    from src.planning.parameteriser import TimeParameteriser as _TimeParameteriser
    from src.planning.parameteriser import ToppRAParameteriser as _ToppRAParameteriser
    from src.planning.pipeline import plan as _pipeline_plan
    from src.planning.samplers import Planner as _Planner
    from src.planning.samplers import RRTStarPlanner as _RRTStarPlanner
    from src.planning.scene import SceneSnapshot as _SceneSnapshot
    from src.planning.types import PlannerStage as _PlannerStage
    from src.planning.types import PlanningUnavailable as _PlanningUnavailable
    from src.planning.types import PlanStatus as _PlanStatus

    _PLANNING_AVAILABLE = True
except ImportError:
    _PLANNING_AVAILABLE = False
    _CollisionChecker = None  # type: ignore[assignment, misc]
    _IKSolver = None  # type: ignore[assignment, misc]
    _DrakeOptimizer = None  # type: ignore[assignment, misc]
    _TrajectoryOptimizer = None  # type: ignore[assignment, misc]
    _TimeParameteriser = None  # type: ignore[assignment, misc]
    _ToppRAParameteriser = None  # type: ignore[assignment, misc]
    _pipeline_plan = None  # type: ignore[assignment]
    _Planner = None  # type: ignore[assignment, misc]
    _RRTStarPlanner = None  # type: ignore[assignment, misc]
    _SceneSnapshot = None  # type: ignore[assignment, misc]
    _PlannerStage = None  # type: ignore[assignment, misc]
    _PlanningUnavailable = None  # type: ignore[assignment, misc]
    _PlanStatus = None  # type: ignore[assignment, misc]
    _CancelToken = None  # type: ignore[assignment, misc]

_PLAN_CACHE_CAP = 32
_HEARTBEAT_INTERVAL = 0.5  # seconds


# ---------------------------------------------------------------------------
# Internal record
# ---------------------------------------------------------------------------


@dataclass
class _PlanRunRecord:
    """Mutable bookkeeping for one plan run (server-side view)."""

    plan_id: str
    request: "PlanRequest"
    status: PlanStatusModel
    stage: PlanStageModel
    cancel_token: "CancelToken"
    future: Optional[concurrent.futures.Future]
    result: Optional["PlanResult"]
    created_at: float
    finished_at: Optional[float]
    _request_model: object = field(default=None, repr=False)  # PlanRequestModel cache


# ---------------------------------------------------------------------------
# PlanningRuntime
# ---------------------------------------------------------------------------


class PlanningRuntime:
    """Session-scoped motion-planning pipeline.

    Instantiated lazily on the first plan request; torn down via
    ``await stop()`` in the server lifespan shutdown handler.
    """

    def __init__(
        self,
        catalog_name: str,
        station_provider: Callable[[], "Station"],
    ) -> None:
        self.catalog_name = catalog_name
        self._station_provider = station_provider

        self.runs: dict[str, _PlanRunRecord] = {}
        self.subscribers: set[asyncio.Queue] = set()
        self.lock: asyncio.Lock = asyncio.Lock()
        self._plan_cache: collections.OrderedDict[str, "TimedTrajectory"] = (
            collections.OrderedDict()
        )
        self.executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=2)
        self.loop = asyncio.get_running_loop()

        # Scene-agnostic planner components — instantiated lazily on first
        # plan() call. CollisionChecker and IKSolver are NOT cached here
        # because they are built from a SceneSnapshot (obstacle-specific);
        # they are created fresh per plan call in _plan_blocking.
        self.collision: Optional["CollisionChecker"] = None
        self.ik: Optional["IKSolver"] = None
        self.sampling_planner: Optional["Planner"] = None
        self.optimiser: Optional["TrajectoryOptimizer"] = None
        self.parameteriser: Optional["TimeParameteriser"] = None

        self._heartbeat_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lazy component initialisation (scene-agnostic components only)
    # ------------------------------------------------------------------

    def _ensure_stateless_components(self) -> None:
        """Instantiate scene-agnostic components (sampler, optimiser, parameteriser)."""
        if not _PLANNING_AVAILABLE:
            raise RuntimeError("Planning libraries not available on this platform")

        if self.sampling_planner is None:
            self.sampling_planner = _RRTStarPlanner()
        if self.optimiser is None:
            try:
                self.optimiser = _DrakeOptimizer()
            except Exception:  # noqa: BLE001
                # Drake may not be installed; optimizer is optional.
                self.optimiser = None
        if self.parameteriser is None:
            self.parameteriser = _ToppRAParameteriser()

    # ------------------------------------------------------------------
    # Plan fingerprint
    # ------------------------------------------------------------------

    def _scene_plan_fingerprint(self, req: "PlanRequest") -> str:
        """Compute a cache key for this (scene, request) combination."""
        station = self._station_provider()
        scene = _SceneSnapshot.from_station(
            station,
            req.robot_id,
            req.obstacles,
            planner_config=req.planner,
        )
        payload = (
            scene.fingerprint,
            tuple(req.q_start),
            req.goal_q,
            req.goal_pose,
            req.planner.kind,
            req.planner.range_rad,
        )
        return hashlib.sha1(repr(payload).encode()).hexdigest()

    # ------------------------------------------------------------------
    # Progress publication (called from event-loop thread)
    # ------------------------------------------------------------------

    def _publish_progress(
        self,
        plan_id: str,
        stage: PlanStageModel,
        percent: float,
        eta_s: Optional[float] = None,
    ) -> None:
        """Put a progress frame into all subscriber queues.

        Must be called from the event-loop thread (via call_soon_threadsafe).
        """
        frame = PlanProgressFrame(
            plan_id=plan_id,
            stage=stage,
            percent=percent,
            eta_s=eta_s,
            monotonic_s=time.monotonic(),
        )
        payload = frame.model_dump()
        for q in list(self.subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def _thread_publish_progress(
        self,
        plan_id: str,
        stage: PlanStageModel,
        percent: float,
        eta_s: Optional[float] = None,
    ) -> None:
        """Schedule a progress publication from a worker thread."""
        self.loop.call_soon_threadsafe(
            self._publish_progress, plan_id, stage, percent, eta_s
        )

    # ------------------------------------------------------------------
    # Worker (runs on ThreadPoolExecutor)
    # ------------------------------------------------------------------

    def _plan_blocking(self, req: "PlanRequest", record: _PlanRunRecord) -> None:
        """Blocking plan execution; runs in executor worker thread."""
        plan_id = record.plan_id

        def _progress_cb(stage: "_PlannerStage", pct: float) -> None:
            stage_model = PlanStageModel(stage.value)
            self._thread_publish_progress(plan_id, stage_model, pct)
            # Update the record's stage for heartbeat reporting.
            record.stage = stage_model

        try:
            station = self._station_provider()
            self._ensure_stateless_components()

            scene = _SceneSnapshot.from_station(
                station,
                req.robot_id,
                req.obstacles,
                planner_config=req.planner,
            )

            # CollisionChecker and IKSolver are scene-specific (obstacle set
            # is baked into CollisionChecker at construction time). Build fresh
            # instances for this plan call.
            checker = _CollisionChecker(scene=scene)
            ik = _IKSolver(scene=scene)

            result = _pipeline_plan(
                request=req,
                scene=scene,
                checker=checker,
                ik=ik,
                sampler=self.sampling_planner,
                optimizer=self.optimiser,
                parameteriser=self.parameteriser,
                cancel=record.cancel_token,
                on_progress=_progress_cb,
                plan_id=plan_id,
            )

            # Update singleton attributes for external inspection.
            self.collision = checker
            self.ik = ik

            record.result = result
            record.finished_at = time.time()

            if result.status == _PlanStatus.COMPLETED:
                record.status = PlanStatusModel.COMPLETED
                record.stage = PlanStageModel.COMPLETED
                # Store in plan cache.
                try:
                    fp = self._scene_plan_fingerprint(req)
                    if result.trajectory is not None:
                        if len(self._plan_cache) >= _PLAN_CACHE_CAP:
                            self._plan_cache.popitem(last=False)
                        self._plan_cache[fp] = result.trajectory
                except Exception:  # noqa: BLE001
                    pass
            elif result.status == _PlanStatus.CANCELLED:
                record.status = PlanStatusModel.CANCELLED
                record.stage = PlanStageModel.CANCELLED
            else:
                record.status = PlanStatusModel.FAILED
                record.stage = PlanStageModel.FAILED

        except Exception as exc:  # noqa: BLE001
            record.status = PlanStatusModel.FAILED
            record.stage = PlanStageModel.FAILED
            record.finished_at = time.time()
            # Wrap as a minimal PlanResult so callers can read error info.
            from src.planning.types import (
                PlannerStage,
                PlanResult,
                PlanStatus,
            )

            record.result = PlanResult(
                plan_id=plan_id,
                status=PlanStatus.FAILED,
                stage=PlannerStage.FAILED,
                trajectory=None,
                elapsed_s=0.0,
                sampler_path_length=0,
                optimizer_iterations=0,
                parameteriser_grid_points=0,
                cache_hit=False,
                error_code="PLANNING_FAILED",
                error_message=str(exc),
            )
        finally:
            # Always emit a final progress event.
            self._thread_publish_progress(plan_id, record.stage, 1.0)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def plan(
        self,
        req: "PlanRequest",
        plan_id: Optional[str] = None,
    ) -> _PlanRunRecord:
        """Schedule a plan and return the run record immediately.

        Returns a record with ``status=RUNNING``; the caller must poll
        ``record.status`` or await ``record.future`` to know when it finishes.
        Cache hits short-circuit immediately and return ``status=COMPLETED``.
        """
        if plan_id is None:
            plan_id = str(uuid.uuid4())

        from src.planning.budgets import CancelToken

        cancel_token = CancelToken()

        async with self.lock:
            record = _PlanRunRecord(
                plan_id=plan_id,
                request=req,
                status=PlanStatusModel.RUNNING,
                stage=PlanStageModel.QUEUED,
                cancel_token=cancel_token,
                future=None,
                result=None,
                created_at=time.time(),
                finished_at=None,
            )
            self.runs[plan_id] = record

        # Cache lookup before dispatching to worker.
        try:
            fp = self._scene_plan_fingerprint(req)
            if fp in self._plan_cache:
                cached_traj = self._plan_cache[fp]
                # Move to end (LRU recency).
                self._plan_cache.move_to_end(fp)
                from src.planning.types import PlannerStage, PlanResult, PlanStatus

                record.result = PlanResult(
                    plan_id=plan_id,
                    status=PlanStatus.COMPLETED,
                    stage=PlannerStage.COMPLETED,
                    trajectory=cached_traj,
                    elapsed_s=0.0,
                    sampler_path_length=0,
                    optimizer_iterations=0,
                    parameteriser_grid_points=0,
                    cache_hit=True,
                )
                record.status = PlanStatusModel.COMPLETED
                record.stage = PlanStageModel.COMPLETED
                record.finished_at = time.time()
                self._publish_progress(plan_id, PlanStageModel.COMPLETED, 1.0)
                return record
        except Exception:  # noqa: BLE001
            # Fingerprint failure (e.g. robot not in station) — fall through to
            # worker which will produce a proper error result.
            pass

        future = self.loop.run_in_executor(
            self.executor, self._plan_blocking, req, record
        )
        record.future = future

        # Start heartbeat task if not running.
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name="planning_heartbeat"
            )

        return record

    async def cancel(self, plan_id: str) -> _PlanRunRecord:
        """Cooperatively cancel a running plan.

        Sets the cancel token and waits up to 3 s for the worker to honour it.
        Returns the (updated) run record.
        """
        record = self.runs[plan_id]  # raises KeyError if unknown
        if record.status not in (PlanStatusModel.RUNNING,):
            return record

        record.cancel_token.cancel()
        if record.future is not None:
            try:
                await asyncio.wait_for(
                    asyncio.wrap_future(record.future), timeout=3.0
                )
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass

        if record.status == PlanStatusModel.RUNNING:
            record.status = PlanStatusModel.CANCELLED
            record.stage = PlanStageModel.CANCELLED
            record.finished_at = time.time()

        return record

    async def stop(self) -> None:
        """Cancel all running plans, shut down executor, cancel heartbeat."""
        # Cancel all running plans.
        for plan_id, record in list(self.runs.items()):
            if record.status == PlanStatusModel.RUNNING:
                record.cancel_token.cancel()

        # Cancel heartbeat.
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        self.executor.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Record access
    # ------------------------------------------------------------------

    def get_record(self, plan_id: str) -> _PlanRunRecord:
        """Return the run record for ``plan_id``; raises ``KeyError`` if unknown."""
        return self.runs[plan_id]

    def list_records(self) -> list[_PlanRunRecord]:
        """Return all run records in creation order."""
        return list(self.runs.values())

    # ------------------------------------------------------------------
    # Subscriber pub/sub
    # ------------------------------------------------------------------

    def subscribe_progress(self, q: asyncio.Queue) -> None:
        """Add a queue to receive ``PlanProgressFrame`` payloads."""
        self.subscribers.add(q)

    def unsubscribe_progress(self, q: asyncio.Queue) -> None:
        """Remove a queue from progress broadcasts."""
        self.subscribers.discard(q)

    # ------------------------------------------------------------------
    # Heartbeat loop
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Post progress frames for all running plans every 500 ms."""
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            running = [
                r for r in self.runs.values() if r.status == PlanStatusModel.RUNNING
            ]
            if not running:
                # No active plans — exit the heartbeat task.
                return
            for record in running:
                self._publish_progress(
                    record.plan_id,
                    record.stage,
                    0.5,  # indeterminate progress during heartbeat
                    eta_s=None,
                )


__all__ = ["PlanningRuntime", "_PlanRunRecord"]
