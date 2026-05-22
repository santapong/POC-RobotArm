"""WebSocket handler for ``/ws/planning/progress``.

Clients receive ``PlanProgressFrame`` JSON on every stage transition and
heartbeat (every 500 ms). An optional subscribe message filters frames to a
specific plan::

    {"subscribe": "plan/<plan_id>"}

Sending ``{"subscribe": ""}`` (empty string) resets to receive all plans.

Notes
-----
- A per-connection ``asyncio.Queue(maxsize=8)`` receives payloads from
  ``PlanningRuntime._publish_progress``. Old frames are dropped silently
  (``put_nowait``) to avoid head-of-line blocking.
- Two concurrent tasks per connection: a sender that drains the queue and a
  receiver that handles inbound subscribe messages.
- If no ``PlanningRuntime`` exists when the client connects, the connection
  stays open but receives no frames until a plan is submitted.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from server.services.session import Session, get_session

router = APIRouter()


@router.websocket("/ws/planning/progress")
async def ws_planning_progress(
    websocket: WebSocket,
    session: Session = Depends(get_session),
) -> None:
    """Planning progress WebSocket: subscribe to plan stage transitions."""
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)

    runtime = session.planning_runtime
    if runtime is not None:
        runtime.subscribe_progress(queue)

    # Optional plan_id filter — set by receiver.
    plan_filter: list[str | None] = [None]

    try:
        send_task = asyncio.create_task(_sender(websocket, queue, plan_filter))
        recv_task = asyncio.create_task(_receiver(websocket, plan_filter))
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
            runtime.unsubscribe_progress(queue)


async def _sender(
    websocket: WebSocket,
    queue: asyncio.Queue,
    plan_filter: list[str | None],
) -> None:
    """Drain the progress queue and forward frames to the WS client."""
    while True:
        try:
            payload = await asyncio.wait_for(queue.get(), timeout=2.0)
            filt = plan_filter[0]
            if filt is not None and payload.get("plan_id") != filt:
                continue
            await websocket.send_json(payload)
        except asyncio.TimeoutError:
            continue
        except Exception:  # noqa: BLE001
            break


async def _receiver(
    websocket: WebSocket,
    plan_filter: list[str | None],
) -> None:
    """Listen for subscribe messages from the client."""
    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                sub = msg.get("subscribe", "")
                if sub.startswith("plan/"):
                    plan_filter[0] = sub[len("plan/"):]
                elif sub == "":
                    plan_filter[0] = None
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass


__all__ = ["router"]
