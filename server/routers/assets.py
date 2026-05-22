"""Asset management router.

Endpoints
---------
- ``POST /api/assets/import`` — upload a mesh / DXF and optionally add it to the station.
- ``GET  /api/assets/urdf/{robot}/{file:path}`` — serve URDF files for project or
  bundled robots.
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import FileResponse, Response

from server.models.runtime import AssetImportResponse
from server.models.station import FixtureEntryModel
from server.services.assets import get_asset_tempdir, resolve_urdf_path
from server.services.errors import http_error
from server.services.session import Session, _AssetRecord, get_session

router = APIRouter(prefix="/api/assets")


@router.post("/import", response_model=AssetImportResponse)
async def import_asset(
    file: UploadFile,
    attach_to: str | None = Form(default=None),
    add_to_station: bool = Form(default=True),
    session: Session = Depends(get_session),
) -> AssetImportResponse:
    """Upload a mesh (.stl/.obj/.ply) or DXF file and summarise it.

    When ``add_to_station=True``, a :class:`FixtureEntry` referencing the
    uploaded file is appended to the station under ``attach_to`` (defaulting
    to ``"world"``).
    """
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    raw = await file.read()

    tmpdir = get_asset_tempdir()
    asset_id = str(uuid.uuid4())
    dest = tmpdir / f"{asset_id}{ext}"
    dest.write_bytes(raw)

    path_str = str(dest)
    kind: str
    summary: str

    if ext in (".stl", ".obj", ".ply"):
        kind = "mesh"
        try:
            from src.station.cad_import import load_mesh

            mesh = load_mesh(path_str)
            summary = (
                f"# Imported mesh: {filename}\n"
                f"# vertices: {len(mesh.vertices)}\n"
                f"# faces: {len(mesh.faces)}\n"
            )
        except Exception as exc:
            raise http_error(422, "VALIDATION_ERROR", f"Could not load mesh: {exc}") from exc
    elif ext == ".dxf":
        kind = "dxf"
        try:
            from src.station.cad_import import load_dxf

            polylines = load_dxf(path_str)
            summary = (
                f"# Imported DXF: {filename}\n"
                f"# polylines: {len(polylines)}\n"
                f"# total vertices: {sum(len(pl) for pl in polylines)}\n"
            )
        except Exception as exc:
            raise http_error(422, "VALIDATION_ERROR", f"Could not load DXF: {exc}") from exc
    else:
        raise http_error(
            422,
            "VALIDATION_ERROR",
            f"Unsupported file extension {ext!r}. Expected .stl, .obj, .ply, or .dxf.",
        )

    record = _AssetRecord(
        asset_id=asset_id,
        kind=kind,
        filename=filename,
        path=path_str,
        summary=summary,
    )
    session.assets[asset_id] = record

    station_entity: FixtureEntryModel | None = None
    if add_to_station:
        frame_name = attach_to or "world"
        fixture_name = f"import_{asset_id[:8]}"
        fixture = FixtureEntryModel(
            name=fixture_name,
            parent_frame=frame_name,
            mesh_path=path_str,
        )
        try:
            from src.station.scene import Station

            async with session.lock:
                station = session.station
                # Only attach if the frame exists.
                frame_names = {f.name for f in station.frames}
                if frame_name not in frame_names:
                    frame_name = "world"
                    fixture = FixtureEntryModel(
                        name=fixture_name,
                        parent_frame=frame_name,
                        mesh_path=path_str,
                    )
                new_fixtures = list(station.fixtures) + [fixture.to_domain()]
                session.station = Station(
                    name=station.name,
                    frames=station.frames,
                    robots=station.robots,
                    tools=station.tools,
                    workpieces=station.workpieces,
                    fixtures=tuple(new_fixtures),
                    io_signals=station.io_signals,
                )
            station_entity = fixture
        except Exception:  # noqa: BLE001
            pass  # Don't fail the import if attaching fails.

    await session.push_event(
        {
            "type": "import_completed",
            "payload": {"asset_id": asset_id, "filename": filename, "summary": summary},
        }
    )

    return AssetImportResponse(
        asset_id=asset_id,
        kind=kind,  # type: ignore[arg-type]
        filename=filename,
        summary=summary,
        saved_path=path_str,
        station_entity=station_entity,
    )


@router.get("/urdf/{robot}/{file:path}")
async def get_urdf_file(robot: str, file: str) -> Response:
    """Serve a URDF or related file for the given robot.

    For project robots (``ur5``, ``abb_irb1200``), files are served from
    ``<repo_root>/assets/urdf/<robot>/``. For bundled robots (``panda``,
    ``iiwa``), they are resolved via ``pybullet_data``.

    Path traversal attempts return 404.
    """
    try:
        resolved = resolve_urdf_path(robot, file)
    except FileNotFoundError as exc:
        raise http_error(404, "ASSET_NOT_FOUND", str(exc)) from exc

    suffix = resolved.suffix.lower()
    if suffix in (".urdf", ".xml", ".xacro"):
        media_type = "application/xml"
    elif suffix in (".stl",):
        media_type = "application/octet-stream"
    elif suffix in (".dae",):
        media_type = "model/vnd.collada+xml"
    else:
        media_type = "application/octet-stream"

    return FileResponse(str(resolved), media_type=media_type)


__all__ = ["router"]
