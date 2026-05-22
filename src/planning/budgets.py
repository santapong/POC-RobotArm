"""Cancellation tokens and per-stage soft time budgets.

Cancellation is cooperative — :class:`CancelToken` wraps a
``threading.Event``. Worker threads poll it at iteration boundaries
(OMPL ``TerminationCondition``, TOPP-RA bisection step, Drake outer SNOPT
loop) and raise :class:`PlanCancelled` when set.

This is mandatory: ``asyncio.Task.cancel()`` on a
``loop.run_in_executor`` future does NOT stop the worker thread
(CPython issue #107505); we propagate cancellation via this token instead.

Notes
-----
* Module top imports stdlib only — usable on Windows without OMPL / Drake.
* :class:`Budgets` derives stage budgets from the planner's ``timeout_s``
  using the 0.5 / 0.3 / 0.2 split (sample / optimise / parameterise) chosen
  in the design.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from src.planning.types import PlannerConfig


class PlanCancelled(RuntimeError):
    """Raised when a cooperative cancel is observed."""


class PlanTimeout(RuntimeError):
    """Raised when a stage exceeds its soft time budget."""


class CancelToken:
    """Thread-safe cooperative cancel token.

    Pool workers call :meth:`raise_if_cancelled` between iterations.
    Cancellation is set from any thread (FastAPI handler, signal handler,
    a tests fixture) via :meth:`cancel`.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Signal cancellation. Idempotent."""
        self._event.set()

    def is_cancelled(self) -> bool:
        """Return ``True`` if cancellation has been requested."""
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        """Raise :class:`PlanCancelled` if cancellation was requested."""
        if self._event.is_set():
            raise PlanCancelled("Plan cancelled cooperatively")

    def reset(self) -> None:
        """Clear the cancel flag. Intended for test fixtures only."""
        self._event.clear()


@dataclass(frozen=True)
class Budgets:
    """Per-stage soft time budgets derived from ``PlannerConfig.timeout_s``.

    The 0.5 / 0.3 / 0.2 split (sample / optimise / parameterise) is a
    starting point; the pipeline polls each token and stops the stage when
    the wall budget is exhausted. Optimisation is only consulted when
    enabled.
    """

    sample_s: float
    optimise_s: float
    parameterise_s: float

    def __post_init__(self) -> None:
        for fname in ("sample_s", "optimise_s", "parameterise_s"):
            v = getattr(self, fname)
            if v <= 0.0:
                raise ValueError(f"Budgets.{fname} must be > 0, got {v}")

    @classmethod
    def from_planner_config(cls, cfg: PlannerConfig) -> "Budgets":
        """Split ``cfg.timeout_s`` 0.5 / 0.3 / 0.2 across the three stages."""
        total = float(cfg.timeout_s)
        return cls(
            sample_s=total * 0.5,
            optimise_s=total * 0.3,
            parameterise_s=total * 0.2,
        )


__all__ = ["CancelToken", "PlanCancelled", "PlanTimeout", "Budgets"]
