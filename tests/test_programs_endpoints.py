"""Tests for program listing, post-processing, and run endpoints.

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


# ------------------------------------------------------------------ list / get


def test_list_programs(client):
    resp = client.get("/api/programs")
    assert resp.status_code == 200
    programs = resp.json()
    assert isinstance(programs, list)
    ids = [p["id"] for p in programs]
    assert "demo" in ids


def test_get_demo_program(client):
    resp = client.get("/api/programs/demo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "StationDemo"
    assert "procedures" in body


def test_get_unknown_program_returns_404(client):
    resp = client.get("/api/programs/does_not_exist")
    assert resp.status_code == 404


# ------------------------------------------------------------------ post


def test_post_rapid(client):
    resp = client.post("/api/programs/demo/post", json={"vendor": "rapid"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["vendor"] == "rapid"
    assert "PROC" in body["source"] or "MODULE" in body["source"]
    assert body["file_extension"] == ".mod"


def test_post_krl(client):
    resp = client.post("/api/programs/demo/post", json={"vendor": "krl"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["vendor"] == "krl"
    assert body["file_extension"] == ".src"


def test_post_urscript(client):
    resp = client.post("/api/programs/demo/post", json={"vendor": "urscript"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["vendor"] == "urscript"
    assert "def main" in body["source"]
    assert body["file_extension"] == ".script"


def test_post_unknown_program_returns_404(client):
    resp = client.post("/api/programs/nonexistent/post", json={"vendor": "rapid"})
    assert resp.status_code == 404


# ------------------------------------------------------------------ run


def test_run_without_sim_returns_run_id(client):
    resp = client.post("/api/programs/demo/run", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body


def test_get_run_record(client):
    run_resp = client.post("/api/programs/demo/run", json={})
    run_id = run_resp.json()["run_id"]
    resp = client.get(f"/api/programs/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["program_id"] == "demo"
    assert body["status"] in ("queued", "running", "completed", "failed")


def test_stop_run(client):
    run_resp = client.post("/api/programs/demo/run", json={})
    run_id = run_resp.json()["run_id"]
    resp = client.post(f"/api/programs/runs/{run_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("failed", "completed")


def test_get_unknown_run_returns_404(client):
    resp = client.get("/api/programs/runs/nonexistent-run-id")
    assert resp.status_code == 404
