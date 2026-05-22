"""Domain-exception → HTTP status / ErrorResponse mapper.

Public API:
- ``map_exception`` — translates a domain exception to (http_status, ErrorResponse).
- ``http_error`` — builds an HTTPException whose detail is a serialised ErrorResponse.

Both are called from ``server/main.py`` and from individual routers.
"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError

from fastapi import HTTPException

from server.models.errors import ErrorResponse


def http_error(
    status_code: int,
    code: str,
    detail: str,
    hint: str | None = None,
    violations: list[dict] | None = None,
) -> HTTPException:
    """Return an :class:`HTTPException` whose ``detail`` is a serialised :class:`ErrorResponse`.

    FastAPI will convert the ``detail`` dict to JSON verbatim, so the client
    always receives ``{"detail": "...", "code": "...", ...}``.

    Args:
        status_code: HTTP status code (e.g. 404, 422, 503).
        code: Machine-readable error code from design §A.4 (e.g. ``"ROBOT_UNKNOWN"``).
        detail: Human-readable description.
        hint: Optional actionable hint for the caller.
        violations: Optional list of structured validation violation dicts.
    """
    payload = ErrorResponse(
        detail=detail, code=code, hint=hint, violations=violations
    ).model_dump(exclude_none=True)
    return HTTPException(status_code=status_code, detail=payload)


def map_exception(exc: Exception) -> tuple[int, ErrorResponse]:
    """Translate a domain exception to an ``(http_status, ErrorResponse)`` pair.

    Notes
    -----
    Mapping table (matches design §A.4):

    - ``KeyError`` (unknown robot in catalog) → 404 ``ROBOT_UNKNOWN``
    - ``ValueError`` from dataclass ``__post_init__`` → 422 ``VALIDATION_ERROR``
    - ``LimitsExceeded`` → 409 ``LIMITS_EXCEEDED`` (violations populated)
    - ``FileNotFoundError`` → 404 ``ASSET_NOT_FOUND``
    - ``NotImplementedError`` → 501 ``NOT_SUPPORTED``
    - ``RuntimeError("not initialized")`` or ``RuntimeError("SIM_DISCONNECTED")`` → 503
    - ``TimeoutError`` / ``FuturesTimeoutError`` → 504 ``SIM_TIMEOUT``
    - Planning-domain exceptions → see planning error codes below.
    - Anything else → 500 ``INTERNAL_ERROR``
    """
    # Import lazily to avoid circular dep on sim / domain modules at startup.
    try:
        from src.motion.limits import LimitsExceeded
    except ImportError:
        LimitsExceeded = None  # type: ignore[assignment, misc]

    # Lazy planning-lib imports (Linux/macOS only; safe to fail on Windows).
    try:
        from src.planning.budgets import PlanCancelled, PlanTimeout
        from src.planning.ik import PlanningIKUnreachable
        from src.planning.parameteriser import PlanLimitsExceeded
        from src.planning.samplers import PlanNoSolution
        from src.planning.types import PlanningUnavailable
    except ImportError:
        PlanCancelled = PlanTimeout = PlanNoSolution = None  # type: ignore[assignment, misc]
        PlanLimitsExceeded = PlanningIKUnreachable = PlanningUnavailable = None  # type: ignore[assignment, misc]

    # Lazy I/O-lib imports (requires [io] extra; safe to fail on all platforms).
    try:
        from src.io.errors import (
            IoConnectionError,
            IoNotConnected,
            IoProtocolError,
            IoSignalKindMismatch,
            IoTimeout,
            IoUnavailable,
            IoUnknownSignal,
        )
    except ImportError:
        IoConnectionError = IoNotConnected = IoProtocolError = None  # type: ignore[assignment, misc]
        IoSignalKindMismatch = IoTimeout = IoUnavailable = None  # type: ignore[assignment, misc]
        IoUnknownSignal = None  # type: ignore[assignment, misc]

    if LimitsExceeded is not None and isinstance(exc, LimitsExceeded):
        return 409, ErrorResponse(
            detail=str(exc),
            code="LIMITS_EXCEEDED",
            violations=[v.to_dict() for v in exc.violations],
        )

    # Planning-specific exceptions — checked before the generic ValueError /
    # RuntimeError branches because some planning exceptions inherit from those.
    if PlanningUnavailable is not None and isinstance(exc, PlanningUnavailable):
        return 422, ErrorResponse(
            detail=str(exc),
            code="PLANNING_UNAVAILABLE",
            hint=(
                "Planning libraries (OMPL / Drake / toppra) require Linux or macOS. "
                "Windows users: install via WSL (see docs/planning-setup.md)."
            ),
        )

    if PlanCancelled is not None and isinstance(exc, PlanCancelled):
        return 409, ErrorResponse(
            detail=str(exc),
            code="PLANNING_CANCELLED",
        )

    if PlanNoSolution is not None and isinstance(exc, PlanNoSolution):
        return 409, ErrorResponse(
            detail=str(exc),
            code="PLANNING_NO_SOLUTION",
        )

    if PlanningIKUnreachable is not None and isinstance(exc, PlanningIKUnreachable):
        return 409, ErrorResponse(
            detail=str(exc),
            code="PLANNING_IK_UNREACHABLE",
        )

    if PlanLimitsExceeded is not None and isinstance(exc, PlanLimitsExceeded):
        return 409, ErrorResponse(
            detail=str(exc),
            code="PLANNING_LIMITS_EXCEEDED",
            violations=[{"singularity_hint": list(exc.singularity_hint)}],
        )

    if PlanTimeout is not None and isinstance(exc, PlanTimeout):
        return 504, ErrorResponse(
            detail=str(exc),
            code="PLANNING_TIMEOUT",
        )

    # I/O-specific exceptions — checked before generic ValueError / RuntimeError
    # branches because some I/O exceptions inherit from RuntimeError.
    if IoUnavailable is not None and isinstance(exc, IoUnavailable):
        return 422, ErrorResponse(
            detail=str(exc),
            code="IO_UNAVAILABLE",
            hint="Install the [io] extra: pip install 'poc-robotarm[io]'",
        )

    if IoConnectionError is not None and isinstance(exc, IoConnectionError):
        return 503, ErrorResponse(
            detail=str(exc),
            code="IO_CONNECTION_FAILED",
        )

    if IoNotConnected is not None and isinstance(exc, IoNotConnected):
        return 503, ErrorResponse(
            detail=str(exc),
            code="IO_NOT_CONNECTED",
        )

    if IoProtocolError is not None and isinstance(exc, IoProtocolError):
        return 502, ErrorResponse(
            detail=str(exc),
            code="IO_PROTOCOL_ERROR",
        )

    if IoSignalKindMismatch is not None and isinstance(exc, IoSignalKindMismatch):
        return 422, ErrorResponse(
            detail=str(exc),
            code="IO_SIGNAL_KIND_MISMATCH",
        )

    if IoTimeout is not None and isinstance(exc, IoTimeout):
        return 504, ErrorResponse(
            detail=str(exc),
            code="IO_TIMEOUT",
        )

    if IoUnknownSignal is not None and isinstance(exc, IoUnknownSignal):
        return 404, ErrorResponse(
            detail=str(exc),
            code="IO_SIGNAL_UNKNOWN",
        )

    if isinstance(exc, KeyError):
        return 404, ErrorResponse(
            detail=str(exc),
            code="ROBOT_UNKNOWN",
            hint="Check /api/robots/catalog for valid names.",
        )

    if isinstance(exc, ValueError):
        return 422, ErrorResponse(
            detail=str(exc),
            code="VALIDATION_ERROR",
        )

    if isinstance(exc, FileNotFoundError):
        return 404, ErrorResponse(
            detail=str(exc),
            code="ASSET_NOT_FOUND",
        )

    if isinstance(exc, NotImplementedError):
        return 501, ErrorResponse(
            detail=str(exc),
            code="NOT_SUPPORTED",
        )

    if isinstance(exc, (FuturesTimeoutError, TimeoutError)):
        return 504, ErrorResponse(
            detail="Simulation command timed out.",
            code="SIM_TIMEOUT",
        )

    if isinstance(exc, RuntimeError):
        msg = str(exc).lower()
        if "not initialized" in msg or "sim_disconnected" in msg or "not initializ" in msg:
            return 503, ErrorResponse(
                detail=str(exc),
                code="SIM_DISCONNECTED",
                hint="Spawn a robot first to initialise the simulator.",
            )

    return 500, ErrorResponse(
        detail=str(exc),
        code="INTERNAL_ERROR",
    )


__all__ = ["http_error", "map_exception"]
