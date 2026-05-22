"""Tests for the /ws/vision/detections WebSocket.

Skipped if fastapi, httpx, cv2, or numpy are not installed.
"""

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402


@pytest.fixture()
def red_cube_image(tmp_path):
    """Create a 640x480 BGR image with a red 60x60 square."""
    img = np.ones((480, 640, 3), dtype=np.uint8) * 255
    cx, cy = 320, 240
    half = 30
    img[cy - half : cy + half, cx - half : cx + half] = (0, 0, 200)
    path = str(tmp_path / "red_cube.jpg")
    cv2.imwrite(path, img)
    return path


def test_live_loop_pushes_detection_frame(red_cube_image):
    """Start live loop, connect to WS, receive >= 1 LiveDetectionFrame, stop."""
    with TestClient(app) as client:
        client.post(
            "/api/vision/cameras",
            json={
                "kind": "fake",
                "source": red_cube_image,
                "name": "ws_cam",
                "fake_image_paths": [red_cube_image],
                "fps": 15.0,
            },
        )
        client.post(
            "/api/vision/detectors",
            json={"kind": "color", "name": "ws_det", "config": {}},
        )

        # Allow capture thread to populate first frame.
        time.sleep(0.3)

        # Start live loop.
        resp = client.post(
            "/api/vision/detectors/ws_det/start",
            json={"camera": "ws_cam", "rate_hz": 5.0},
        )
        assert resp.status_code == 200
        assert resp.json()["running"] is True

        # Allow the live loop to run at least one iteration.
        time.sleep(0.5)

        with client.websocket_connect("/ws/vision/detections") as ws:
            msg = ws.receive_json()

        assert msg["camera"] == "ws_cam", f"Unexpected camera: {msg.get('camera')}"
        assert "detections" in msg
        assert isinstance(msg["detections"], list)

        # Stop live loop.
        stop_resp = client.post(
            "/api/vision/detectors/ws_det/stop",
            json={"camera": "ws_cam"},
        )
        assert stop_resp.status_code == 200
        assert stop_resp.json()["running"] is False
