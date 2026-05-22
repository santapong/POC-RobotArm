/**
 * Register-detector dialog.
 *
 * Supports two detector kinds:
 *  - "color": HSV lower/upper ranges, min_area_px, class_name (optional second range)
 *  - "yolo": model_path, conf_threshold
 */

import { useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { addDetector, listDetectors } from "@/api/vision";
import { useVisionStore } from "@/store/vision";
import { ApiError } from "@/api/client";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function DetectorDialog({ open, onClose }: Props) {
  const setDetectors = useVisionStore((s) => s.setDetectors);

  const [kind, setKind] = useState<"color" | "yolo">("color");
  const [detName, setDetName] = useState("");

  // Color detector fields
  const [hsvLower, setHsvLower] = useState("0,120,70");
  const [hsvUpper, setHsvUpper] = useState("10,255,255");
  const [hsvLower2, setHsvLower2] = useState("170,120,70");
  const [hsvUpper2, setHsvUpper2] = useState("180,255,255");
  const [useSecondRange, setUseSecondRange] = useState(true);
  const [minAreaPx, setMinAreaPx] = useState("200");
  const [className, setClassName] = useState("red_cube");

  // YOLO fields
  const [modelPath, setModelPath] = useState("yolov8n.pt");
  const [confThreshold, setConfThreshold] = useState("0.25");

  const [busy, setBusy] = useState(false);

  function reset() {
    setKind("color");
    setDetName("");
    setHsvLower("0,120,70");
    setHsvUpper("10,255,255");
    setHsvLower2("170,120,70");
    setHsvUpper2("180,255,255");
    setUseSecondRange(true);
    setMinAreaPx("200");
    setClassName("red_cube");
    setModelPath("yolov8n.pt");
    setConfThreshold("0.25");
    setBusy(false);
  }

  function parseTriplet(s: string): [number, number, number] {
    const parts = s.split(",").map((v) => parseFloat(v.trim()));
    return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0];
  }

  async function handleSubmit() {
    const trimmedName = detName.trim();
    if (!trimmedName) {
      toast.error("Detector name is required");
      return;
    }

    let config: Record<string, unknown>;
    if (kind === "color") {
      const [h1, s1, v1] = parseTriplet(hsvLower);
      const [h2, s2, v2] = parseTriplet(hsvUpper);
      config = {
        hsv_lower: [h1, s1, v1],
        hsv_upper: [h2, s2, v2],
        min_area_px: parseInt(minAreaPx, 10),
        class_name: className.trim() || "object",
      };
      if (useSecondRange) {
        const [h3, s3, v3] = parseTriplet(hsvLower2);
        const [h4, s4, v4] = parseTriplet(hsvUpper2);
        config.hsv_lower2 = [h3, s3, v3];
        config.hsv_upper2 = [h4, s4, v4];
      }
    } else {
      config = {
        model_path: modelPath.trim(),
        conf_threshold: parseFloat(confThreshold),
      };
    }

    setBusy(true);
    try {
      await addDetector({ kind, name: trimmedName, config });
      const updated = await listDetectors();
      setDetectors(updated);
      toast.success(`Detector "${trimmedName}" registered`);
      reset();
      onClose();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Failed to register detector: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Register Detector</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3 py-2">
          {/* Kind */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium">Kind</label>
            <Select value={kind} onValueChange={(v) => setKind(v as "color" | "yolo")}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="color" className="text-xs">
                  Color (HSV threshold)
                </SelectItem>
                <SelectItem value="yolo" className="text-xs">
                  YOLO (ML detector)
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Name */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium">Name</label>
            <Input
              className="h-8 text-xs"
              placeholder="e.g. red_cube_det"
              value={detName}
              onChange={(e) => setDetName(e.target.value)}
            />
          </div>

          {kind === "color" ? (
            <>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Class name</label>
                <Input
                  className="h-8 text-xs"
                  placeholder="red_cube"
                  value={className}
                  onChange={(e) => setClassName(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium">HSV lower (H,S,V)</label>
                  <Input
                    className="h-8 text-xs font-mono"
                    value={hsvLower}
                    onChange={(e) => setHsvLower(e.target.value)}
                    placeholder="0,120,70"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium">HSV upper (H,S,V)</label>
                  <Input
                    className="h-8 text-xs font-mono"
                    value={hsvUpper}
                    onChange={(e) => setHsvUpper(e.target.value)}
                    placeholder="10,255,255"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="second-range"
                  checked={useSecondRange}
                  onChange={(e) => setUseSecondRange(e.target.checked)}
                  className="h-3 w-3"
                />
                <label htmlFor="second-range" className="text-xs">
                  Enable second HSV range (red wraparound)
                </label>
              </div>

              {useSecondRange && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium">HSV lower 2</label>
                    <Input
                      className="h-8 text-xs font-mono"
                      value={hsvLower2}
                      onChange={(e) => setHsvLower2(e.target.value)}
                      placeholder="170,120,70"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium">HSV upper 2</label>
                    <Input
                      className="h-8 text-xs font-mono"
                      value={hsvUpper2}
                      onChange={(e) => setHsvUpper2(e.target.value)}
                      placeholder="180,255,255"
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Min area (px)</label>
                <Input
                  className="h-8 text-xs"
                  type="number"
                  min={1}
                  value={minAreaPx}
                  onChange={(e) => setMinAreaPx(e.target.value)}
                />
              </div>
            </>
          ) : (
            <>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Model path</label>
                <Input
                  className="h-8 text-xs font-mono"
                  placeholder="yolov8n.pt"
                  value={modelPath}
                  onChange={(e) => setModelPath(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Confidence threshold</label>
                <Input
                  className="h-8 text-xs"
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={confThreshold}
                  onChange={(e) => setConfThreshold(e.target.value)}
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              reset();
              onClose();
            }}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button size="sm" onClick={() => void handleSubmit()} disabled={busy}>
            {busy ? "Registering..." : "Register"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
