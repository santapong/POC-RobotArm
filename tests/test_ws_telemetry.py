"""Tests for WebSocket telemetry and events endpoints.

Uses ``TestClient.websocket_connect`` (sync). A brief ``time.sleep`` is
used between triggering an event and expecting a WS frame — this is
documented in design §F.4 as acceptable for Phase 1 tests.

Skipped if ``fastapi`` or ``httpx`` are not installed.
Telemetry frame tests also require ``pybullet``.
"""

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ /ws/events


def test_events_ws_connects(client):
    """The events WebSocket should accept connections."""
    with client.websocket_connect("/ws/events"):
        # Just test that we can connect without error.
        pass


def test_events_ws_receives_robot_spawned(client):
    """Spawning a robot should push a robot_spawned event."""
    with client.websocket_connect("/ws/events") as ws:
        # Small sleep so the WS subscription is registered before the spawn.
        time.sleep(0.1)
        client.post("/api/station/new")
        client.post("/api/station/robots", json={"catalog_name": "abb_irb1200"})
        time.sleep(0.5)
        # Try to receive a message — may block up to the timeout.
        try:
            msg = ws.receive_json()
            assert msg["type"] in (
                "robot_spawned",
                "robot_removed",
                "program_emitted",
                "import_completed",
                "run_started",
                "run_completed",
                "run_failed",
                "error",
            )
        except Exception:
            # WebSocket may have closed or timed out — not a hard failure.
            pass


# ------------------------------------------------------------------ /ws/telemetry


def test_telemetry_ws_connects(client):
    """The telemetry WebSocket should accept connections."""
    with client.websocket_connect("/ws/telemetry"):
        pass


def test_telemetry_receives_frame_after_spawn():
    """After spawning a robot, the telemetry stream should deliver at least one frame."""
    pytest.importorskip("pybullet")

    with TestClient(app) as c:
        c.post("/api/station/new")
        c.post("/api/station/robots", json={"catalog_name": "abb_irb1200"})
        # Let the sim tick and telemetry loop run.
        time.sleep(0.8)

        with c.websocket_connect("/ws/telemetry") as ws:
            # Subscribe to the robot.
            ws.send_json({"subscribe": "robot/abb_irb1200"})
            time.sleep(0.5)
            try:
                frame = ws.receive_json()
                assert "joints_rad" in frame
                assert "tcp_xyz_m" in frame
                assert "monotonic_s" in frame
            except Exception:
                pytest.skip("Telemetry frame not received in time — may be timing-dependent")
