"""Tests for robot catalog, jog, and state endpoints.

Jog and state tests require PyBullet (``pytest.importorskip("pybullet")``).
Catalog test works without PyBullet.

Skipped if ``fastapi`` or ``httpx`` are not installed.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ catalog


def test_catalog_returns_list(client):
    resp = client.get("/api/robots/catalog")
    assert resp.status_code == 200
    entries = resp.json()
    assert isinstance(entries, list)
    assert len(entries) >= 1


def test_catalog_entry_shape(client):
    resp = client.get("/api/robots/catalog")
    entry = resp.json()[0]
    for field in ("name", "dof", "vendor", "urdf_url", "home_q", "description"):
        assert field in entry, f"Missing field: {field}"


def test_catalog_contains_known_robots(client):
    resp = client.get("/api/robots/catalog")
    names = {e["name"] for e in resp.json()}
    assert "abb_irb1200" in names
    assert "ur5" in names


# ------------------------------------------------------------------ state + jog (requires pybullet)


@pytest.fixture()
def client_with_robot(client):
    """Spawn a robot and return (client, robot_id)."""
    pytest.importorskip("pybullet")
    import time

    client.post("/api/station/new")
    resp = client.post("/api/station/robots", json={"catalog_name": "abb_irb1200"})
    assert resp.status_code == 200, resp.text
    robot_id = resp.json()["id"]
    # Give the sim tick loop a moment to run.
    time.sleep(0.3)
    return client, robot_id


def test_get_robot_state(client_with_robot):
    c, robot_id = client_with_robot
    resp = c.get(f"/api/station/robots/{robot_id}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert "joints_rad" in body
    assert "tcp_xyz_m" in body
    assert "moving" in body


def test_jog_single_joint(client_with_robot):
    c, robot_id = client_with_robot
    resp = c.post(
        f"/api/station/robots/{robot_id}/jog",
        json={"joint_index": 0, "value_rad": 0.1},
    )
    # May return 200 or 409 (clamped) — both are valid responses.
    assert resp.status_code in (200, 409)
    if resp.status_code == 200:
        body = resp.json()
        assert "joints_rad" in body


def test_jog_full_set(client_with_robot):
    c, robot_id = client_with_robot
    # ABB IRB1200 is 6 DOF; send zeros.
    resp = c.post(
        f"/api/station/robots/{robot_id}/jog",
        json={"values_rad": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
    )
    assert resp.status_code in (200, 409)


def test_jog_invalid_body_returns_422(client):
    client.post("/api/station/new")
    # Both joint_index+value_rad AND values_rad set → validation error.
    resp = client.post(
        "/api/station/robots/abb_irb1200/jog",
        json={"joint_index": 0, "value_rad": 0.1, "values_rad": [0.0]},
    )
    assert resp.status_code == 422


def test_jog_without_sim_returns_503(client):
    client.post("/api/station/new")
    # No robot spawned → no sim → 503.
    resp = client.post(
        "/api/station/robots/abb_irb1200/jog",
        json={"joint_index": 0, "value_rad": 0.0},
    )
    assert resp.status_code == 503
