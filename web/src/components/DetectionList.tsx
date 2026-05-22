/**
 * Detection list panel.
 *
 * Shows per-detection rows for `useVisionStore.lastDetections[selectedCamera]`.
 * Each row displays class name, confidence, and bbox coordinates.
 * Clicking a row sets `selectedDetection` for the inspector.
 */

import { useVisionStore } from "@/store/vision";

export function DetectionList() {
  const selectedCamera = useVisionStore((s) => s.selectedCamera);
  const cameras = useVisionStore((s) => s.cameras);
  const lastDetections = useVisionStore((s) => s.lastDetections);
  const selectedDetection = useVisionStore((s) => s.selectedDetection);
  const setSelectedDetection = useVisionStore((s) => s.setSelectedDetection);

  const cameraNames = Object.keys(cameras);
  const activeName = selectedCamera ?? cameraNames[0] ?? null;
  const detections = activeName !== null ? (lastDetections[activeName] ?? []) : [];

  if (activeName === null) {
    return (
      <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
        No camera selected
      </div>
    );
  }

  if (detections.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
        No detections — run detector or start live loop
      </div>
    );
  }

  return (
    <div className="flex flex-col divide-y overflow-auto">
      {detections.map((det, i) => {
        const [x1, y1, x2, y2] = det.bbox_xyxy;
        const isSelected = selectedDetection === i;
        return (
          <button
            key={i}
            className={`flex items-center justify-between px-2 py-1 text-left text-xs transition-colors ${
              isSelected ? "bg-accent" : "hover:bg-muted"
            }`}
            onClick={() => setSelectedDetection(isSelected ? null : i)}
          >
            <span className="font-medium">{det.class_name}</span>
            <span className="ml-2 text-muted-foreground">
              {(det.confidence * 100).toFixed(0)}%
            </span>
            <span className="ml-auto font-mono text-muted-foreground">
              [{x1.toFixed(0)},{y1.toFixed(0)} {x2.toFixed(0)},{y2.toFixed(0)}]
            </span>
          </button>
        );
      })}
    </div>
  );
}
