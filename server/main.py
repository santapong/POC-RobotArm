"""FastAPI application factory for POC-RobotArm Phase 1.

Usage
-----
Production::

    uvicorn server.main:create_app --factory --host 0.0.0.0 --port 8000

Development (with CORS and auto-reload)::

    POC_DEV_CORS=1 uvicorn server.main:create_app --factory --reload

Notes
-----
- Session initialisation and teardown happen in the ``lifespan`` context
  manager, not in deprecated ``on_event`` hooks.
- CORS is only mounted when ``POC_DEV_CORS=1`` is set.
- Static assets are served from ``<repo_root>/assets`` at ``/assets``.
- A global exception handler translates domain exceptions into
  ``ErrorResponse`` via ``server.services.errors.map_exception``.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server.models.errors import ErrorResponse
from server.services.errors import map_exception
from server.services.session import init_session

# Resolve repo root: server/main.py → server/ → repo root
_REPO_ROOT = Path(__file__).parent.parent.resolve()
_ASSETS_DIR = _REPO_ROOT / "assets"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise and tear down the global Session."""
    session = init_session()
    yield
    # Shutdown: stop SimRuntime if active.
    if session.sim_runtime is not None:
        try:
            await session.sim_runtime.stop()
        except Exception:  # noqa: BLE001
            pass
    # Shutdown: stop VisionRuntime if active.
    if session.vision_runtime is not None:
        try:
            await session.vision_runtime.stop()
        except Exception:  # noqa: BLE001
            pass


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="POC-RobotArm Server",
        version="1.0.0",
        description=(
            "Phase 1 REST + WebSocket API for the POC-RobotArm station editor. "
            "Exposes station I/O, robot spawning, jog, code post-processing, "
            "and live PyBullet telemetry."
        ),
        lifespan=_lifespan,
    )

    # ------------------------------------------------------------------
    # CORS (dev only)
    # ------------------------------------------------------------------
    if os.environ.get("POC_DEV_CORS", "") == "1":
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ------------------------------------------------------------------
    # Global exception handlers
    # ------------------------------------------------------------------
    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # When detail is already an ErrorResponse dict (from http_error()), return
        # it flat so the client sees {"detail": "...", "code": "..."} directly.
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        # Plain-string detail: wrap in a minimal ErrorResponse shape.
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                detail="Request validation failed.",
                code="VALIDATION_ERROR",
                violations=[
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
                ],
            ).model_dump(exclude_none=True),
        )

    @app.exception_handler(Exception)
    async def _global_handler(request: Request, exc: Exception) -> JSONResponse:
        status_code, body = map_exception(exc)
        return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    from server.routers.assets import router as assets_router
    from server.routers.health import router as health_router
    from server.routers.programs import router as programs_router
    from server.routers.robots import router as robots_router
    from server.routers.station import router as station_router
    from server.routers.vision import router as vision_router
    from server.ws.events import router as events_router
    from server.ws.telemetry import router as telemetry_router
    from server.ws.vision import router as vision_ws_router

    app.include_router(health_router)
    app.include_router(assets_router)
    app.include_router(programs_router)
    app.include_router(robots_router)
    app.include_router(station_router)
    app.include_router(vision_router)
    app.include_router(events_router)
    app.include_router(telemetry_router)
    app.include_router(vision_ws_router)

    # ------------------------------------------------------------------
    # Static files
    # ------------------------------------------------------------------
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR), html=False), name="assets")

    return app


__all__ = ["create_app"]
