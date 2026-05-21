"""Phase 0 FastAPI app: /health endpoint + /ws/telemetry stub."""

from fastapi import FastAPI, WebSocket

app = FastAPI(title="POC-RobotArm Server", version="0.0.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/telemetry")
async def telemetry(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "hello"})
    await websocket.close()
