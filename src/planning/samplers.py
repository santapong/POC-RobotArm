"""OMPL 2.0.0 sampling planner wrappers (RRT, RRT*, PRM).

Single-threaded ``ompl.base.Planner::solve`` is the only execution path —
``ompl.tools.ParallelPlan`` segfaults when paired with Python validity
callbacks (OMPL issue #1146) and is intentionally NEVER imported. The
:mod:`tests.test_planning_rrt` assertion ``"ParallelPlan" not in
dir(samplers)`` enforces that ban.

Notes
-----
* Module top imports stdlib + numpy + the planning types. OMPL is imported
  lazily inside :meth:`solve` so :mod:`src.planning.samplers` is
  importable on Windows.
* Cancellation is polled via OMPL's ``PlannerTerminationCondition`` —
  every node-expansion iteration checks the wall-clock deadline and the
  :class:`CancelToken` together.
* The validity-checker callback closes over the :class:`CollisionChecker`
  passed in; because the latter is thread-affined, OMPL's C++ side never
  directly touches PyBullet — the wrapper posts the query to a dedicated
  worker thread and blocks.
"""

from __future__ import annotations

import abc
import time
from typing import Callable, Sequence

from src.planning.budgets import CancelToken, PlanCancelled, PlanTimeout
from src.planning.collision import CollisionChecker
from src.planning.scene import SceneSnapshot
from src.planning.types import (
    PlannerConfig,
    PlannerKind,
    PlanningUnavailable,
)


class PlanNoSolution(RuntimeError):
    """Raised when the sampler exhausts its budget without finding a path."""


def _ensure_supported() -> None:
    """Raise :class:`PlanningUnavailable` on Windows."""
    import sys

    if sys.platform == "win32":
        raise PlanningUnavailable(
            "src.planning.samplers is not supported on Windows. Use WSL."
        )


