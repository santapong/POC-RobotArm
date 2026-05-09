"""GUI smoke test: open the PyBullet window briefly, drive the arm,
capture a frame to ``artifacts/smoke_<timestamp>.png``.

Skipped unless ``RUN_GUI_TESTS=1`` is set, because most CI runners are
headless. On a real desktop:

    RUN_GUI_TESTS=1 pytest tests/test_gui_smoke.py -v
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("pybullet")

if os.environ.get("RUN_GUI_TESTS") != "1":
    pytest.skip("Set RUN_GUI_TESTS=1 to run GUI smoke tests.", allow_module_level=True)

import pybullet as p  # noqa: E402

from src.simulation.engine import RobotArmSim  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"


def _capture_frame(sim: RobotArmSim, path: Path) -> tuple[int, int]:
    width, height = 640, 480
    view = p.computeViewMatrix(
        cameraEyePosition=[1.4, 1.0, 0.9],
        cameraTargetPosition=[0.0, 0.0, 0.4],
        cameraUpVector=[0.0, 0.0, 1.0],
    )
    proj = p.computeProjectionMatrixFOV(
        fov=60, aspect=width / height, nearVal=0.1, farVal=10.0
    )
    img = p.getCameraImage(
        width, height, viewMatrix=view, projectionMatrix=proj,
        renderer=p.ER_BULLET_HARDWARE_OPENGL,
        physicsClientId=sim.client,
    )
    rgba = img[2]  # H x W x 4 numpy array (or list of bytes on some builds)
    try:
        import numpy as np
        from PIL import Image

        arr = np.array(rgba, dtype=np.uint8).reshape(height, width, 4)
        Image.fromarray(arr).save(path)
    except ImportError:
        # Fall back: write a raw PPM so the test produces evidence even if
        # Pillow isn't installed.
        with open(path.with_suffix(".ppm"), "wb") as fp:
            fp.write(f"P6\n{width} {height}\n255\n".encode())
            fp.write(bytes(rgba))
    return width, height


@pytest.mark.gui
def test_gui_smoke_captures_frame_with_robot():
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    sim = RobotArmSim(robot_name="panda", use_gui=True)
    try:
        target = [0.4, 0.0, 0.5]
        sol = sim.solve_ik(target)
        sim.reset_joint_angles(sol)
        sim.add_target_marker(target)
        # Let the renderer paint a frame.
        for _ in range(60):
            sim.step()
            time.sleep(1.0 / 240.0)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = ARTIFACTS_DIR / f"smoke_{ts}.png"
        w, h = _capture_frame(sim, out)
        produced = out if out.exists() else out.with_suffix(".ppm")
        assert produced.exists(), f"no smoke artifact at {produced}"
        assert produced.stat().st_size > 1024, "smoke artifact looks empty"
        print(f"\nSmoke artifact: {produced} ({w}x{h})")
    finally:
        sim.disconnect()
