"""Tests for vision REST endpoints: register camera/detector, detect, delete.

Skipped if fastapi, httpx, cv2, or numpy are not installed.
"""


import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def red_cube_image(tmp_path):
    """Create a 640x480 BGR image with a red 60x60 square at the centre."""
    img = np.ones((480, 640, 3), dtype=np.uint8) * 255  # white background
    cx, cy = 320, 240
    half = 30
    img[cy - half : cy + half, cx - half : cx + half] = (0, 0, 200)  # BGR red
    path = str(tmp_path / "red_cube.jpg")
    cv2.imwrite(path, img)
    return path


def test_register_fake_camera(client, red_cube_image):
    resp = client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "test_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "test_cam"
    assert body["kind"] == "fake"


def test_list_cameras(client, red_cube_image):
    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "cam_list",
            "fake_image_paths": [red_cube_image],
        },
    )
    resp = client.get("/api/vision/cameras")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "cam_list" in names


def test_register_color_detector(client, red_cube_image):
    # Register camera first
    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "ep_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    resp = client.post(
        "/api/vision/detectors",
        json={"kind": "color", "name": "ep_det", "config": {}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "ep_det"
    assert body["kind"] == "color"


def test_list_detectors(client, red_cube_image):
    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "list_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    client.post(
        "/api/vision/detectors",
        json={"kind": "color", "name": "list_det", "config": {}},
    )
    resp = client.get("/api/vision/detectors")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "list_det" in names


def test_run_detection(client, red_cube_image):
    import time

    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "run_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    client.post(
        "/api/vision/detectors",
        json={"kind": "color", "name": "run_det", "config": {}},
    )
    # Allow capture thread to read first frame.
    time.sleep(0.2)
    resp = client.post(
        "/api/vision/detectors/run_det/run",
        json={"camera": "run_cam", "return_grasp": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["camera"] == "run_cam"
    assert body["detector"] == "run_det"
    assert isinstance(body["detections"], list)
    assert len(body["detections"]) >= 1


def test_delete_camera(client, red_cube_image):
    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "del_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    resp = client.delete("/api/vision/cameras/del_cam")
    assert resp.status_code == 200
    assert resp.json()["removed"] == "del_cam"


def test_delete_detector(client, red_cube_image):
    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "del_det_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    client.post(
        "/api/vision/detectors",
        json={"kind": "color", "name": "del_det", "config": {}},
    )
    resp = client.delete("/api/vision/detectors/del_det")
    assert resp.status_code == 200
    assert resp.json()["removed"] == "del_det"


def test_delete_unknown_camera_returns_404(client):
    resp = client.delete("/api/vision/cameras/no_such_cam")
    assert resp.status_code == 404


def test_delete_unknown_detector_returns_404(client):
    resp = client.delete("/api/vision/detectors/no_such_det")
    assert resp.status_code == 404


def test_bootstrap_intrinsics(client, red_cube_image):
    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "intr_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    intrinsics = {
        "fx": 500.0,
        "fy": 500.0,
        "cx": 320.0,
        "cy": 240.0,
        "width": 640,
        "height": 480,
        "dist_coeffs": [0.0, 0.0, 0.0, 0.0, 0.0],
    }
    resp = client.post("/api/vision/cameras/intr_cam/intrinsics", json=intrinsics)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fx"] == 500.0


def test_bootstrap_extrinsics(client, red_cube_image):
    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "extr_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    extrinsics = {
        "R_cam_in_world": [
            [1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, -1.0],
        ],
        "t_cam_in_world": [0.0, 0.0, 0.6],
        "reference_frame": "world",
        "mount": "eye_to_hand",
    }
    resp = client.post("/api/vision/cameras/extr_cam/extrinsics", json=extrinsics)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["t_cam_in_world"] == [0.0, 0.0, 0.6]


def test_snapshot_returns_jpeg(client, red_cube_image):
    import time

    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "snap_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    time.sleep(0.2)
    resp = client.get("/api/vision/cameras/snap_cam/snapshot")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    # JPEG SOI marker
    assert resp.content[:2] == b"\xff\xd8"


def test_charuco_pose_accepts_json_body(client, red_cube_image):
    """POST /charuco_pose with a JSON body (not Form) parses correctly.

    A synthetic RGB image contains no ChArUco board, so we expect either
    200 (unlikely but valid) or 422 with VISION_CALIBRATION_FAILED.
    The point is that the request shape parses without a 422 VALIDATION_ERROR.
    """
    import time

    # Register camera with a synthetic image.
    client.post(
        "/api/vision/cameras",
        json={
            "kind": "fake",
            "source": red_cube_image,
            "name": "charuco_cam",
            "fake_image_paths": [red_cube_image],
        },
    )
    time.sleep(0.2)

    # Bootstrap intrinsics so the endpoint passes the intrinsics guard.
    client.post(
        "/api/vision/cameras/charuco_cam/intrinsics",
        json={
            "fx": 500.0,
            "fy": 500.0,
            "cx": 320.0,
            "cy": 240.0,
            "width": 640,
            "height": 480,
            "dist_coeffs": [0.0, 0.0, 0.0, 0.0, 0.0],
        },
    )

    resp = client.post(
        "/api/vision/cameras/charuco_cam/charuco_pose",
        json={
            "squares_x": 5,
            "squares_y": 7,
            "square_length_m": 0.04,
            "marker_length_m": 0.03,
            "aruco_dict_id": 0,
        },
    )
    # No ChArUco in the synthetic image — expect calibration failure, not a
    # parse error.  A 200 would also be valid if the detector somehow fires.
    assert resp.status_code in (200, 422)
    if resp.status_code == 422:
        assert resp.json()["code"] == "VISION_CALIBRATION_FAILED"


def test_grasp_preview_accepts_full_request(client, red_cube_image):
    """POST /grasp_preview with the full GraspPreviewRequest body.

    Bootstraps a station + robot + sim, then POSTs a world-frame grasp and
    asserts the response contains the three required fields.
    Skipped if pybullet is not installed.
    """
    import time

    pytest.importorskip("pybullet")

    # Bootstrap station + robot (which also starts SimRuntime).
    client.post("/api/station/new")
    spawn = client.post("/api/station/robots", json={"catalog_name": "abb_irb1200"})
    assert spawn.status_code == 200, spawn.text
    robot_id = spawn.json()["id"]

    # Give the sim tick loop a moment to settle.
    time.sleep(0.3)

    resp = client.post(
        "/api/vision/grasp_preview",
        json={
            "robot_id": robot_id,
            "grasp": {
                "xyz_m": [0.3, 0.0, 0.3],
                "quat_wxyz": [1.0, 0.0, 0.0, 0.0],
                "frame": "world",
                "approach_vector": [0.0, 0.0, -1.0],
            },
            "preview_mode": "ik_only",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["reachable"], bool)
    assert isinstance(body["joints_rad"], list)
    assert isinstance(body["ik_residual_m"], float)
