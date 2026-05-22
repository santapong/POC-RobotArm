"""Station management router.

Endpoints
---------
- ``POST /api/station/new`` — reset to an empty station.
- ``POST /api/station/load`` — replace station from uploaded JSON.
- ``GET  /api/station`` — return current station.
- ``POST /api/station/save`` — return station JSON for download.
- ``POST /api/station/robots`` — spawn a robot (lazy-inits SimRuntime).
- ``DELETE /api/station/robots/{id}`` — remove a robot.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from server.models.station import StationModel
from server.services.errors import http_error
from server.services.session import Session, get_session
from server.services.sim import SimRuntime
from src.robots.catalog import get_spec
from src.station.scene import Frame, RobotEntry, Station, from_dict

router = APIRouter(prefix="/api/station")


@router.post("/new", response_model=StationModel)
async def new_station(session: Session = Depends(get_session)) -> StationModel:
    """Reset the session to an empty station containing only a ``world`` frame."""
    async with session.lock:
        session.station = Station(
            name="untitled_station",
            frames=(Frame("world", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent=None),),
        )
        session.station_path = None
    return StationModel.from_domain(session.station)


@router.post("/load", response_model=StationModel)
async def load_station(
    file: UploadFile,
    session: Session = Depends(get_session),
) -> StationModel:
    """Replace the current station from an uploaded JSON file."""
    raw = await file.read()
    try:
        data = json.loads(raw)
        station = from_dict(data, Station)
    except Exception as exc:
        raise http_error(
            422, "VALIDATION_ERROR", f"Could not parse station JSON: {exc}"
        ) from exc
    async with session.lock:
        session.station = station
        session.station_path = None
    return StationModel.from_domain(session.station)


@router.get("", response_model=StationModel)
async def get_station(session: Session = Depends(get_session)) -> StationModel:
    """Return the current station."""
    return StationModel.from_domain(session.station)


@router.post("/save")
async def save_station(session: Session = Depends(get_session)) -> Response:
    """Return the station as a JSON download.

    Always returns ``application/json``; the filename hint is in
    ``Content-Disposition``.
    """
    from src.station.scene import to_dict as station_to_dict

    data = station_to_dict(session.station)
    body = json.dumps(data, indent=2)
    filename = f"{session.station.name}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class SpawnRobotBody(BaseModel):
    """Body for ``POST /api/station/robots``."""

    catalog_name: str
    base_xyz_m: list[float] = [0.0, 0.0, 0.0]
    base_quat_wxyz: list[float] = [1.0, 0.0, 0.0, 0.0]


@router.post("/robots")
async def spawn_robot(
    body: SpawnRobotBody,
    session: Session = Depends(get_session),
) -> dict:
    """Add a robot to the station and lazily initialise the SimRuntime.

    Returns ``{"id": str, "station": StationModel}``.
    """
    # Validate catalog name — raises ValueError for unknown names.
    try:
        get_spec(body.catalog_name)
    except (ValueError, KeyError) as exc:
        raise http_error(422, "VALIDATION_ERROR", str(exc)) from exc

    async with session.lock:
        station = session.station
        frame_name = f"{body.catalog_name}_base"
        frames = list(station.frames)
        if not any(f.name == frame_name for f in frames):
            parent = "world" if any(f.name == "world" for f in frames) else None
            frames.append(
                Frame(
                    frame_name,
                    tuple(body.base_xyz_m[:3]),  # type: ignore[arg-type]
                    tuple(body.base_quat_wxyz[:4]),  # type: ignore[arg-type]
                    parent=parent,
                )
            )

        existing_names = {r.name for r in station.robots}
        candidate = body.catalog_name
        idx = 1
        while candidate in existing_names:
            idx += 1
            candidate = f"{body.catalog_name}_{idx}"

        robots = list(station.robots) + [
            RobotEntry(name=candidate, robot_catalog_name=body.catalog_name, base_frame=frame_name)
        ]
        session.station = Station(
            name=station.name,
            frames=tuple(frames),
            robots=tuple(robots),
            tools=station.tools,
            workpieces=station.workpieces,
            fixtures=station.fixtures,
            io_signals=station.io_signals,
        )

        # Lazily initialise SimRuntime for the first robot only.
        if session.sim_runtime is None:
            runtime = SimRuntime(body.catalog_name)
            runtime.start()
            session.sim_runtime = runtime

    await session.push_event(
        {"type": "robot_spawned", "payload": {"id": candidate, "catalog_name": body.catalog_name}}
    )

    return {"id": candidate, "station": StationModel.from_domain(session.station)}


@router.delete("/robots/{robot_id}", response_model=StationModel)
async def delete_robot(
    robot_id: str,
    session: Session = Depends(get_session),
) -> StationModel:
    """Remove a robot from the station; tear down SimRuntime if it was the sim robot."""
    async with session.lock:
        station = session.station
        robots = [r for r in station.robots if r.name != robot_id]
        if len(robots) == len(station.robots):
            raise http_error(
                404, "ROBOT_UNKNOWN", f"Robot '{robot_id}' not found in station."
            )

        session.station = Station(
            name=station.name,
            frames=station.frames,
            robots=tuple(robots),
            tools=station.tools,
            workpieces=station.workpieces,
            fixtures=station.fixtures,
            io_signals=station.io_signals,
        )

        # Tear down sim if the deleted robot was the sim-loaded one.
        if session.sim_runtime is not None and session.sim_runtime.catalog_name == robot_id:
            asyncio.create_task(session.sim_runtime.stop())
            session.sim_runtime = None
            # Import lazily so this module is usable without pybullet installed.
            from src.simulation.bridge import SimBridge

            SimBridge.shutdown()

    await session.push_event(
        {"type": "robot_removed", "payload": {"id": robot_id}}
    )

    return StationModel.from_domain(session.station)


__all__ = ["router"]
