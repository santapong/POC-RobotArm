"""Error response model for the POC-RobotArm FastAPI server."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Uniform error body returned for all non-2xx responses."""

    model_config = ConfigDict(from_attributes=True)

    detail: str
    code: str
    hint: Optional[str] = None
    violations: Optional[list[dict]] = None


__all__ = ["ErrorResponse"]
