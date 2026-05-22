"""FastAPI application entry point for the POC-RobotArm server.

Phase 1: delegates to ``server.main.create_app`` and re-exports the
application instance so ``uvicorn server.app:app`` and the existing
Phase 0 health test both continue to work.
"""

from server.main import create_app

app = create_app()

__all__ = ["app", "create_app"]
