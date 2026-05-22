"""Vision pipeline router.

Endpoints
---------
- ``POST /api/vision/cameras`` — register a camera.
- ``GET  /api/vision/cameras`` — list cameras.
- ``DELETE /api/vision/cameras/{name}`` — remove a camera.
- ``GET  /api/vision/cameras/{name}/snapshot`` — single JPEG frame.
- ``GET  /api/vision/cameras/{name}/stream`` — MJPEG stream.
- ``POST /api/vision/cameras/{name}/calibrate/intrinsic`` — batch intrinsic cal.
- ``POST /api/vision/cameras/{name}/calibrate/hand-eye`` — hand-eye cal.
- ``POST /api/vision/cameras/{name}/intrinsics`` — bootstrap intrinsics setter.
- ``POST /api/vision/cameras/{name}/extrinsics`` — bootstrap extrinsics setter.
- ``POST /api/vision/cameras/{name}/charuco_pose`` — live charuco pose estimate.
- ``POST /api/vision/detectors`` — register a detector.
- ``GET  /api/vision/detectors`` — list detectors.
- ``DELETE /api/vision/detectors/{name}`` — remove a detector.
- ``POST /api/vision/detectors/{name}/run`` — one-shot detect.
- ``POST /api/vision/detectors/{name}/start`` — start live detection loop.
- ``POST /api/vision/detectors/{name}/stop`` — stop live detection loop.
- ``POST /api/vision/grasp_preview`` — IK preview for a grasp pose.
"""

from __future__ import annotations

import asyncio

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Form, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from server.models.vision import (
    CameraExtrinsicsModel,
    CameraIntrinsicsModel,
    CameraSpec,
    CameraStatus,
    CharucoPoseRequest,
    DetectorSpec,
    DetectorStatus,
    GraspPreviewRequest,
    GraspPreviewResponse,
    HandEyeRequest,
    RunDetectionRequest,
    RunDetectionResponse,
)
from server.services.errors import http_error
from server.services.session import Session, get_session
from server.services.vision import VisionRuntime

router = APIRouter(prefix="/api/vision")

_JPEG_QUALITY = 80


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_create_runtime(session: Session) -> VisionRuntime:
    """Lazily create the VisionRuntime on first use."""
    if session.vision_runtime is None:
        session.vision_runtime = VisionRuntime()
    return session.vision_runtime


def _require_runtime(session: Session) -> VisionRuntime:
    """Return runtime or raise 503 if not initialised."""
    if session.vision_runtime is None:
        raise http_error(503, "VISION_CAMERA_NOT_READY", "No vision runtime — register a camera first.")
    return session.vision_runtime


async def _encode_jpeg(frame: np.ndarray) -> bytes:
    """Encode a BGR frame to JPEG bytes in a thread."""
    def _enc(f: np.ndarray) -> bytes:
        ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
        if not ok:
            raise RuntimeError("cv2.imencode failed")
        return bytes(buf)

    return await asyncio.to_thread(_enc, frame)


