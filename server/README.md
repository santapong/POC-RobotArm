# POC-RobotArm Server

FastAPI skeleton for the web app (Phase 0). Install with:

    pip install -e .[server,dev]

Run with:

    make server     # or: python -m server

Endpoints today:

- `GET /health` -> `{"status": "ok"}`
- `WebSocket /ws/telemetry` -> emits `{"type": "hello"}` on connect, then closes.

Domain endpoints (motion, vision, planning, I/O) land in later phases. See the root `README.md` and `.claude/plans/can-you-create-an-sparkling-garden.md`.
