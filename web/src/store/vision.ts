/**
 * Vision state store.
 *
 * Holds camera registry, detector registry, intrinsics/extrinsics cache,
 * last detections per camera, grasp poses per camera, selection state,
 * and the set of active live loops.
 *
 * Written by `useVisionDetections` (WS hook) and REST-call callbacks in
 * VisionPanel components. Never pollutes `useTelemetryStore`.
 */

import { create } from "zustand";
import type {
  CameraStatus,
  DetectorStatus,
  CameraIntrinsicsModel,
  CameraExtrinsicsModel,
  DetectionModel,
  GraspPoseModel,
  LiveDetectionFrame,
} from "@/api/types";

interface LiveLoop {
  detector: string;
  camera: string;
}

interface VisionState {
  cameras: Record<string, CameraStatus>;
  detectors: Record<string, DetectorStatus>;
  intrinsics: Record<string, CameraIntrinsicsModel>;
  extrinsics: Record<string, CameraExtrinsicsModel>;
  lastDetections: Record<string, DetectionModel[]>;
  lastGrasps: Record<string, GraspPoseModel[]>;
  selectedCamera: string | null;
  selectedDetector: string | null;
  selectedDetection: number | null;
  liveLoops: LiveLoop[];

  setCameras: (cameras: CameraStatus[]) => void;
  setDetectors: (detectors: DetectorStatus[]) => void;
  setIntrinsics: (cameraName: string, model: CameraIntrinsicsModel) => void;
  setExtrinsics: (cameraName: string, model: CameraExtrinsicsModel) => void;
  applyLiveFrame: (frame: LiveDetectionFrame) => void;
  setSelectedCamera: (name: string | null) => void;
  setSelectedDetector: (name: string | null) => void;
  setSelectedDetection: (index: number | null) => void;
  addLiveLoop: (loop: LiveLoop) => void;
  removeLiveLoop: (detector: string, camera: string) => void;
}

export const useVisionStore = create<VisionState>()((set) => ({
  cameras: {},
  detectors: {},
  intrinsics: {},
  extrinsics: {},
  lastDetections: {},
  lastGrasps: {},
  selectedCamera: null,
  selectedDetector: null,
  selectedDetection: null,
  liveLoops: [],

  setCameras: (cameras) =>
    set({
      cameras: Object.fromEntries(cameras.map((c) => [c.name, c])),
    }),

  setDetectors: (detectors) =>
    set({
      detectors: Object.fromEntries(detectors.map((d) => [d.name, d])),
    }),

  setIntrinsics: (cameraName, model) =>
    set((state) => ({
      intrinsics: { ...state.intrinsics, [cameraName]: model },
    })),

  setExtrinsics: (cameraName, model) =>
    set((state) => ({
      extrinsics: { ...state.extrinsics, [cameraName]: model },
    })),

  applyLiveFrame: (frame) =>
    set((state) => ({
      lastDetections: { ...state.lastDetections, [frame.camera]: frame.detections },
      lastGrasps: { ...state.lastGrasps, [frame.camera]: frame.grasps },
    })),

  setSelectedCamera: (name) => set({ selectedCamera: name, selectedDetection: null }),

  setSelectedDetector: (name) => set({ selectedDetector: name }),

  setSelectedDetection: (index) => set({ selectedDetection: index }),

  addLiveLoop: (loop) =>
    set((state) => ({
      liveLoops: [...state.liveLoops.filter(
        (l) => !(l.detector === loop.detector && l.camera === loop.camera),
      ), loop],
    })),

  removeLiveLoop: (detector, camera) =>
    set((state) => ({
      liveLoops: state.liveLoops.filter(
        (l) => !(l.detector === detector && l.camera === camera),
      ),
    })),
}));
