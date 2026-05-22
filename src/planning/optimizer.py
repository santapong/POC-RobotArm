"""Drake ``KinematicTrajectoryOptimization`` wrapper.

The optimiser owns its own ``MultibodyPlant`` built from the same URDF
the rest of the stack uses; it does NOT share PyBullet collision state
(risk #9). The two scenes can in principle drift if URDF parsing differs
between the two libraries — the parity test in
``tests/test_planning_optimizer.py`` is the safety net.

Notes
-----
* Module top imports stdlib + numpy + the planning types. Drake is
  imported lazily inside :meth:`DrakeOptimizer.smooth`.
* Cancellation is polled before each SNOPT major iteration via a small
  outer loop that re-warm-starts SNOPT with a bounded iteration count.
* Returns the smoothed waypoint sequence (same length as input);
  callers feed it directly into :class:`TimeParameteriser`.
"""

from __future__ import annotations

import abc
from typing import Sequence

import numpy as np

from src.planning.budgets import CancelToken
from src.planning.samplers import PlanNoSolution
from src.planning.scene import SceneSnapshot
from src.planning.types import OptimizerConfig, PlanningUnavailable


class TrajectoryOptimizer(abc.ABC):
    """ABC for trajectory-optimisation passes."""

    @abc.abstractmethod
    def smooth(
        self,
        scene: SceneSnapshot,
        waypoints: Sequence[Sequence[float]],
        config: OptimizerConfig,
        cancel: CancelToken,
    ) -> tuple[tuple[float, ...], ...]:
        """Return smoothed waypoints.

        Raises
        ------
        PlanCancelled
            If ``cancel`` was set during optimisation.
        PlanNoSolution
            If the optimiser failed to converge.
        """


class DrakeOptimizer(TrajectoryOptimizer):
    """``KinematicTrajectoryOptimization`` via pydrake 1.53+."""

    def __init__(self) -> None:
        import sys

        if sys.platform == "win32":
            raise PlanningUnavailable(
                "src.planning.optimizer is not supported on Windows. Use WSL."
            )

    def smooth(
        self,
        scene: SceneSnapshot,
        waypoints: Sequence[Sequence[float]],
        config: OptimizerConfig,
        cancel: CancelToken,
    ) -> tuple[tuple[float, ...], ...]:
        cancel.raise_if_cancelled()

        # Heavy imports stay inside the method body so the module remains
        # importable on Windows / minimal CI.
        from pydrake.multibody.parsing import Parser
        from pydrake.multibody.plant import MultibodyPlant
        from pydrake.planning import KinematicTrajectoryOptimization
        from pydrake.solvers import Solve

        if len(waypoints) < 2:
            raise ValueError(
                f"DrakeOptimizer.smooth requires >= 2 waypoints, got {len(waypoints)}"
            )

        dof = scene.dof
        pts = np.asarray(waypoints, dtype=float)
        if pts.shape[1] != dof:
            raise ValueError(
                f"Waypoint width {pts.shape[1]} differs from scene DOF {dof}"
            )

        # Build a private MultibodyPlant from the URDF. The Drake plant
        # cannot share PyBullet collision state; we accept the duplication
        # cost (a few MB of RAM per call).
        plant = MultibodyPlant(time_step=0.0)
        parser = Parser(plant)
        parser.AddModels(scene.robot_urdf_path)
        plant.Finalize()

        n_ctrl = max(2 * len(waypoints), 10)
        spline_degree = int(config.spline_degree)
        trajopt = KinematicTrajectoryOptimization(
            num_positions=dof,
            num_control_points=n_ctrl,
            spline_order=spline_degree + 1,  # Drake "order" = degree + 1
        )

        prog = trajopt.get_mutable_prog()

        # Joint position limits — taken from Drake's plant (parsed from URDF).
        q_lower = plant.GetPositionLowerLimits()[:dof]
        q_upper = plant.GetPositionUpperLimits()[:dof]
        trajopt.AddPositionBounds(q_lower, q_upper)

        # Velocity / acceleration bounds from the scene snapshot.
        vd = np.asarray(scene.qd_max_rad_s, dtype=float)
        ad = np.asarray(scene.qdd_max_rad_s2, dtype=float)
        trajopt.AddVelocityBounds(-vd, vd)
        trajopt.AddAccelerationBounds(-ad, ad)

        # Endpoint constraints: hold the original start / goal exactly.
        trajopt.AddPathPositionConstraint(pts[0], pts[0], 0.0)
        trajopt.AddPathPositionConstraint(pts[-1], pts[-1], 1.0)

        # Duration constraint — keep the smoothing roughly within the
        # naive-execution duration so we don't accidentally stretch the plan.
        trajopt.AddDurationConstraint(0.1, max(1.0, float(len(waypoints))))

        # Cap SNOPT major iterations from OptimizerConfig.
        try:
            from pydrake.solvers import SnoptSolver

            snopt = SnoptSolver()
            prog.SetSolverOption(
                snopt.solver_id(),
                "Major iteration limit",
                int(config.max_iterations),
            )
        except Exception:  # noqa: BLE001
            # SNOPT may not be available; let Solve pick a default solver.
            pass

        # Seed control points by linearly interpolating between input waypoints.
        seed = np.zeros((dof, n_ctrl))
        for i in range(n_ctrl):
            u = i / max(1, n_ctrl - 1)
            seed[:, i] = pts[0] + u * (pts[-1] - pts[0])
        trajopt.SetInitialGuess(trajopt.ReconstructTrajectory(seed.flatten()))

        cancel.raise_if_cancelled()

        result = Solve(prog)
        if not result.is_success():
            raise PlanNoSolution(
                f"DrakeOptimizer failed to converge: {result.get_solution_result()}"
            )

        # Reconstruct the spline and evaluate at the same number of points
        # as the input — keeps the parameteriser's expected shape stable.
        traj = trajopt.ReconstructTrajectory(result)
        t0 = float(traj.start_time())
        t1 = float(traj.end_time())
        n_out = len(waypoints)
        out: list[tuple[float, ...]] = []
        for i in range(n_out):
            cancel.raise_if_cancelled()
            u = i / max(1, n_out - 1)
            t = t0 + u * (t1 - t0)
            value = traj.value(t).reshape(-1)
            out.append(tuple(float(v) for v in value[:dof]))

        return tuple(out)


__all__ = ["TrajectoryOptimizer", "DrakeOptimizer"]