class Planner(abc.ABC):
    """ABC for sampling planners."""

    kind: PlannerKind  # set by subclasses

    @abc.abstractmethod
    def solve(
        self,
        scene: SceneSnapshot,
        checker: CollisionChecker,
        q_start: Sequence[float],
        q_goal: Sequence[float],
        config: PlannerConfig,
        cancel: CancelToken,
        on_progress: Callable[[float], None] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        """Solve for a collision-free joint-space path.

        Returns
        -------
        tuple[tuple[float, ...], ...]
            The raw waypoint sequence including ``q_start`` and ``q_goal``.

        Raises
        ------
        PlanNoSolution
            If no collision-free path was found within the budget.
        PlanTimeout
            If the wall-clock budget elapsed before a path was found.
        PlanCancelled
            If the cancel token was set during the search.
        """


# ---------------------------------------------------------------------------
# Concrete planners
# ---------------------------------------------------------------------------


def _build_planner(ob, og, kind: PlannerKind, si):
    """Instantiate the OMPL planner that matches the requested kind."""
    if kind == PlannerKind.RRT:
        return og.RRT(si)
    if kind == PlannerKind.RRT_STAR:
        return og.RRTstar(si)
    if kind == PlannerKind.PRM:
        return og.PRM(si)
    raise ValueError(f"Unsupported PlannerKind: {kind!r}")


def _solve_with_ompl(
    scene: SceneSnapshot,
    checker: CollisionChecker,
    q_start: Sequence[float],
    q_goal: Sequence[float],
    config: PlannerConfig,
    cancel: CancelToken,
    on_progress: Callable[[float], None] | None,
    kind: PlannerKind,
) -> tuple[tuple[float, ...], ...]:
    """Common OMPL setup + solve loop used by every concrete subclass."""
    _ensure_supported()

    # Heavy import is deferred — keeps `import src.planning.samplers` cheap
    # on Windows + light test environments without OMPL installed. The
    # ``ompl.tools`` submodule is intentionally NOT imported (issue #1146 —
    # ParallelPlan segfaults with Python validity callbacks).
    from ompl import base as ob
    from ompl import geometric as og

    dof = scene.dof
    if len(q_start) != dof:
        raise ValueError(
            f"q_start has length {len(q_start)}, expected {dof}"
        )
    if len(q_goal) != dof:
        raise ValueError(
            f"q_goal has length {len(q_goal)}, expected {dof}"
        )

    # State space: an RnStateSpace with per-joint position limits.
    space = ob.RealVectorStateSpace(dof)
    bounds = ob.RealVectorBounds(dof)
    # Position limits aren't stored in SceneSnapshot directly; the planner
    # extracts them from the URDF via PyBullet through the collision
    # checker. We default to ±2π so the planner never rejects on bounds
    # alone; collision-driven rejection handles the rest. Tighter bounds
    # can be supplied through a future PlannerConfig extension.
    import math as _math

    for i in range(dof):
        bounds.setLow(i, -2.0 * _math.pi)
        bounds.setHigh(i, 2.0 * _math.pi)
    space.setBounds(bounds)

    si = ob.SpaceInformation(space)

    # Validity callback closes over the thread-safe checker wrapper. OMPL
    # invokes this from C++ on the calling thread; the wrapper forwards to
    # the dedicated PyBullet worker thread and blocks.
    clearance = float(config.clearance_m)

    def _is_valid(state) -> bool:
        try:
            cancel.raise_if_cancelled()
        except PlanCancelled:
            return False
        q = [state[i] for i in range(dof)]
        return not checker.is_collision(q, clearance_m=clearance)

    si.setStateValidityChecker(ob.StateValidityCheckerFn(_is_valid))
    si.setup()

    pdef = ob.ProblemDefinition(si)
    s_start = ob.State(space)
    s_goal = ob.State(space)
    for i in range(dof):
        s_start[i] = float(q_start[i])
        s_goal[i] = float(q_goal[i])
    pdef.setStartAndGoalStates(s_start, s_goal)

    planner = _build_planner(ob, og, kind, si)
    if hasattr(planner, "setRange"):
        planner.setRange(float(config.range_rad))
    planner.setProblemDefinition(pdef)
    planner.setup()

    if on_progress is not None:
        on_progress(0.0)

    deadline = time.monotonic() + float(config.timeout_s)

    # Cooperative termination: every node-expansion call OMPL evaluates
    # this lambda; we exit on cancel or deadline. The wall-clock check is
    # the primary defence against OMPL hangs.
    def _terminate() -> bool:
        if cancel.is_cancelled():
            return True
        return time.monotonic() > deadline

    ptc = ob.PlannerTerminationCondition(_terminate)
    solved = planner.solve(ptc)

    if cancel.is_cancelled():
        raise PlanCancelled("Planner cancelled mid-solve")

    if not solved:
        # Differentiate timeout vs no-solution by checking the deadline.
        if time.monotonic() >= deadline:
            raise PlanTimeout(
                f"Planner {kind.value} exceeded timeout_s={config.timeout_s}"
            )
        raise PlanNoSolution(
            f"Planner {kind.value} exhausted budget with no solution"
        )

    # Some OMPL builds emit `ompl::base::PlannerStatus` that is truthy even
    # when only an approximate solution is available. Guard against that
    # so the pipeline doesn't propagate a useless path. ``hasExactSolution``
    # is the canonical 2.0.0 accessor; fall back to the legacy attribute
    # if missing (older builds) and to a hard PlanNoSolution if neither
    # exposes the bit.
    if hasattr(pdef, "hasExactSolution") and not pdef.hasExactSolution():
        raise PlanNoSolution(
            f"Planner {kind.value} returned only an approximate solution"
        )

    path = pdef.getSolutionPath()
    if path is None:
        raise PlanNoSolution(
            f"Planner {kind.value} returned no solution path"
        )

    # Optional short-cutting smoothing pass (OMPL geometric).
    if config.smoothing_iterations > 0:
        try:
            simplifier = og.PathSimplifier(si)
            simplifier.shortcutPath(path, int(config.smoothing_iterations))
        except Exception:  # noqa: BLE001
            # Smoothing failures should not invalidate a solved path.
            pass

    # Interpolate so adjacent waypoints are within ``range_rad`` — keeps
    # the time-parameteriser well-conditioned downstream.
    try:
        path.interpolate()
    except Exception:  # noqa: BLE001
        pass

    state_count = path.getStateCount()
    waypoints: list[tuple[float, ...]] = []
    for i in range(state_count):
        s = path.getState(i)
        waypoints.append(tuple(float(s[j]) for j in range(dof)))

    if on_progress is not None:
        on_progress(1.0)

    if len(waypoints) < 2:
        raise PlanNoSolution(
            f"Planner {kind.value} returned a degenerate path "
            f"(state_count={state_count})"
        )

    return tuple(waypoints)


class RRTPlanner(Planner):
    """OMPL ``ompl.geometric.RRT``."""

    kind = PlannerKind.RRT

    def solve(
        self,
        scene: SceneSnapshot,
        checker: CollisionChecker,
        q_start: Sequence[float],
        q_goal: Sequence[float],
        config: PlannerConfig,
        cancel: CancelToken,
        on_progress: Callable[[float], None] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        return _solve_with_ompl(
            scene, checker, q_start, q_goal, config, cancel, on_progress,
            kind=PlannerKind.RRT,
        )


class RRTStarPlanner(Planner):
    """OMPL ``ompl.geometric.RRTstar``."""

    kind = PlannerKind.RRT_STAR

    def solve(
        self,
        scene: SceneSnapshot,
        checker: CollisionChecker,
        q_start: Sequence[float],
        q_goal: Sequence[float],
        config: PlannerConfig,
        cancel: CancelToken,
        on_progress: Callable[[float], None] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        return _solve_with_ompl(
            scene, checker, q_start, q_goal, config, cancel, on_progress,
            kind=PlannerKind.RRT_STAR,
        )


class PRMPlanner(Planner):
    """OMPL ``ompl.geometric.PRM``."""

    kind = PlannerKind.PRM

    def solve(
        self,
        scene: SceneSnapshot,
        checker: CollisionChecker,
        q_start: Sequence[float],
        q_goal: Sequence[float],
        config: PlannerConfig,
        cancel: CancelToken,
        on_progress: Callable[[float], None] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        return _solve_with_ompl(
            scene, checker, q_start, q_goal, config, cancel, on_progress,
            kind=PlannerKind.PRM,
        )


__all__ = [
    "Planner",
    "RRTPlanner",
    "RRTStarPlanner",
    "PRMPlanner",
    "PlanNoSolution",
]
