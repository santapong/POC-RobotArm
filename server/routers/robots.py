"""Robot catalog and jog/state endpoints.

Endpoints
---------
- ``GET  /api/robots/catalog`` — list all available robots.
- ``POST /api/station/robots/{id}/jog`` — drive joints.
- ``GET  /api/station/robots/{id}/state`` — read current joint state.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from server.models.catalog import RobotCatalogEntry
from server.models.runtime import JogRequest, RobotStateResponse
from server.services.assets import urdf_url_for
from server.services.errors import http_error
from server.services.session import Session, get_session
from src.robots.catalog import list_specs

router = APIRouter()

# Vendor prefix map: catalog_name prefix → vendor display name.
_VENDOR_MAP: dict[str, str] = {
    "panda": "Franka",
    "ur5": "Universal Robots",
    "iiwa": "KUKA",
    "abb_irb1200": "ABB",
}


def _vendor_for(name: str) -> str:
    for prefix, vendor in _VENDOR_MAP.items():
        if name.startswith(prefix):
            return vendor
    return "Unknown"


@router.get("/api/robots/catalog", response_model=list[RobotCatalogEntry])
async def get_catalog() -> list[RobotCatalogEntry]:
    """Return all robots available in the catalog."""
    entries: list[RobotCatalogEntry] = []
    for spec in list_specs():
        limits = spec.limits
        entries.append(
            RobotCatalogEntry(
                name=spec.name,
                dof=spec.dof,
                vendor=_vendor_for(spec.name),
                urdf_url=urdf_url_for(spec.name),
                ee_link_name=spec.ee_link_name,
                home_q=spec.home_q,
                description=spec.description,
                qd_max_rad_s=limits.qd_max_rad_s if limits else None,
                qdd_max_rad_s2=limits.qdd_max_rad_s2 if limits else None,
            )
        )
    return entries


@router.post(
    "/api/station/robots/{robot_id}/jog",
    response_model=RobotStateResponse,
)
async def jog_robot(
    robot_id: str,
    body: JogRequest,
    session: Session = Depends(get_session),
) -> RobotStateResponse:
    """Drive the robot joints and return the updated state.

    Accepts either a single ``(joint_index, value_rad)`` or a full
    ``values_rad`` array. Joint values are clamped to the URDF limits.
    """
    runtime = session.sim_runtime
    if runtime is None:
        raise http_error(
            503,
            "SIM_DISCONNECTED",
            "Simulator not initialised. Spawn a robot first.",
            hint="Spawn a robot first to initialise the simulator.",
        )

    bridge = runtime.bridge

    def _apply_jog(s):  # runs on worker thread
        current = s.get_joint_angles()
        if body.values_rad is not None:
            target = list(body.values_rad)
        else:
            target = list(current)
            target[body.joint_index] = body.value_rad  # type: ignore[index]

        # Clamp to joint limits.
        clamped = False
        for i, (jinfo, val) in enumerate(zip(s.joints, target)):
            clamped_val = max(jinfo.lower, min(jinfo.upper, val))
            if clamped_val != val:
                clamped = True
            target[i] = clamped_val

        s.reset_joint_angles(target)
        return target, clamped

    try:
        target_angles, was_clamped = await asyncio.to_thread(bridge.submit, _apply_jog)
    except Exception as exc:
        raise http_error(503, "SIM_DISCONNECTED", f"Sim error: {exc}") from exc

    if was_clamped:
        raise http_error(
            409,
            "JOINT_LIMIT_CLAMPED",
            "One or more joint values were clamped to their limits.",
        )

    snap = await asyncio.to_thread(bridge.snapshot)
    return _snap_to_state(runtime.catalog_name, runtime.dof, snap)


@router.get(
    "/api/station/robots/{robot_id}/state",
    response_model=RobotStateResponse,
)
async def get_robot_state(
    robot_id: str,
    session: Session = Depends(get_session),
) -> RobotStateResponse:
    """Return the current joint state for a robot."""
    runtime = session.sim_runtime
    if runtime is None:
        raise http_error(
            503,
            "SIM_DISCONNECTED",
            "Simulator not initialised.",
            hint="Spawn a robot first to initialise the simulator.",
        )

    snap = await asyncio.to_thread(runtime.bridge.snapshot)
    return _snap_to_state(runtime.catalog_name, runtime.dof, snap)


def _snap_to_state(catalog_name: str, dof: int, snap: dict) -> RobotStateResponse:
    ee_pos = snap.get("ee_position", [0.0, 0.0, 0.0])
    ee_orn = snap.get("ee_orientation", [0.0, 0.0, 0.0, 1.0])
    # ee_orientation from PyBullet is xyzw; convert to wxyz
    tcp_quat_wxyz = (
        float(ee_orn[3]),
        float(ee_orn[0]),
        float(ee_orn[1]),
        float(ee_orn[2]),
    )
    traj = snap.get("trajectory", {})
    moving = bool(traj.get("active", False))
    return RobotStateResponse(
        catalog_name=catalog_name,
        dof=dof,
        joints_rad=[float(a) for a in snap.get("joint_angles", [])],
        tcp_xyz_m=(float(ee_pos[0]), float(ee_pos[1]), float(ee_pos[2])),
        tcp_quat_wxyz=tcp_quat_wxyz,
        moving=moving,
        error=None if snap.get("connected") else "Simulator disconnected",
    )


__all__ = ["router"]
