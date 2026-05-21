"""WebSocket handler for ``/ws/telemetry``.

Clients send ``{"subscribe": "robot/<id>"}`` after connecting. The server
then pushes ``TelemetryFrame`` JSON at ~30 Hz until the client disconnects.

Notes
-----
- A per-connection ``asyncio.Queue(maxsize=4)`` receives frames from
  ``SimRuntime._telemetry_loop``.  Old frames are dropped (``put_nowait``
  with silent discard on full) to avoid head-of-line blocking at slow clients.
- The handler runs two concurrent tasks: one that drains the queue and sends
  frames, one that listens for incoming ``subscribe`` messages from the client.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from server.services.session import Session, get_session

router = APIRouter()


@router.websocket("/ws/telemetry")
async def ws_telemetry(
    websocket: WebSocket,
    session: Session = Depends(get_session),
) -> None:
    """Telemetry WebSocket: subscribe to robot state at ~30 Hz."""
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    runtime = session.sim_runtime

    if runtime is not None:
        runtime.subscribe_telemetry(queue)

    try:
        send_task = asyncio.create_task(_sender(websocket, queue))
        recv_task = asyncio.create_task(_receiver(websocket))
        _, pending = await asyncio.wait(
            {send_task, recv_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        if runtime is not None:
            runtime.unsubscribe_telemetry(queue)


async def _sender(websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Drain the telemetry queue and forward frames to the WS client."""
    while True:
        try:
            frame = await asyncio.wait_for(queue.get(), timeout=2.0)
            await websocket.send_json(frame)
        except asyncio.TimeoutError:
            continue
        except Exception:  # noqa: BLE001
            break


async def _receiver(websocket: WebSocket) -> None:
    """Listen for subscribe messages from the client (ignored for now)."""
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass


__all__ = ["router"]
