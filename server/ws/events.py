"""WebSocket handler for ``/ws/events``.

The server pushes structured event frames when station mutations happen:
``robot_spawned``, ``robot_removed``, ``program_emitted``, ``import_completed``,
``run_started``, ``run_completed``, ``run_failed``, ``error``.

Notes
-----
- Each connection gets a dedicated ``asyncio.Queue``, subscribed to the
  session event bus in ``Session._event_subscribers``.
- Clients receive events passively; no inbound messages are expected.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from server.services.session import Session, get_session

router = APIRouter()


@router.websocket("/ws/events")
async def ws_events(
    websocket: WebSocket,
    session: Session = Depends(get_session),
) -> None:
    """Events WebSocket: receive station-level event notifications."""
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    session.subscribe_events(queue)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=2.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
            except Exception:  # noqa: BLE001
                break
    finally:
        session.unsubscribe_events(queue)


__all__ = ["router"]
