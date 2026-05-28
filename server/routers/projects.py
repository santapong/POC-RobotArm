"""REST endpoints for the project (Doc) store.

These power the browser app's Save/Load against the server (so projects can
live somewhere other than the user's downloads folder + localStorage), and
share the same store the MCP endpoint operates on. The wire shape is
identical to the on-disk format — the same JSON the TS app downloads.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.models.project import Doc
from server.services.project_store import (
    ProjectInvalid,
    ProjectNotFound,
    get_project_store,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[dict])
def list_projects() -> list[dict]:
    """List every saved project (id + meta + op count)."""
    return get_project_store().list()


@router.get("/{project_id}", response_model=Doc, response_model_by_alias=True)
def load_project(project_id: str) -> Doc:
    try:
        return get_project_store().load(project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=f"project '{project_id}' not found")
    except ProjectInvalid as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/{project_id}", response_model=Doc, response_model_by_alias=True)
def save_project(project_id: str, doc: Doc) -> Doc:
    return get_project_store().save(project_id, doc)


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict:
    ok = get_project_store().delete(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"project '{project_id}' not found")
    return {"deleted": project_id}
