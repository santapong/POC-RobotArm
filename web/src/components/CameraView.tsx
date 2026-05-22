/**
 * MJPEG camera view.
 *
 * Renders the live MJPEG stream for the selected camera as an `<img>` tag.
 * Clicking the frame selects a camera. When no camera is selected, shows
 * a placeholder message.
 */

import { useVisionStore } from "@/store/vision";
import { streamUrl } from "@/api/vision";

export function CameraView() {
  const selectedCamera = useVisionStore((s) => s.selectedCamera);
  const cameras = useVisionStore((s) => s.cameras);
  const setSelectedCamera = useVisionStore((s) => s.setSelectedCamera);

  const cameraNames = Object.keys(cameras);

  if (cameraNames.length === 0) {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded border bg-muted text-xs text-muted-foreground">
        No cameras registered
      </div>
    );
  }

  const activeName = selectedCamera ?? cameraNames[0];

  return (
    <div className="flex flex-col gap-1">
      {/* Camera selector tabs when multiple cameras are present */}
      {cameraNames.length > 1 && (
        <div className="flex gap-1 overflow-x-auto">
          {cameraNames.map((name) => (
            <button
              key={name}
              className={`shrink-0 rounded px-2 py-0.5 text-xs transition-colors ${
                name === activeName
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
              onClick={() => setSelectedCamera(name)}
            >
              {name}
            </button>
          ))}
        </div>
      )}

      {/* MJPEG frame */}
      <div
        className="aspect-video w-full cursor-pointer overflow-hidden rounded border"
        onClick={() => setSelectedCamera(activeName)}
      >
        <img
          key={activeName}
          src={streamUrl(activeName, true, 12)}
          alt={`Camera feed: ${activeName}`}
          className="h-full w-full object-contain"
        />
      </div>
    </div>
  );
}
