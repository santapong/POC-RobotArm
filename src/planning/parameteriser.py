"""TOPP-RA time parameterisation.

Wraps the TOPP-RA library (build-from-source on Python 3.12 + NumPy < 2,
per master plan §A). The reference API shape used here was validated in
the build-gate smoke on 2026-05-22:

.. code-block:: python

    import toppra as ta, toppra.constraint as constraint, toppra.algorithm as algo
    path = ta.SplineInterpolator(ss, way_pts)
    inst = algo.TOPPRA(
        [
            constraint.JointVelocityConstraint(vlims),
            constraint.JointAccelerationConstraint(alims),
        ],
        path,
        parametrizer="ParametrizeConstAccel",
    )
    jnt_traj = inst.compute_trajectory()  # jnt_traj.duration; jnt_traj(t)

Notes
-----
* Module top imports stdlib + numpy + the planning types. ``toppra`` is
  imported inside :meth:`parameterise`.
* Joint velocity / acceleration limits come from :class:`SceneSnapshot`
  scaled by :attr:`ParameteriserConfig.qd_scale` /
  :attr:`ParameteriserConfig.qdd_scale`.
* Near-singular paths return a ``None`` trajectory from TOPP-RA; we map
  that to :class:`PlanLimitsExceeded` with a ``singularity_hint`` payload
  the planner can use to retry (risk #10).
"""

from __future__ import annotations

import abc
from typing import Sequence

import numpy as np

from src.planning.budgets import CancelToken
from src.planning.scene import SceneSnapshot
from src.planning.types import (
    ParameteriserConfig,
    PlanningUnavailable,
    TimedTrajectory,
    TrajectorySample,
)


class PlanLimitsExceeded(RuntimeError):
    """Raised when TOPP-RA cannot honour the requested joint limits."""

    def __init__(
        self,
        message: str,
        singularity_hint: tuple[int, ...] = (),
    ) -> None:
        super().__init__(message)
        self.singularity_hint: tuple[int, ...] = tuple(int(i) for i in singularity_hint)


class TimeParameteriser(abc.ABC):
    """ABC for trajectory time-parameterisation."""

    @abc.abstractmethod
    def parameterise(
        self,
        scene: SceneSnapshot,
        waypoints: Sequence[Sequence[float]],
        config: ParameteriserConfig,
        cancel: CancelToken,
        dt_s: float = 0.01,
    ) -> TimedTrajectory:
        """Compute a time-parameterised :class:`TimedTrajectory`.

        Raises
        ------
        PlanLimitsExceeded
            If the path cannot be parameterised under the requested
            velocity / acceleration limits.
        PlanCancelled
            If ``cancel`` was set during the call.
        """


