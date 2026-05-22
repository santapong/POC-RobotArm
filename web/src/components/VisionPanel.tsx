/**
 * Vision panel — two-column flex layout.
 *
 * Left column: CameraView (MJPEG feed) + DetectionList.
 * Right column: controls — register camera/detector, calibrate, start/stop
 *   live detection, run once, and grasp preview.
 *
 * Loads camera/detector lists on first render.
 */

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { CameraView } from "./CameraView";
import { DetectionList } from "./DetectionList";
import { CameraDialog } from "./CameraDialog";
import { DetectorDialog } from "./DetectorDialog";
import { CalibrationWizard } from "./CalibrationWizard";
import { GraspButton } from "./GraspButton";
import {
  listCameras,
  listDetectors,
  removeCamera,
  removeDetector,
  runDetector,
  startLive,
  stopLive,
} from "@/api/vision";
import { useVisionStore } from "@/store/vision";
import { ApiError } from "@/api/client";

export function VisionPanel() {
  const cameras = useVisionStore((s) => s.cameras);
  const detectors = useVisionStore((s) => s.detectors);
  const selectedCamera = useVisionStore((s) => s.selectedCamera);
  const selectedDetector = useVisionStore((s) => s.selectedDetector);
  const liveLoops = useVisionStore((s) => s.liveLoops);
  const setCameras = useVisionStore((s) => s.setCameras);
  const setDetectors = useVisionStore((s) => s.setDetectors);
  const setSelectedCamera = useVisionStore((s) => s.setSelectedCamera);
  const setSelectedDetector = useVisionStore((s) => s.setSelectedDetector);
  const addLiveLoop = useVisionStore((s) => s.addLiveLoop);
  const removeLiveLoop = useVisionStore((s) => s.removeLiveLoop);

  const [cameraDialogOpen, setCameraDialogOpen] = useState(false);
  const [detectorDialogOpen, setDetectorDialogOpen] = useState(false);
  const [calibrationOpen, setCalibrationOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const cameraNames = Object.keys(cameras);
  const detectorNames = Object.keys(detectors);

  const activeCam = selectedCamera ?? cameraNames[0] ?? null;
  const activeDet = selectedDetector ?? detectorNames[0] ?? null;

  const isLive =
    activeCam !== null &&
    activeDet !== null &&
    liveLoops.some((l) => l.camera === activeCam && l.detector === activeDet);

  // Load lists on mount
  useEffect(() => {
    void listCameras().then(setCameras).catch(() => undefined);
    void listDetectors().then(setDetectors).catch(() => undefined);
  }, [setCameras, setDetectors]);

  async function handleRemoveCamera() {
    if (activeCam === null) return;
    setBusy(true);
    try {
      await removeCamera(activeCam);
      const updated = await listCameras();
      setCameras(updated);
      setSelectedCamera(null);
      toast.info(`Camera "${activeCam}" removed`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Remove camera failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveDetector() {
    if (activeDet === null) return;
    setBusy(true);
    try {
      await removeDetector(activeDet);
      const updated = await listDetectors();
      setDetectors(updated);
      setSelectedDetector(null);
      toast.info(`Detector "${activeDet}" removed`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Remove detector failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleRunOnce() {
    if (activeCam === null || activeDet === null) return;
    setBusy(true);
    try {
      const resp = await runDetector(activeDet, { camera: activeCam, return_grasp: false });
      toast.info(`Detected ${resp.detections.length} object(s)`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Detection failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleLive() {
    if (activeCam === null || activeDet === null) return;
    setBusy(true);
    try {
      if (isLive) {
        await stopLive(activeDet, activeCam);
        removeLiveLoop(activeDet, activeCam);
        toast.info("Live detection stopped");
      } else {
        await startLive(activeDet, activeCam, 5);
        addLiveLoop({ detector: activeDet, camera: activeCam });
        toast.info("Live detection started");
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Live loop error: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full gap-2 overflow-hidden p-2">
      {/* Left column: feed + detections */}
      <div className="flex min-w-0 flex-1 flex-col gap-2 overflow-hidden">
        <CameraView />
        <div className="min-h-0 flex-1 overflow-auto rounded border">
          <div className="px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Detections
          </div>
          <Separator />
          <DetectionList />
        </div>
      </div>

      {/* Right column: controls */}
      <div className="flex w-48 shrink-0 flex-col gap-2 overflow-y-auto">
        {/* Camera section */}
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Camera
        </div>

        {cameraNames.length > 0 && (
          <Select
            value={activeCam ?? ""}
            onValueChange={(v) => setSelectedCamera(v || null)}
          >
            <SelectTrigger className="h-7 text-xs">
              <SelectValue placeholder="Select camera" />
            </SelectTrigger>
            <SelectContent>
              {cameraNames.map((n) => (
                <SelectItem key={n} value={n} className="text-xs">
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <div className="flex gap-1">
          <Button
            size="sm"
            variant="outline"
            className="flex-1 text-xs"
            onClick={() => setCameraDialogOpen(true)}
          >
            + Add
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-xs text-destructive"
            onClick={() => void handleRemoveCamera()}
            disabled={activeCam === null || busy}
          >
            Del
          </Button>
        </div>

        <Button
          size="sm"
          variant="outline"
          className="text-xs"
          onClick={() => setCalibrationOpen(true)}
          disabled={activeCam === null}
        >
          Calibrate...
        </Button>

        <Separator />

        {/* Detector section */}
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Detector
        </div>

        {detectorNames.length > 0 && (
          <Select
            value={activeDet ?? ""}
            onValueChange={(v) => setSelectedDetector(v || null)}
          >
            <SelectTrigger className="h-7 text-xs">
              <SelectValue placeholder="Select detector" />
            </SelectTrigger>
            <SelectContent>
              {detectorNames.map((n) => (
                <SelectItem key={n} value={n} className="text-xs">
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <div className="flex gap-1">
          <Button
            size="sm"
            variant="outline"
            className="flex-1 text-xs"
            onClick={() => setDetectorDialogOpen(true)}
          >
            + Add
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-xs text-destructive"
            onClick={() => void handleRemoveDetector()}
            disabled={activeDet === null || busy}
          >
            Del
          </Button>
        </div>

        <Button
          size="sm"
          variant="outline"
          className="text-xs"
          onClick={() => void handleRunOnce()}
          disabled={activeCam === null || activeDet === null || busy}
        >
          Run once
        </Button>

        <Button
          size="sm"
          variant={isLive ? "destructive" : "default"}
          className="text-xs"
          onClick={() => void handleToggleLive()}
          disabled={activeCam === null || activeDet === null || busy}
        >
          {isLive ? "Stop live" : "Start live"}
        </Button>

        <Separator />

        {/* Grasp section */}
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Grasp
        </div>
        <GraspButton preview />
      </div>

      {/* Dialogs */}
      <CameraDialog open={cameraDialogOpen} onClose={() => setCameraDialogOpen(false)} />
      <DetectorDialog open={detectorDialogOpen} onClose={() => setDetectorDialogOpen(false)} />
      <CalibrationWizard open={calibrationOpen} onClose={() => setCalibrationOpen(false)} />
    </div>
  );
}
