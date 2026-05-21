"""Tests for station management endpoints.

Covers: POST /api/station/new, POST /api/station/load,
        GET /api/station, POST /api/station/save.

Skipped if ``fastapi`` or ``httpx`` are not installed.
"""

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_new_station_returns_world_frame(client):
    resp = client.post("/api/station/new")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "untitled_station"
    frame_names = [f["name"] for f in body["frames"]]
    assert "world" in frame_names


def test_get_station_after_new(client):
    client.post("/api/station/new")
    resp = client.get("/api/station")
    assert resp.status_code == 200
    body = resp.json()
    assert "frames" in body


def test_load_station_from_json(client):
    # Build a minimal station dict that round-trips through from_dict.
    station_dict = {
        "__type__": "Station",
        "name": "test_station",
        "frames": [
            {
                "__type__": "Frame",
                "name": "world",
                "xyz_m": [0.0, 0.0, 0.0],
                "quat_wxyz": [1.0, 0.0, 0.0, 0.0],
                "parent": None,
            }
        ],
        "robots": [],
        "tools": [],
        "workpieces": [],
        "fixtures": [],
        "io_signals": [],
    }
    raw = json.dumps(station_dict).encode()
    resp = client.post(
        "/api/station/load",
        files={"file": ("station.json", raw, "application/json")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "test_station"


def test_load_station_bad_json_returns_422(client):
    resp = client.post(
        "/api/station/load",
        files={"file": ("bad.json", b"not json at all", "application/json")},
    )
    assert resp.status_code == 422


def test_save_station_returns_json(client):
    client.post("/api/station/new")
    resp = client.post("/api/station/save")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    data = json.loads(resp.content)
    assert data["__type__"] == "Station"


def test_spawn_robot_adds_to_station(client):
    client.post("/api/station/new")
    resp = client.post(
        "/api/station/robots",
        json={"catalog_name": "abb_irb1200"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert "station" in body
    robot_names = [r["name"] for r in body["station"]["robots"]]
    assert body["id"] in robot_names


def test_spawn_unknown_robot_returns_error(client):
    client.post("/api/station/new")
    resp = client.post(
        "/api/station/robots",
        json={"catalog_name": "nonexistent_robot_xyz"},
    )
    # Should be 4xx or 5xx — catalog raises ValueError for unknown names.
    assert resp.status_code >= 400


def test_delete_robot(client):
    client.post("/api/station/new")
    spawn = client.post("/api/station/robots", json={"catalog_name": "abb_irb1200"})
    robot_id = spawn.json()["id"]

    resp = client.delete(f"/api/station/robots/{robot_id}")
    assert resp.status_code == 200
    robot_names = [r["name"] for r in resp.json()["robots"]]
    assert robot_id not in robot_names


def test_delete_nonexistent_robot_returns_404(client):
    client.post("/api/station/new")
    resp = client.delete("/api/station/robots/does_not_exist")
    assert resp.status_code == 404
