"""Tests for asset import and URDF serving endpoints.

Skipped if ``fastapi`` or ``httpx`` are not installed.
CAD import tests require ``trimesh`` and ``ezdxf`` (skipped if absent).
"""

import io
import struct

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ URDF serving


def test_urdf_served_for_project_robot(client):
    """Project robots (abb_irb1200, ur5) should have their URDF served."""
    # The URDF URL is in the catalog.
    catalog_resp = client.get("/api/robots/catalog")
    entries = {e["name"]: e for e in catalog_resp.json()}

    robot = "abb_irb1200"
    if robot in entries:
        url = entries[robot]["urdf_url"]
        # Strip the /api prefix since TestClient routes directly.
        path = url  # full path starts with /api/assets/urdf/...
        resp = client.get(path)
        assert resp.status_code == 200
        assert "robot" in resp.text.lower() or "urdf" in resp.text.lower()


def test_urdf_path_traversal_rejected(client):
    """Attempting ``../`` in the file path should return 404."""
    resp = client.get("/api/assets/urdf/abb_irb1200/../../etc/passwd")
    assert resp.status_code == 404


def test_urdf_nonexistent_file_returns_404(client):
    resp = client.get("/api/assets/urdf/abb_irb1200/totally_fake_file.urdf")
    assert resp.status_code == 404


def test_urdf_unknown_robot_returns_404(client):
    resp = client.get("/api/assets/urdf/robot_does_not_exist/model.urdf")
    assert resp.status_code == 404


# ------------------------------------------------------------------ Asset import (mesh)


def _minimal_stl_bytes() -> bytes:
    """Return a minimal binary STL with one triangle."""
    header = b"POC-RobotArm test STL" + b"\x00" * (80 - 21)
    num_triangles = struct.pack("<I", 1)
    normal = struct.pack("<fff", 0.0, 0.0, 1.0)
    v1 = struct.pack("<fff", 0.0, 0.0, 0.0)
    v2 = struct.pack("<fff", 1.0, 0.0, 0.0)
    v3 = struct.pack("<fff", 0.0, 1.0, 0.0)
    attrib = struct.pack("<H", 0)
    return header + num_triangles + normal + v1 + v2 + v3 + attrib


@pytest.mark.skipif(
    not pytest.importorskip("trimesh", reason="trimesh not installed"),  # type: ignore[arg-type]
    reason="trimesh not installed",
)
def test_import_stl_mesh(client):
    pytest.importorskip("trimesh")
    stl_bytes = _minimal_stl_bytes()
    resp = client.post(
        "/api/assets/import",
        files={"file": ("test.stl", stl_bytes, "model/stl")},
        data={"add_to_station": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "mesh"
    assert body["filename"] == "test.stl"
    assert "vertices" in body["summary"]


def test_import_unsupported_extension_returns_422(client):
    resp = client.post(
        "/api/assets/import",
        files={"file": ("test.txt", b"hello", "text/plain")},
        data={"add_to_station": "false"},
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------ Asset import (DXF)


@pytest.mark.skipif(
    not pytest.importorskip("ezdxf", reason="ezdxf not installed"),  # type: ignore[arg-type]
    reason="ezdxf not installed",
)
def test_import_dxf(client):
    ezdxf = pytest.importorskip("ezdxf")
    # Create a minimal DXF in memory.
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0))  # 1m line in mm
    buf = io.StringIO()
    doc.write(buf)
    dxf_bytes = buf.getvalue().encode()

    resp = client.post(
        "/api/assets/import",
        files={"file": ("test.dxf", dxf_bytes, "application/dxf")},
        data={"add_to_station": "false"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "dxf"
    assert "polylines" in body["summary"]
