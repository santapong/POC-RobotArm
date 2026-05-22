"""WebSocket handler for ``/ws/io/stream``.

Clients receive :class:`~server.models.io.IoEventModel` JSON frames on every
I/O event (connection-status change, value change, write acknowledgement, or
error).  An optional subscribe message filters frames to a specific
connection::

    {"subscribe": "connection/<name>"}

Sending ``{"subscribe": ""}`` (empty string) resets to receive events from
all connections.

Notes
-----
- A per-connection ``asyncio.Queue(maxsize=64)`` receives raw
  ``IoEvent`` payloads from ``IoRuntime._publish``.  The larger cap (64 vs
  Plan's 8) reflects the higher event rate of I/O streaming.  Overflow
  drops the oldest event via ``put_nowait``.
- Two concurrent tasks per WS connection: a sender that drains the queue
  and a receiver that handles inbound subscribe messages.
- No heartbeat — I/O events are intrinsically chatty; silence genuinely
  implies no events (contrast with planning where a stalled solver emits
  nothing for seconds).
- If no ``IoRuntime`` exists when the client connects, the connection stays
  open but receives no events until one is created.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from server.services.session import Session, get_session

router = APIRouter()


@router.websocket("/ws/io/stream")
async def ws_io_stream(
    websocket: WebSocket,
    session: Session = Depends(get_session),
) -> None:
    """I/O event WebSocket: subscribe to live I/O events."""
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)

    runtime = session.io_runtime
    if runtime is not None:
        runtime.subscribe(queue)

    # Optional connection-name filter — a mutable list so the closure can
    # share a reference between the sender and receiver tasks.
    conn_filter: list[str | None] = [None]

    try:
        send_task = asyncio.create_task(_sender(websocket, queue, conn_filter))
        recv_task = asyncio.create_task(_receiver(websocket, conn_filter))
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
    conn_filter: list[str | None],
) -> None:
    """Drain the I/O event queue and forward frames to the WS client.

    Each ``IoEvent`` from ``IoRuntime`` is translated to the wire-model
    shape (``IoEventModel`` / TypeScript ``IoEventModel``) and serialised
    as JSON.  The ``kind`` field from the lib becomes ``type`` on the wire.
    """
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=2.0)
            # Apply optional connection filter.
            filt = conn_filter[0]
            conn_name = event.connection if hasattr(event, "connection") else event.get("connection")
            if filt is not None and conn_name != filt:
                continue

            # Translate IoEvent (lib domain) → wire dict matching IoEventModel.
            payload = _event_to_wire(event)
            await websocket.send_json(payload)
        except asyncio.TimeoutError:
            continue
        except Exception:  # noqa: BLE001
            break


async def _receiver(
    websocket: WebSocket,
    conn_filter: list[str | None],
) -> None:
    """Listen for subscribe messages from the client.

    Accepted message shape::

        {"subscribe": "connection/<name>"}   # filter to one connection
        {"subscribe": ""}                    # clear filter (receive all)
    """
    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                sub = msg.get("subscribe", "")
                if sub.startswith("connection/"):
                    conn_filter[0] = sub[len("connection/"):]
                elif sub == "":
                    conn_filter[0] = None
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass


def _event_to_wire(event: object) -> dict:
    """Convert an ``IoEvent`` domain object to a JSON-serialisable wire dict.

    The domain ``IoEvent.kind`` becomes ``type`` on the wire to match the
    TypeScript ``IoEventModel.type`` field.

    Parameters
    ----------
    event:
        An ``IoEvent`` dataclass (from ``src.io.types``) or a plain dict
        (defensive fallback).
    """
    if isinstance(event, dict):
        # Already a dict — normalise ``kind`` → ``type`` if needed.
        out = dict(event)
        if "kind" in out and "type" not in out:
            out["type"] = out.pop("kind")
        return out

    # Domain dataclass path.
    kind = getattr(event, "kind", None)
    status_raw = getattr(event, "status", None)

    # status may be a ConnectionStatusKind enum or a raw string.
    status_str: str | None
    if status_raw is None:
        status_str = None
    elif hasattr(status_raw, "value"):
        status_str = status_raw.value
    else:
        status_str = str(status_raw)

    return {
        "type": kind.value if hasattr(kind, "value") else kind,
        "connection": getattr(event, "connection", ""),
        "signal": getattr(event, "signal", None),
        "value": getattr(event, "value", None),
        "status": status_str,
        "error_code": getattr(event, "error_code", None),
        "error_message": getattr(event, "error_message", None),
        "monotonic_s": getattr(event, "monotonic_s", 0.0),
    }


__all__ = ["router"]
