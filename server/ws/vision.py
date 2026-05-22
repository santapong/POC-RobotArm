"""WebSocket handler for ``/ws/vision/detections``.

Clients may send ``{"subscribe": "camera/<name>"}`` after connecting to filter
frames to a specific camera. Without a subscribe message all frames are forwarded.

Notes
-----
- A per-connection ``asyncio.Queue(maxsize=8)`` receives ``LiveDetectionFrame``
  payloads from ``VisionRuntime._live_loop``. Old frames are dropped
  (``put_nowait`` with silent discard) to avoid head-of-line blocking.
- The handler runs two concurrent tasks: a sender that drains the queue and a
  receiver that handles inbound subscribe messages.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from server.services.session import Session, get_session

router = APIRouter()


@router.websocket("/ws/vision/detections")
async def ws_vision_detections(
    websocket: WebSocket,
    session: Session = Depends(get_session),
) -> None:
    """Vision detections WebSocket: subscribe to live detection frames."""
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)

    runtime = session.vision_runtime
    if runtime is not None:
        runtime.subscribe(queue)

    # Optional camera filter — set by receiver when client sends subscribe.
    camera_filter: list[str | None] = [None]

    try:
        send_task = asyncio.create_task(_sender(websocket, queue, camera_filter))
        recv_task = asyncio.create_task(_receiver(websocket, camera_filter))
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
            runtime.unsubscribe(queue)


async def _sender(
    websocket: WebSocket,
    queue: asyncio.Queue,
    camera_filter: list[str | None],
) -> None:
    """Drain the detection queue and forward frames to the WS client."""
    while True:
        try:
            payload = await asyncio.wait_for(queue.get(), timeout=2.0)
            # Apply optional camera filter.
            filt = camera_filter[0]
            if filt is not None and payload.get("camera") != filt:
                continue
            await websocket.send_json(payload)
        except asyncio.TimeoutError:
            continue
        except Exception:  # noqa: BLE001
            break


async def _receiver(
    websocket: WebSocket,
    camera_filter: list[str | None],
) -> None:
    """Listen for subscribe messages from the client."""
    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                sub = msg.get("subscribe", "")
                if sub.startswith("camera/"):
                    camera_filter[0] = sub[len("camera/"):]
                elif sub == "":
                    camera_filter[0] = None
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass


__all__ = ["router"]