async def _frame_with_overlay(
    frame: np.ndarray,
    detections: list,
) -> np.ndarray:
    """Draw bounding boxes and labels on a frame copy (runs in thread)."""
    def _draw(f: np.ndarray, dets: list) -> np.ndarray:
        out = f.copy()
        for det in dets:
            x1, y1, x2, y2 = (int(v) for v in det.bbox_xyxy)
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{det.class_name} {det.confidence:.2f}"
            cv2.putText(out, label, (x1, max(y1 - 6, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        return out

    return await asyncio.to_thread(_draw, frame, detections)


# ---------------------------------------------------------------------------
# Camera endpoints
# ---------------------------------------------------------------------------


@router.post("/cameras", response_model=CameraStatus)
async def register_camera(
    body: CameraSpec,
    session: Session = Depends(get_session),
) -> CameraStatus:
    """Register a camera and start its capture thread."""
    runtime = _get_or_create_runtime(session)

    try:
        if body.kind == "fake":
            from src.vision.capture import FakeCamera

            camera = FakeCamera(
                name=body.name,
                image_paths=body.fake_image_paths,
                width=body.width,
                height=body.height,
                fps=body.fps,
            )
        else:
            from src.vision.capture import RealCamera

            camera = RealCamera(
                name=body.name,
                source=int(body.source),
                width=body.width,
                height=body.height,
            )
    except (ImportError, ValueError) as exc:
        raise http_error(501, "VISION_DEPENDENCY_MISSING", str(exc)) from exc
    except RuntimeError as exc:
        raise http_error(503, "VISION_CAMERA_NOT_READY", str(exc)) from exc

    try:
        runtime.add_camera(camera, body.kind)
    except ValueError as exc:
        raise http_error(409, "VISION_CAMERA_UNKNOWN", str(exc)) from exc

    await session.push_event({"type": "camera_registered", "payload": {"name": body.name}})

    return CameraStatus(
        name=body.name,
        kind=body.kind,
        width=body.width,
        height=body.height,
        has_intrinsics=body.name in runtime.intrinsics,
        has_extrinsics=body.name in runtime.extrinsics,
        live_detector=None,
    )


@router.get("/cameras", response_model=list[CameraStatus])
async def list_cameras(session: Session = Depends(get_session)) -> list[CameraStatus]:
    """Return all registered cameras."""
    if session.vision_runtime is None:
        return []
    return [CameraStatus(**s) for s in session.vision_runtime.camera_status()]


@router.delete("/cameras/{name}")
async def remove_camera(
    name: str,
    session: Session = Depends(get_session),
) -> dict:
    """Stop a camera's capture thread and deregister it."""
    # If no runtime exists at all, the camera is definitionally unknown.
    if session.vision_runtime is None or name not in session.vision_runtime.cameras:
        raise http_error(404, "VISION_CAMERA_UNKNOWN", f"Camera {name!r} not found.")
    try:
        session.vision_runtime.remove_camera(name)
    except KeyError:
        raise http_error(404, "VISION_CAMERA_UNKNOWN", f"Camera {name!r} not found.")
    return {"removed": name}


# ---------------------------------------------------------------------------
# Snapshot + MJPEG stream
# ---------------------------------------------------------------------------


@router.get("/cameras/{name}/snapshot")
async def snapshot(
    name: str,
    overlay: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> Response:
    """Return a single JPEG frame from the camera."""
    runtime = _require_runtime(session)
    try:
        frame, _ = runtime.get_latest_frame(name)
    except KeyError:
        raise http_error(404, "VISION_CAMERA_UNKNOWN", f"Camera {name!r} not found.")
    except RuntimeError as exc:
        raise http_error(503, "VISION_CAMERA_NOT_READY", str(exc)) from exc

    if overlay:
        # Use the first active detector's cached detections.
        all_dets: list = []
        for (det_name, cam_name), dets in runtime._last_detections.items():
            if cam_name == name:
                all_dets = dets
                break
        frame = await _frame_with_overlay(frame, all_dets)

    jpg = await _encode_jpeg(frame)
    return Response(content=jpg, media_type="image/jpeg")


@router.get("/cameras/{name}/stream")
async def mjpeg_stream(
    name: str,
    overlay: bool = Query(default=False),
    fps: int = Query(default=15, ge=1, le=30),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Return an MJPEG stream from the camera at up to ``fps`` frames/second."""
    runtime = _require_runtime(session)
    if name not in runtime.cameras:
        raise http_error(404, "VISION_CAMERA_UNKNOWN", f"Camera {name!r} not found.")

    async def _generator():
        interval = 1.0 / fps
        while True:
            try:
                frame, _ = runtime.get_latest_frame(name)
            except (KeyError, RuntimeError):
                await asyncio.sleep(interval)
                continue

            if overlay:
                all_dets: list = []
                for (det_name, cam_name), dets in runtime._last_detections.items():
                    if cam_name == name:
                        all_dets = dets
                        break
                frame = await _frame_with_overlay(frame, all_dets)

            try:
                jpg = await _encode_jpeg(frame)
            except Exception:  # noqa: BLE001
                await asyncio.sleep(interval)
                continue

            header = (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
            )
            yield header + jpg + b"\r\n"
            await asyncio.sleep(interval)

    return StreamingResponse(
        _generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# Calibration endpoints
# ---------------------------------------------------------------------------


@router.post("/cameras/{name}/calibrate/intrinsic", response_model=CameraIntrinsicsModel)
async def calibrate_intrinsic(
    name: str,
    files: list[UploadFile],
    squares_x: int = Form(default=5),
    squares_y: int = Form(default=7),
    square_length_m: float = Form(default=0.04),
    marker_length_m: float = Form(default=0.03),
    session: Session = Depends(get_session),
) -> CameraIntrinsicsModel:
    """Estimate camera intrinsics from >= 5 ChArUco calibration images."""
    runtime = _get_or_create_runtime(session)

    if len(files) < 5:
        raise http_error(
            422,
            "VISION_CALIBRATION_FAILED",
            f"At least 5 images required for intrinsic calibration, got {len(files)}.",
        )

    frames: list[np.ndarray] = []
    for f in files:
        raw = await f.read()

        def _decode(data: bytes) -> np.ndarray:
            arr = np.frombuffer(data, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("cv2.imdecode returned None")
            return img

        try:
            img = await asyncio.to_thread(_decode, raw)
        except ValueError as exc:
            raise http_error(422, "VALIDATION_ERROR", f"Could not decode image: {exc}") from exc
        frames.append(img)

    if not frames:
        raise http_error(422, "VISION_CALIBRATION_FAILED", "No valid images provided.")

    h, w = frames[0].shape[:2]
    image_size = (w, h)

    from src.vision.calibration import CharucoBoardSpec
    from src.vision.calibration import calibrate_intrinsic as _calibrate

    try:
        board_spec = CharucoBoardSpec(
            squares_x=squares_x,
            squares_y=squares_y,
            square_length_m=square_length_m,
            marker_length_m=marker_length_m,
        )
        board = board_spec.make_board()
    except ValueError as exc:
        raise http_error(422, "VALIDATION_ERROR", str(exc)) from exc

    try:
        intrinsics = await asyncio.to_thread(_calibrate, frames, board, image_size)
    except ValueError as exc:
        raise http_error(422, "VISION_CALIBRATION_FAILED", str(exc)) from exc

    runtime.intrinsics[name] = intrinsics
    return CameraIntrinsicsModel.from_domain(intrinsics)


@router.post("/cameras/{name}/calibrate/hand-eye", response_model=CameraExtrinsicsModel)
async def calibrate_hand_eye(
    name: str,
    body: HandEyeRequest,
    session: Session = Depends(get_session),
) -> CameraExtrinsicsModel:
    """Solve hand-eye calibration from pose-pair data."""
    runtime = _get_or_create_runtime(session)

    from src.vision.hand_eye import solve_hand_eye

    R_g2b = [np.array(pp.R_gripper2base, dtype=np.float64) for pp in body.pose_pairs]
    t_g2b = [np.array(pp.t_gripper2base, dtype=np.float64) for pp in body.pose_pairs]
    R_t2c = [np.array(pp.R_target2cam, dtype=np.float64) for pp in body.pose_pairs]
    t_t2c = [np.array(pp.t_target2cam, dtype=np.float64) for pp in body.pose_pairs]

    try:
        extrinsics = await asyncio.to_thread(
            solve_hand_eye, R_g2b, t_g2b, R_t2c, t_t2c,
            body.method, body.mount, body.reference_frame,
        )
    except (ValueError, KeyError) as exc:
        raise http_error(422, "VISION_CALIBRATION_FAILED", str(exc)) from exc

    runtime.extrinsics[name] = extrinsics
    return CameraExtrinsicsModel.from_domain(extrinsics)


# ---------------------------------------------------------------------------
# Bootstrap setters
# ---------------------------------------------------------------------------


@router.post("/cameras/{name}/intrinsics", response_model=CameraIntrinsicsModel)
async def set_intrinsics(
    name: str,
    body: CameraIntrinsicsModel,
    session: Session = Depends(get_session),
) -> CameraIntrinsicsModel:
    """Bootstrap: set intrinsics directly, bypassing calibration."""
    runtime = _get_or_create_runtime(session)
    try:
        runtime.intrinsics[name] = body.to_domain()
    except ValueError as exc:
        raise http_error(422, "VALIDATION_ERROR", str(exc)) from exc
    return body


@router.post("/cameras/{name}/extrinsics", response_model=CameraExtrinsicsModel)
async def set_extrinsics(
    name: str,
    body: CameraExtrinsicsModel,
    session: Session = Depends(get_session),
) -> CameraExtrinsicsModel:
    """Bootstrap: set extrinsics directly, bypassing calibration."""
    runtime = _get_or_create_runtime(session)
    try:
        runtime.extrinsics[name] = body.to_domain()
    except ValueError as exc:
        raise http_error(422, "VALIDATION_ERROR", str(exc)) from exc
    return body


# ---------------------------------------------------------------------------
# Charuco pose
# ---------------------------------------------------------------------------


@router.post("/cameras/{name}/charuco_pose")
async def charuco_pose(
    name: str,
    body: CharucoPoseRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Estimate charuco board pose from latest camera frame."""
    runtime = _require_runtime(session)

    if name not in runtime.intrinsics:
        raise http_error(409, "VISION_NO_INTRINSICS", f"No intrinsics stored for camera {name!r}.")

    try:
        frame, _ = runtime.get_latest_frame(name)
    except KeyError:
        raise http_error(404, "VISION_CAMERA_UNKNOWN", f"Camera {name!r} not found.")
    except RuntimeError as exc:
        raise http_error(503, "VISION_CAMERA_NOT_READY", str(exc)) from exc

    intrinsics = runtime.intrinsics[name]

    from src.vision.calibration import CharucoBoardSpec, detect_charuco

    try:
        board_spec = CharucoBoardSpec(
            squares_x=body.squares_x,
            squares_y=body.squares_y,
            square_length_m=body.square_length_m,
            marker_length_m=body.marker_length_m,
        )
        board = board_spec.make_board()
    except ValueError as exc:
        raise http_error(422, "VALIDATION_ERROR", str(exc)) from exc

    def _detect_and_estimate(f: np.ndarray) -> dict:
        corners, ids = detect_charuco(f, board)
        if corners is None or ids is None:
            raise ValueError("ChArUco detection failed — no corners found in frame")

        K_np = intrinsics.K_np()
        dist_np = np.array(intrinsics.dist_coeffs, dtype=np.float64)

        ok, rvec, tvec = cv2.aruco.estimatePoseCharucoBoard(
            corners, ids, board, K_np, dist_np, None, None
        )
        if not ok:
            raise ValueError("estimatePoseCharucoBoard returned False — pose estimation failed")

        R_mat, _ = cv2.Rodrigues(rvec)
        return {
            "R_target2cam": R_mat.tolist(),
            "t_target2cam": tvec.flatten().tolist(),
        }

    try:
        result = await asyncio.to_thread(_detect_and_estimate, frame)
    except ValueError as exc:
        raise http_error(422, "VISION_CALIBRATION_FAILED", str(exc)) from exc

    return result


# ---------------------------------------------------------------------------
# Detector endpoints
# ---------------------------------------------------------------------------


@router.post("/detectors", response_model=DetectorStatus)
async def register_detector(
    body: DetectorSpec,
    session: Session = Depends(get_session),
) -> DetectorStatus:
    """Register a detector."""
    runtime = _get_or_create_runtime(session)

    try:
        if body.kind == "color":
            from src.vision.detection import ColorDetector

            kwargs: dict = {k: v for k, v in body.config.items()}
            detector = ColorDetector(name=body.name, **kwargs)
        elif body.kind == "yolo":
            from src.vision.detection import YOLODetector

            kwargs = {k: v for k, v in body.config.items()}
            try:
                detector = YOLODetector(name=body.name, **kwargs)
            except ImportError as exc:
                raise http_error(
                    501, "VISION_DEPENDENCY_MISSING",
                    f"ultralytics not installed — install [vision-ml] extra: {exc}"
                ) from exc
        else:
            raise http_error(422, "VALIDATION_ERROR", f"Unknown detector kind {body.kind!r}.")
    except ValueError as exc:
        raise http_error(422, "VALIDATION_ERROR", str(exc)) from exc

    try:
        runtime.add_detector(detector, body.kind, body.config)
    except ValueError as exc:
        raise http_error(409, "VISION_DETECTOR_UNKNOWN", str(exc)) from exc

    return DetectorStatus(name=body.name, kind=body.kind, config=body.config, live_cameras=[])


@router.get("/detectors", response_model=list[DetectorStatus])
async def list_detectors(session: Session = Depends(get_session)) -> list[DetectorStatus]:
    """Return all registered detectors."""
    if session.vision_runtime is None:
        return []
    return [DetectorStatus(**s) for s in session.vision_runtime.detector_status()]


@router.delete("/detectors/{name}")
async def remove_detector(
    name: str,
    session: Session = Depends(get_session),
) -> dict:
    """Remove a detector, stopping any live loops using it."""
    if session.vision_runtime is None or name not in session.vision_runtime.detectors:
        raise http_error(404, "VISION_DETECTOR_UNKNOWN", f"Detector {name!r} not found.")
    try:
        session.vision_runtime.remove_detector(name)
    except KeyError:
        raise http_error(404, "VISION_DETECTOR_UNKNOWN", f"Detector {name!r} not found.")
    return {"removed": name}


@router.post("/detectors/{name}/run", response_model=RunDetectionResponse)
async def run_detection(
    name: str,
    body: RunDetectionRequest,
    session: Session = Depends(get_session),
) -> RunDetectionResponse:
    """One-shot detection run."""
    runtime = _require_runtime(session)
    if name not in runtime.detectors:
        raise http_error(404, "VISION_DETECTOR_UNKNOWN", f"Detector {name!r} not found.")
    if body.camera not in runtime.cameras:
        raise http_error(404, "VISION_CAMERA_UNKNOWN", f"Camera {body.camera!r} not found.")

    try:
        return await runtime.run_detection_once(
            name, body.camera, body.return_grasp, body.plane_z_m
        )
    except RuntimeError as exc:
        raise http_error(503, "VISION_CAMERA_NOT_READY", str(exc)) from exc


@router.post("/detectors/{name}/start")
async def start_live(
    name: str,
    body: dict,
    session: Session = Depends(get_session),
) -> dict:
    """Start a live detection loop for (detector, camera) at rate_hz."""
    runtime = _require_runtime(session)
    camera = body.get("camera", "")
    rate_hz = float(body.get("rate_hz", 5.0))

    if name not in runtime.detectors:
        raise http_error(404, "VISION_DETECTOR_UNKNOWN", f"Detector {name!r} not found.")
    if camera not in runtime.cameras:
        raise http_error(404, "VISION_CAMERA_UNKNOWN", f"Camera {camera!r} not found.")

    runtime.start_live(name, camera, rate_hz)
    return {"running": True}


@router.post("/detectors/{name}/stop")
async def stop_live(
    name: str,
    body: dict,
    session: Session = Depends(get_session),
) -> dict:
    """Stop a live detection loop."""
    runtime = _require_runtime(session)
    camera = body.get("camera", "")
    runtime.stop_live(name, camera)
    return {"running": False}


# ---------------------------------------------------------------------------
# Grasp preview (Open Question 2)
# ---------------------------------------------------------------------------


@router.post("/grasp_preview", response_model=GraspPreviewResponse)
async def grasp_preview(
    body: GraspPreviewRequest,
    session: Session = Depends(get_session),
) -> GraspPreviewResponse:
    """Compute IK for a grasp pose and optionally apply it to the simulator.

    Steps
    -----
    1. Resolve RobotEntry by ``robot_id``; 404 ``ROBOT_UNKNOWN`` if missing.
    2. Require ``session.sim_runtime``; 503 ``SIM_DISCONNECTED`` if absent.
    3. Transform pose from ``camera`` frame to ``world`` if needed.
    4. Solve IK via ``RobotArmSim.solve_ik_position`` on the bridge thread.
    5. Apply joints if ``preview_mode == "jog"``.
    """
    # Step 1 — resolve robot.
    station = session.station
    robot_entry = next((r for r in station.robots if r.name == body.robot_id), None)
    if robot_entry is None:
        raise http_error(404, "ROBOT_UNKNOWN", f"Robot {body.robot_id!r} not found in station.")

    # Step 2 — require sim runtime.
    sim_runtime = session.sim_runtime
    if sim_runtime is None:
        raise http_error(503, "SIM_DISCONNECTED", "Simulator not initialised.")

    # Step 3 — resolve pose in world frame.
    grasp = body.grasp
    if grasp.frame == "camera":
        vision = session.vision_runtime
        # Find a camera that has extrinsics.
        extrinsics = None
        if vision is not None:
            for cam_name, ext in vision.extrinsics.items():
                extrinsics = ext
                break
        if extrinsics is None:
            raise http_error(409, "VISION_NO_EXTRINSICS", "No camera extrinsics available for frame transform.")
        # Transform xyz through extrinsics R and t.
        import numpy as np

        R = np.array(extrinsics.R_cam_in_world, dtype=np.float64)
        t = np.array(extrinsics.t_cam_in_world, dtype=np.float64)
        xyz_cam = np.array(grasp.xyz_m, dtype=np.float64)
        xyz_world = R @ xyz_cam + t
        xyz_m_world = (float(xyz_world[0]), float(xyz_world[1]), float(xyz_world[2]))
    else:
        xyz_m_world = (float(grasp.xyz_m[0]), float(grasp.xyz_m[1]), float(grasp.xyz_m[2]))

    quat_wxyz = tuple(float(v) for v in grasp.quat_wxyz)

    bridge = sim_runtime.bridge

    # Step 4 — solve IK on bridge worker thread.
    _IK_RESIDUAL_THRESHOLD_M = 0.005  # 5 mm

    def _solve_ik(s) -> tuple[list[float], float]:
        # Convert wxyz → xyzw for PyBullet.
        w, x, y, z = quat_wxyz
        quat_xyzw = (x, y, z, w)
        joints = s.solve_ik(xyz_m_world, quat_xyzw)
        # Compute FK residual by reading EE position after applying the joints.
        s.reset_joint_angles(joints)
        ee_pos, _ = s.get_end_effector_pose()
        residual = float(
            sum((a - b) ** 2 for a, b in zip(ee_pos[:3], xyz_m_world)) ** 0.5
        )
        return joints, residual

    try:
        joints, residual = await asyncio.to_thread(bridge.submit, _solve_ik)
    except Exception as exc:
        return GraspPreviewResponse(
            joints_rad=[],
            reachable=False,
            ik_residual_m=9999.0,
            applied=False,
            error=str(exc),
        )

    reachable = residual <= _IK_RESIDUAL_THRESHOLD_M

    # Step 5 — apply joints if jog mode.
    applied = False
    if body.preview_mode == "jog":
        def _apply(s) -> None:
            s.reset_joint_angles(joints)

        try:
            await asyncio.to_thread(bridge.submit, _apply)
            applied = True
        except Exception:  # noqa: BLE001
            pass

    return GraspPreviewResponse(
        joints_rad=[float(j) for j in joints],
        reachable=reachable,
        ik_residual_m=residual,
        applied=applied,
        error=None,
    )


__all__ = ["router"]
