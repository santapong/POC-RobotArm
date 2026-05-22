"""Phase 2 exit gate: red-cube image → FakeCamera + ColorDetector → grasp pose.

Bootstraps intrinsics and extrinsics via the setter endpoints, registers a
FakeCamera pointed at a synthetic red-cube image, registers a ColorDetector,
runs one-shot detection with ``return_grasp=true``, and asserts the returned
grasp pose xyz is within 5 mm of world (0, 0, 0).

Skipped if fastapi, httpx, cv2, or numpy are not installed.
"""

import math
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402


def _build_red_cube_image(tmp_path) -> str:
    """640×480 white image with a 60×60 red square centred at (320, 240)."""
    img = np.ones((480, 640, 3), dtype=np.uint8) * 255
    cx, cy = 320, 240
    half = 30
    img[cy - half : cy + half, cx - half : cx + half] = (0, 0, 200)  # BGR red
    path = str(tmp_path / "red_cube_e2e.jpg")
    cv2.imwrite(path, img)
    return path


def _rotx(deg: float) -> list[list[float]]:
    """3×3 rotation matrix around X axis by *deg* degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [
        [1.0, 0.0, 0.0],
        [0.0, c, -s],
        [0.0, s, c],
    ]


def test_e2e_grasp_pose_within_5mm(tmp_path):
    """Full pipeline: bootstrap → register → detect → assert grasp xyz ~ (0,0,0)."""
    image_path = _build_red_cube_image(tmp_path)

    # Bootstrap intrinsics: fx=fy=500, cx=320, cy=240, no distortion.
    intrinsics_body = {
        "fx": 500.0,
        "fy": 500.0,
        "cx": 320.0,
        "cy": 240.0,
        "width": 640,
        "height": 480,
        "dist_coeffs": [0.0, 0.0, 0.0, 0.0, 0.0],
    }

    # Bootstrap extrinsics: camera at (0, 0, 0.6) m looking straight down.
    # "Looking straight down" = camera +z axis points toward −world-z.
    # R = rotx(180°): maps camera z → world −z (i.e. looking down).
    extrinsics_body = {
        "R_cam_in_world": _rotx(180.0),
        "t_cam_in_world": [0.0, 0.0, 0.6],
        "reference_frame": "world",
        "mount": "eye_to_hand",
    }

    with TestClient(app) as client:
        # 1. Register FakeCamera.
        reg_resp = client.post(
            "/api/vision/cameras",
            json={
                "kind": "fake",
                "source": image_path,
                "name": "e2e_cam",
                "fake_image_paths": [image_path],
                "fps": 15.0,
            },
        )
        assert reg_resp.status_code == 200, reg_resp.text

        # 2. Bootstrap intrinsics.
        intr_resp = client.post("/api/vision/cameras/e2e_cam/intrinsics", json=intrinsics_body)
        assert intr_resp.status_code == 200, intr_resp.text

        # 3. Bootstrap extrinsics.
        extr_resp = client.post("/api/vision/cameras/e2e_cam/extrinsics", json=extrinsics_body)
        assert extr_resp.status_code == 200, extr_resp.text

        # 4. Register ColorDetector.
        det_resp = client.post(
            "/api/vision/detectors",
            json={"kind": "color", "name": "e2e_det", "config": {}},
        )
        assert det_resp.status_code == 200, det_resp.text

        # 5. Allow capture thread to grab a frame.
        time.sleep(0.3)

        # 6. One-shot detect with grasp.
        run_resp = client.post(
            "/api/vision/detectors/e2e_det/run",
            json={"camera": "e2e_cam", "return_grasp": True, "plane_z_m": 0.0},
        )
        assert run_resp.status_code == 200, run_resp.text
        body = run_resp.json()

        assert len(body["detections"]) >= 1, "Expected at least one red-cube detection"
        assert len(body["grasps"]) >= 1, "Expected at least one grasp pose"

        grasp = body["grasps"][0]
        xyz = grasp["xyz_m"]
        x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])

        dist = math.sqrt(x**2 + y**2 + z**2)
        assert dist < 0.005, (
            f"Grasp xyz ({x:.6f}, {y:.6f}, {z:.6f}) is {dist*1000:.2f} mm from origin "
            f"(limit 5 mm). Check intrinsics / extrinsics / detector."
        )
