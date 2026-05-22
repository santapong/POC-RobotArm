"""Motion planning package — sampling, optimisation, time parameterisation.

Phase 3 lands a full classical + optimisation + parameterisation stack:

* :mod:`src.planning.samplers` — OMPL 2.0.0 wrappers (RRT / RRT* / PRM).
* :mod:`src.planning.optimizer` — Drake ``KinematicTrajectoryOptimization``.
* :mod:`src.planning.parameteriser` — TOPP-RA time parameterisation.
* :mod:`src.planning.ik` — PyBullet IK with quantised LRU seed cache.
* :mod:`src.planning.collision` — thread-affined wrapper around the existing
  PyBullet ``CollisionChecker``.
* :mod:`src.planning.scene` — immutable scene snapshot with deterministic
  fingerprint for plan caching at the server layer.
* :mod:`src.planning.pipeline` — orchestrates sample -> optimise ->
  parameterise into a :class:`TimedTrajectory`.

Notes
-----
* This module is importable on Windows even though OMPL / Drake / TOPP-RA do
  not have Windows wheels. Concrete-class ``__init__`` methods raise
  :class:`PlanningUnavailable` on Windows; everything else (types, scene,
  budgets) is pure-Python and works.
* All units are SI throughout — metres, radians, seconds. Vendor-specific
  unit conversion lives at the post-processor / driver boundaries.
* Quaternions are ``(w, x, y, z)`` everywhere, mirroring :mod:`src.motion.ir`.
"""

from __future__ import annotations

import sys

from src.planning.budgets import Budgets, CancelToken, PlanCancelled, PlanTimeout
from src.planning.collision import CollisionChecker
from src.planning.ik import IKResult, IKSolver, PlanningIKUnreachable
from src.planning.optimizer import DrakeOptimizer, TrajectoryOptimizer
from src.planning.parameteriser import (
    PlanLimitsExceeded,
    TimeParameteriser,
    ToppRAParameteriser,
)
from src.planning.pipeline import plan
from src.planning.samplers import (
    Planner,
    PlanNoSolution,
    PRMPlanner,
    RRTPlanner,
    RRTStarPlanner,
)
from src.planning.scene import SceneSnapshot
from src.planning.types import (
    OptimizerConfig,
    ParameteriserConfig,
    PlannerConfig,
    PlannerKind,
    PlannerStage,
    PlanningUnavailable,
    PlanRequest,
    PlanResult,
    PlanStatus,
    TimedTrajectory,
    TrajectorySample,
    from_dict,
    to_dict,
)

# Windows has no OMPL / Drake / TOPP-RA wheels in 2026 (see plan §L). Module
# import stays cheap on all platforms (every submodule above only imports
# stdlib + numpy + the planning types at module level); concrete-class
# __init__ enforces the guard so type / budget / scene utilities remain
# usable on Windows.
_HAS_PLANNING: bool = sys.platform != "win32"

__all__ = [
    # Enums
    "PlannerStage",
    "PlannerKind",
    "PlanStatus",
    # Request / result types
    "PlanRequest",
    "PlanResult",
    "TimedTrajectory",
    "TrajectorySample",
    # Configs
    "PlannerConfig",
    "OptimizerConfig",
    "ParameteriserConfig",
    # Cancellation / budgets
    "CancelToken",
    "Budgets",
    "PlanCancelled",
    "PlanTimeout",
    "PlanningUnavailable",
    # Scene
    "SceneSnapshot",
    # Collision
    "CollisionChecker",
    # IK
    "IKSolver",
    "IKResult",
    "PlanningIKUnreachable",
    # Sampling
    "Planner",
    "RRTPlanner",
    "RRTStarPlanner",
    "PRMPlanner",
    "PlanNoSolution",
    # Optimisation
    "TrajectoryOptimizer",
    "DrakeOptimizer",
    # Parameterisation
    "TimeParameteriser",
    "ToppRAParameteriser",
    "PlanLimitsExceeded",
    # Pipeline
    "plan",
    # JSON I/O
    "to_dict",
    "from_dict",
]
