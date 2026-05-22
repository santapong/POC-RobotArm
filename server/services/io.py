"""I/O service layer for the server.

Re-exports :class:`~src.io.runtime.IoRuntime` as the canonical runtime used
by ``Session.io_runtime``.  This shim exists so server code imports from
``server.services.io`` consistently (mirrors ``server.services.planning``
and ``server.services.vision``), and so that future orchestration logic has
a place to live without touching the core ``src.io`` package.

Notes
-----
* ``import server.services.io`` succeeds even when the ``[io]`` extra is
  not installed — the heavy protocol libraries are never imported at module
  level.  :class:`~src.io.errors.IoUnavailable` is raised at the first
  ``IoRuntime.add_connection`` call when a concrete adapter cannot be built.
* ``get_or_create_io_runtime`` is the one place ``IoRuntime()`` is
  instantiated; it mirrors the lazy-init pattern used for
  ``PlanningRuntime`` in ``server/routers/planning.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.services.session import Session

# Re-export so callers do ``from server.services.io import IoRuntime``.
from src.io.runtime import IoRuntime

__all__ = ["IoRuntime", "get_or_create_io_runtime"]


def get_or_create_io_runtime(session: "Session") -> IoRuntime:
    """Return (or lazily create) the session's :class:`IoRuntime`.

    Mirrors the ``PlanningRuntime`` construction pattern in
    ``server/routers/planning.py`` — the runtime is created on the first
    call and stored on ``session.io_runtime`` for subsequent calls.

    Parameters
    ----------
    session:
        The global session singleton.

    Returns
    -------
    IoRuntime
        The active I/O runtime for this session.
    """
    if session.io_runtime is None:
        session.io_runtime = IoRuntime()
    return session.io_runtime