class ToppRAParameteriser(TimeParameteriser):
    """TOPP-RA time parameterisation."""

    def __init__(self) -> None:
        import sys

        if sys.platform == "win32":
            raise PlanningUnavailable(
                "src.planning.parameteriser is not supported on Windows. Use WSL."
            )

    def parameterise(
        self,
        scene: SceneSnapshot,
        waypoints: Sequence[Sequence[float]],
        config: ParameteriserConfig,
        cancel: CancelToken,
        dt_s: float = 0.01,
    ) -> TimedTrajectory:
        cancel.raise_if_cancelled()

        # Heavy import — keep it inside the call so the module stays
        # importable on Windows + minimal envs.
        import toppra as ta
        import toppra.algorithm as algo
        import toppra.constraint as constraint

        if dt_s <= 0.0:
            raise ValueError(f"dt_s must be > 0, got {dt_s}")
        pts = np.asarray(waypoints, dtype=float)
        if pts.ndim != 2:
            raise ValueError(
                f"waypoints must be 2D (n, dof), got shape {pts.shape}"
            )
        n_pts, dof = pts.shape
        if n_pts < 2:
            raise ValueError(
                f"ToppRAParameteriser requires >= 2 waypoints, got {n_pts}"
            )
        if dof != scene.dof:
            raise ValueError(
                f"Waypoint DOF {dof} differs from scene DOF {scene.dof}"
            )

        # Normalise the path parameter to [0, 1]; TOPP-RA solves the
        # time-optimal trajectory under joint vel/accel constraints,
        # independent of the original parameterisation.
        ss = np.linspace(0.0, 1.0, n_pts)
        path = ta.SplineInterpolator(ss, pts)

        vmax = np.asarray(scene.qd_max_rad_s, dtype=float) * float(config.qd_scale)
        amax = np.asarray(scene.qdd_max_rad_s2, dtype=float) * float(config.qdd_scale)
        vlims = np.stack([-vmax, vmax], axis=1)
        alims = np.stack([-amax, amax], axis=1)

        pc_vel = constraint.JointVelocityConstraint(vlims)
        pc_acc = constraint.JointAccelerationConstraint(alims)

        cancel.raise_if_cancelled()

        try:
            inst = algo.TOPPRA(
                [pc_vel, pc_acc],
                path,
                parametrizer="ParametrizeConstAccel",
                gridpoints=np.linspace(0.0, 1.0, int(config.grid_points)),
            )
        except TypeError:
            # Older toppra builds don't accept gridpoints as a kwarg; fall
            # back to the algorithm's default discretisation.
            inst = algo.TOPPRA(
                [pc_vel, pc_acc],
                path,
                parametrizer="ParametrizeConstAccel",
            )

        cancel.raise_if_cancelled()

        jnt_traj = inst.compute_trajectory()
        if jnt_traj is None:
            # TOPP-RA returns None when it cannot honour the constraints —
            # typical cause is a path through a singular configuration.
            # See risk #10. We try to flag the offending waypoint index.
            hint = self._near_singular_indices(pts, vmax, amax)
            raise PlanLimitsExceeded(
                "TOPP-RA could not parameterise the path under the requested "
                "joint velocity/acceleration limits",
                singularity_hint=hint,
            )

        duration = float(jnt_traj.duration)
        # Sample at the requested dt; keep the last sample at exactly the
        # duration so TimedTrajectory's monotonicity / duration invariants
        # hold without floating-point slop.
        n_samples = max(2, int(round(duration / float(dt_s))) + 1)
        ts = np.linspace(0.0, duration, n_samples)

        # Evaluate position, velocity, acceleration at each sample. TOPP-RA's
        # OutputTrajectory supports __call__(t, order) but the kwarg name
        # varies by version. Use positional with a small wrapper.
        def _eval(t: float, order: int) -> np.ndarray:
            try:
                return jnt_traj(t, order=order)
            except TypeError:
                return jnt_traj(t, order)

        samples: list[TrajectorySample] = []
        for t in ts:
            cancel.raise_if_cancelled()
            q = _eval(float(t), 0).reshape(-1)
            qd = _eval(float(t), 1).reshape(-1)
            qdd = _eval(float(t), 2).reshape(-1)
            samples.append(
                TrajectorySample(
                    t_s=float(t),
                    q_rad=tuple(float(v) for v in q[:dof]),
                    qd_rad_s=tuple(float(v) for v in qd[:dof]),
                    qdd_rad_s2=tuple(float(v) for v in qdd[:dof]),
                )
            )

        # Validate the achieved limits — if the trajectory still exceeds
        # the requested cap by more than 1% (numerical slack on TOPP-RA's
        # solution), report as a limits-exceeded failure with the offending
        # sample index list.
        slack = 1.01
        violated: list[int] = []
        for i, s in enumerate(samples):
            qd_arr = np.asarray(s.qd_rad_s)
            qdd_arr = np.asarray(s.qdd_rad_s2)
            if np.any(np.abs(qd_arr) > vmax * slack):
                violated.append(i)
                continue
            if np.any(np.abs(qdd_arr) > amax * slack):
                violated.append(i)
        if violated:
            raise PlanLimitsExceeded(
                "TOPP-RA output exceeded requested velocity/acceleration limits "
                f"at {len(violated)} samples",
                singularity_hint=tuple(violated),
            )

        return TimedTrajectory(
            robot_id=scene.robot_id,
            dt_s=float(dt_s),
            samples=tuple(samples),
            duration_s=float(samples[-1].t_s),
        )

    @staticmethod
    def _near_singular_indices(
        pts: np.ndarray,
        vmax: np.ndarray,
        amax: np.ndarray,
    ) -> tuple[int, ...]:
        """Best-effort flag for path indices that look near-singular.

        We have no Jacobian access here — the optimiser owns the
        ``MultibodyPlant``. As a fallback, we flag waypoint indices where
        the local secant velocity (in joint space) would exceed ``vmax``
        if the path were traversed in a single timestep; that's a useful
        heuristic for the planner to try a different seed.
        """
        if pts.shape[0] < 2:
            return ()
        diffs = np.diff(pts, axis=0)
        # Per-segment finite-difference velocity (unitless — path is on
        # the [0, 1] arc-length space; the actual time scaling is computed
        # by TOPP-RA). Comparing against vmax is a heuristic.
        hits: list[int] = []
        for i, d in enumerate(diffs):
            if np.any(np.abs(d) > vmax * 0.5):
                hits.append(i)
        # Also look at curvature (second difference) for amax.
        if pts.shape[0] >= 3:
            d2 = np.diff(diffs, axis=0)
            for i, d in enumerate(d2):
                if np.any(np.abs(d) > amax * 0.5):
                    hits.append(i + 1)
        return tuple(sorted(set(hits)))


__all__ = ["TimeParameteriser", "ToppRAParameteriser", "PlanLimitsExceeded"]
