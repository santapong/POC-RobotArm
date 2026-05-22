"""VisionRuntime — per-session camera capture + detection service.

One ``VisionRuntime`` is created lazily when the first camera is registered via
``POST /api/vision/cameras``. It owns:

* One OS thread per camera; only that thread writes to the camera's
  ``_LatestFrame`` slot.
* A ``ThreadPoolExecutor(max_workers=2)`` for detection work — detection
  never runs on the event loop directly.
* Asyncio live-detection tasks (one per ``(detector, camera)`` pair) that loop
  at the requested ``rate_hz``.
* A ``set[asyncio.Queue]`` for WebSocket subscribers; frames are published
  via ``put_nowait`` (dropped when the queue is full).

Notes
-----
- All ``cv2.*`` calls happen on capture threads, the detector executor, or
  via ``asyncio.to_thread`` — never directly on the event loop.
- ``stop()`` cancels live tasks, signals capture threads, and shuts down the
  executor.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from server.models.vision import (
    DetectionModel,
    GraspPoseModel,
    LiveDetectionFrame,
    RunDetectionResponse,
)
from src.vision.capture import Camera
from src.vision.detection import Detector
from src.vision.grasp import pixel_to_world
from src.vision.types import CameraExtrinsics, CameraIntrinsics

# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass
class _LatestFrame:
    """Slot holding the most-recent frame from a capture thread."""

    frame: Optional[np.ndarray] = None
    monotonic_s: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class _CameraSlot:
    """Bookkeeping for one registered camera."""

    camera: Camera
    latest: _LatestFrame
    capture_thread: threading.Thread
    stop_event: threading.Event
    kind: str  # "real" or "fake"


@dataclass
class _LiveDetectorTask:
    """Wrapper around an asyncio.Task for a live detection loop."""

    task: asyncio.Task
    rate_hz: float


# ---------------------------------------------------------------------------
# VisionRuntime
# ---------------------------------------------------------------------------


class VisionRuntime:
    """Session-scoped vision pipeline: cameras, detectors, calibration.

    Instantiated lazily on the first camera registration; torn down via
    ``await stop()`` in the server lifespan shutdown handler.
    """

    def __init__(self) -> None:
        self.cameras: dict[str, _CameraSlot] = {}
        self.detectors: dict[str, Detector] = {}
        # Stores kind strings for status reporting
        self._detector_kinds: dict[str, str] = {}
        self._detector_configs: dict[str, dict] = {}
        self.intrinsics: dict[str, CameraIntrinsics] = {}
        self.extrinsics: dict[str, CameraExtrinsics] = {}
        # Key: (detector_name, camera_name)
        self.live_tasks: dict[tuple[str, str], _LiveDetectorTask] = {}
        # Latest detections per (detector, camera) for MJPEG overlay
        self._last_detections: dict[tuple[str, str], list] = {}
        self.subscribers: set[asyncio.Queue] = set()
        self.detector_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=2)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Camera management
    # ------------------------------------------------------------------

    def add_camera(self, camera: Camera, kind: str) -> None:
        """Register a camera and start its capture thread.

        The capture thread continuously calls ``camera.read()`` and stores
        the result in a ``_LatestFrame`` slot.  The thread exits when its
        ``stop_event`` is set.
        """
        if camera.name in self.cameras:
            raise ValueError(f"Camera {camera.name!r} is already registered")

        latest = _LatestFrame()
        stop_event = threading.Event()

        def _capture_loop() -> None:
            while not stop_event.is_set():
                try:
                    frame = camera.read()
                    ts = time.monotonic()
                    with latest.lock:
                        latest.frame = frame
                        latest.monotonic_s = ts
                except StopIteration:
                    # FakeCamera with loop=False exhausted.
                    break
                except Exception:  # noqa: BLE001
                    # Don't crash the thread on a transient read error.
                    time.sleep(0.05)

        t = threading.Thread(target=_capture_loop, daemon=True, name=f"capture_{camera.name}")
        t.start()

        self.cameras[camera.name] = _CameraSlot(
            camera=camera,
            latest=latest,
            capture_thread=t,
            stop_event=stop_event,
            kind=kind,
        )

    def remove_camera(self, name: str) -> None:
        """Stop the capture thread and release the camera."""
        slot = self.cameras.pop(name, None)
        if slot is None:
            raise KeyError(name)
        slot.stop_event.set()
        slot.capture_thread.join(timeout=2.0)
        try:
            slot.camera.close()
        except Exception:  # noqa: BLE001
            pass

    def get_latest_frame(self, camera_name: str) -> tuple[np.ndarray, float]:
        """Return a copy of the most-recent frame and its monotonic timestamp.

        Raises
        ------
        KeyError
            If ``camera_name`` is not registered.
        RuntimeError
            If no frame has been captured yet.
        """
        slot = self.cameras.get(camera_name)
        if slot is None:
            raise KeyError(camera_name)
        with slot.latest.lock:
            if slot.latest.frame is None:
                raise RuntimeError(f"Camera {camera_name!r}: no frame available yet")
            return slot.latest.frame.copy(), slot.latest.monotonic_s

    # ------------------------------------------------------------------
    # Detector management
    # ------------------------------------------------------------------

    def add_detector(self, detector: Detector, kind: str, config: dict) -> None:
        """Register a detector."""
        if detector.name in self.detectors:
            raise ValueError(f"Detector {detector.name!r} is already registered")
        self.detectors[detector.name] = detector
        self._detector_kinds[detector.name] = kind
        self._detector_configs[detector.name] = config

    def remove_detector(self, name: str) -> None:
        """Remove a detector, stopping any live loops that use it."""
        if name not in self.detectors:
            raise KeyError(name)
        # Cancel live loops.
        keys_to_cancel = [k for k in self.live_tasks if k[0] == name]
        for key in keys_to_cancel:
            self._cancel_live_task(key)
        detector = self.detectors.pop(name)
        self._detector_kinds.pop(name, None)
        self._detector_configs.pop(name, None)
        try:
            detector.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    async def run_detection_once(
        self,
        detector_name: str,
        camera_name: str,
        return_grasp: bool = False,
        plane_z_m: float = 0.0,
    ) -> RunDetectionResponse:
        """Run a single detection pass and optionally compute grasp poses.

        Parameters
        ----------
        detector_name:
            Registered detector name.
        camera_name:
            Registered camera name.
        return_grasp:
            When ``True``, attempts ``pixel_to_world`` for each detection.
            Silently skips if intrinsics/extrinsics are missing.
        plane_z_m:
            Z-height of the ground plane for back-projection.
        """
        frame, ts = self.get_latest_frame(camera_name)
        detector = self.detectors[detector_name]

        loop = asyncio.get_running_loop()
        detections = await loop.run_in_executor(
            self.detector_executor, detector.detect, frame
        )

        # Store for MJPEG overlay.
        self._last_detections[(detector_name, camera_name)] = detections

        grasps: list[GraspPoseModel] = []
        if return_grasp:
            intrinsics = self.intrinsics.get(camera_name)
            extrinsics = self.extrinsics.get(camera_name)
            if intrinsics is not None and extrinsics is not None:
                for det in detections:
                    try:
                        gp = pixel_to_world(det, intrinsics, extrinsics, plane_z_m)
                        grasps.append(GraspPoseModel.from_domain(gp))
                    except Exception:  # noqa: BLE001
                        pass

        return RunDetectionResponse(
            camera=camera_name,
            detector=detector_name,
            detections=[DetectionModel.from_domain(d) for d in detections],
            grasps=grasps,
            monotonic_s=ts,
        )

    # ------------------------------------------------------------------
    # Live detection loops
    # ------------------------------------------------------------------

    def start_live(self, detector_name: str, camera_name: str, rate_hz: float) -> None:
        """Schedule an asyncio task for continuous detection at ``rate_hz``."""
        key = (detector_name, camera_name)
        if key in self.live_tasks:
            return  # already running

        loop = asyncio.get_running_loop()
        task = loop.create_task(
            self._live_loop(detector_name, camera_name, rate_hz),
            name=f"live_{detector_name}_{camera_name}",
        )
        self.live_tasks[key] = _LiveDetectorTask(task=task, rate_hz=rate_hz)

    def stop_live(self, detector_name: str, camera_name: str) -> None:
        """Cancel the live detection loop for this (detector, camera) pair."""
        key = (detector_name, camera_name)
        self._cancel_live_task(key)

    def _cancel_live_task(self, key: tuple[str, str]) -> None:
        task_wrapper = self.live_tasks.pop(key, None)
        if task_wrapper is not None and not task_wrapper.task.done():
            task_wrapper.task.cancel()

    async def _live_loop(
        self, detector_name: str, camera_name: str, rate_hz: float
    ) -> None:
        """Continuous detection loop; publishes to subscriber queues."""
        interval = 1.0 / max(rate_hz, 0.1)
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(interval)
            try:
                slot = self.cameras.get(camera_name)
                detector = self.detectors.get(detector_name)
                if slot is None or detector is None:
                    continue

                with slot.latest.lock:
                    if slot.latest.frame is None:
                        continue
                    frame_copy = slot.latest.frame.copy()
                    ts = slot.latest.monotonic_s

                detections = await loop.run_in_executor(
                    self.detector_executor, detector.detect, frame_copy
                )
                self._last_detections[(detector_name, camera_name)] = detections

                frame_msg = LiveDetectionFrame(
                    camera=camera_name,
                    detector=detector_name,
                    detections=[DetectionModel.from_domain(d) for d in detections],
                    grasps=[],
                    monotonic_s=ts,
                )
                payload = frame_msg.model_dump()
                for q in list(self.subscribers):
                    try:
                        q.put_nowait(payload)
                    except asyncio.QueueFull:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Subscriber pub/sub
    # ------------------------------------------------------------------

    def subscribe(self, queue: asyncio.Queue) -> None:
        """Add a queue to receive ``LiveDetectionFrame`` payloads."""
        self.subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a queue from detection broadcasts."""
        self.subscribers.discard(queue)

    # ------------------------------------------------------------------
    # Last-detections (for MJPEG overlay)
    # ------------------------------------------------------------------

    def last_detections(self, detector_name: str, camera_name: str) -> list:
        """Return the most-recent detection list for this (detector, camera) pair."""
        return self._last_detections.get((detector_name, camera_name), [])

    # ------------------------------------------------------------------
    # Camera / detector status helpers
    # ------------------------------------------------------------------

    def camera_status(self) -> list[dict]:
        """Return a list of camera status dicts."""
        results = []
        live_cam_to_detectors: dict[str, str] = {}
        for (det_name, cam_name) in self.live_tasks:
            live_cam_to_detectors[cam_name] = det_name
        for name, slot in self.cameras.items():
            results.append(
                {
                    "name": name,
                    "kind": slot.kind,
                    "width": slot.camera.width,
                    "height": slot.camera.height,
                    "has_intrinsics": name in self.intrinsics,
                    "has_extrinsics": name in self.extrinsics,
                    "live_detector": live_cam_to_detectors.get(name),
                }
            )
        return results

    def detector_status(self) -> list[dict]:
        """Return a list of detector status dicts."""
        cam_to_det: dict[str, list[str]] = {}
        for (det_name, cam_name) in self.live_tasks:
            cam_to_det.setdefault(det_name, []).append(cam_name)
        results = []
        for name in self.detectors:
            results.append(
                {
                    "name": name,
                    "kind": self._detector_kinds.get(name, "unknown"),
                    "config": self._detector_configs.get(name, {}),
                    "live_cameras": cam_to_det.get(name, []),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        """Cancel all live tasks, stop capture threads, shut down executor."""
        # Cancel live tasks.
        for key in list(self.live_tasks):
            self._cancel_live_task(key)
        # Give tasks a moment to finish.
        await asyncio.sleep(0.05)

        # Stop capture threads.
        for name in list(self.cameras):
            try:
                self.remove_camera(name)
            except Exception:  # noqa: BLE001
                pass

        # Close detectors.
        for det in list(self.detectors.values()):
            try:
                det.close()
            except Exception:  # noqa: BLE001
                pass

        self.detector_executor.shutdown(wait=False)


__all__ = ["VisionRuntime"]
