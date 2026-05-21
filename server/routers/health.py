"""Health-check router — ``GET /health``."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return ``{"status": "ok"}`` when the server is live."""
    return {"status": "ok"}


__all__ = ["router"]
