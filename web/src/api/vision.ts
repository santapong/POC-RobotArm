/**
 * REST client functions for the /api/vision/* endpoints.
 *
 * All functions mirror the FastAPI vision router exactly.
 * Multipart uploads use `requestMultipart`; JSON calls use `get`, `post`, `del`.
 */

import { get, post, del, requestMultipart } from "./client";
import type {
  CameraSpec,
  CameraStatus,
  CameraIntrinsicsModel,
  CameraExtrinsicsModel,
  DetectorSpec,
  DetectorStatus,
  RunDetectionRequest,
  RunDetectionResponse,
  HandEyeRequest,
  CharucoPoseResponse,
  GraspPreviewRequest,
  GraspPreviewResponse,
} from "./types";

// ---------------------------------------------------------------------------
// Camera management
// ---------------------------------------------------------------------------

export function listCameras(): Promise<CameraStatus[]> {
  return get<CameraStatus[]>("/vision/cameras");
}

export function addCamera(spec: CameraSpec): Promise<CameraStatus> {
  return post<CameraStatus>("/vision/cameras", spec);
}

export function removeCamera(name: string): Promise<{ removed: string }> {
  return del<{ removed: string }>(`/vision/cameras/${encodeURIComponent(name)}`);
}

// ---------------------------------------------------------------------------
// Camera frame URLs (not fetch calls — consumed as <img src={...}>)
// ---------------------------------------------------------------------------

/**
 * Returns the absolute path for a single JPEG snapshot.
 * Suitable for `<img src={snapshotUrl(...)} />` or blob fetch.
 */
export function snapshotUrl(name: string, overlay = false): string {
  return `/api/vision/cameras/${encodeURIComponent(name)}/snapshot?overlay=${overlay ? 1 : 0}`;
}

/**
 * Returns the MJPEG stream URL for use in an `<img>` tag.
 * The browser holds the connection open; the server pushes boundary frames.
 */
export function streamUrl(name: string, overlay = true, fps = 12): string {
  return `/api/vision/cameras/${encodeURIComponent(name)}/stream?overlay=${overlay ? 1 : 0}&fps=${fps}`;
}

// ---------------------------------------------------------------------------
// Calibration — intrinsic
// ---------------------------------------------------------------------------

/**
 * Uploads N>=5 JPEG frames and optional board parameters to solve for
 * camera intrinsics. The server stores the result keyed by camera name.
 */
export async function calibrateIntrinsic(
  cameraName: string,
  files: File[],
  boardParams?: {
    squares_x?: number;
    squares_y?: number;
    square_length_m?: number;
    marker_length_m?: number;
  },
): Promise<CameraIntrinsicsModel> {
  const form = new FormData();
  for (const f of files) {
    form.append("files", f);
  }
  if (boardParams) {
    if (boardParams.squares_x !== undefined) {
      form.append("squares_x", String(boardParams.squares_x));
    }
    if (boardParams.squares_y !== undefined) {
      form.append("squares_y", String(boardParams.squares_y));
    }
    if (boardParams.square_length_m !== undefined) {
      form.append("square_length_m", String(boardParams.square_length_m));
    }
    if (boardParams.marker_length_m !== undefined) {
      form.append("marker_length_m", String(boardParams.marker_length_m));
    }
  }
  return requestMultipart<CameraIntrinsicsModel>(
    `/vision/cameras/${encodeURIComponent(cameraName)}/calibrate/intrinsic`,
    form,
  );
}

// ---------------------------------------------------------------------------
// Calibration — hand-eye
// ---------------------------------------------------------------------------

export function calibrateHandEye(
  cameraName: string,
  req: HandEyeRequest,
): Promise<CameraExtrinsicsModel> {
  return post<CameraExtrinsicsModel>(
    `/vision/cameras/${encodeURIComponent(cameraName)}/calibrate/hand-eye`,
    req,
  );
}

// ---------------------------------------------------------------------------
// ChArUco pose (for hand-eye pair capture in the wizard)
// ---------------------------------------------------------------------------

export function charucoPose(
  cameraName: string,
  boardParams?: {
    squares_x?: number;
    squares_y?: number;
    square_length_m?: number;
    marker_length_m?: number;
  },
): Promise<CharucoPoseResponse> {
  return post<CharucoPoseResponse>(
    `/vision/cameras/${encodeURIComponent(cameraName)}/charuco_pose`,
    boardParams ?? {},
  );
}

// ---------------------------------------------------------------------------
// Bootstrap setters (bypass calibration — used in tests and dev)
// ---------------------------------------------------------------------------

export function setIntrinsics(
  cameraName: string,
  model: CameraIntrinsicsModel,
): Promise<CameraIntrinsicsModel> {
  return post<CameraIntrinsicsModel>(
    `/vision/cameras/${encodeURIComponent(cameraName)}/intrinsics`,
    model,
  );
}

export function setExtrinsics(
  cameraName: string,
  model: CameraExtrinsicsModel,
): Promise<CameraExtrinsicsModel> {
  return post<CameraExtrinsicsModel>(
    `/vision/cameras/${encodeURIComponent(cameraName)}/extrinsics`,
    model,
  );
}

// ---------------------------------------------------------------------------
// Detector management
// ---------------------------------------------------------------------------

export function listDetectors(): Promise<DetectorStatus[]> {
  return get<DetectorStatus[]>("/vision/detectors");
}

export function addDetector(spec: DetectorSpec): Promise<DetectorStatus> {
  return post<DetectorStatus>("/vision/detectors", spec);
}

export function removeDetector(name: string): Promise<{ removed: string }> {
  return del<{ removed: string }>(`/vision/detectors/${encodeURIComponent(name)}`);
}

// ---------------------------------------------------------------------------
// Detection — one-shot
// ---------------------------------------------------------------------------

export function runDetector(
  detectorName: string,
  req: RunDetectionRequest,
): Promise<RunDetectionResponse> {
  return post<RunDetectionResponse>(
    `/vision/detectors/${encodeURIComponent(detectorName)}/run`,
    req,
  );
}

// ---------------------------------------------------------------------------
// Detection — live loop control
// ---------------------------------------------------------------------------

export function startLive(
  detectorName: string,
  camera: string,
  rate_hz = 5,
): Promise<{ running: boolean }> {
  return post<{ running: boolean }>(
    `/vision/detectors/${encodeURIComponent(detectorName)}/start`,
    { camera, rate_hz },
  );
}

export function stopLive(
  detectorName: string,
  camera: string,
): Promise<{ running: boolean }> {
  return post<{ running: boolean }>(
    `/vision/detectors/${encodeURIComponent(detectorName)}/stop`,
    { camera },
  );
}

// ---------------------------------------------------------------------------
// Grasp preview (Phase 2 — sim IK preview, not real motion)
// ---------------------------------------------------------------------------

/**
 * Asks the server to run IK for a grasp pose and optionally apply the
 * joint solution in the simulator.
 */
export function graspPreview(req: GraspPreviewRequest): Promise<GraspPreviewResponse> {
  return post<GraspPreviewResponse>("/vision/grasp_preview", req);
}
