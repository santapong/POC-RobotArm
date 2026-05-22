/**
 * Register-camera dialog.
 *
 * Supports "real" (USB capture) and "fake" (file-backed) camera kinds.
 * For fake cameras, the user picks one or more image files, which are
 * uploaded via `POST /api/assets/import` and the returned absolute paths
 * are passed as `fake_image_paths` to `POST /api/vision/cameras`.
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
import { addCamera, listCameras } from "@/api/vision";
import { importAsset } from "@/api/assets";
import { useVisionStore } from "@/store/vision";
import { ApiError } from "@/api/client";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CameraDialog({ open, onClose }: Props) {
  const setCameras = useVisionStore((s) => s.setCameras);

  const [kind, setKind] = useState<"real" | "fake">("fake");
  const [name, setName] = useState("");
  const [source, setSource] = useState("0");
  const [width, setWidth] = useState("640");
  const [height, setHeight] = useState("480");
  const [fps, setFps] = useState("15");
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);

  function reset() {
    setKind("fake");
    setName("");
    setSource("0");
    setWidth("640");
    setHeight("480");
    setFps("15");
    setImageFiles([]);
    setBusy(false);
  }

  async function handleSubmit() {
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("Camera name is required");
      return;
    }

    setBusy(true);
    try {
      let fakePaths: string[] = [];

      if (kind === "fake" && imageFiles.length > 0) {
        // Upload each image via /api/assets/import and collect absolute paths.
        const uploadResults = await Promise.all(
          imageFiles.map((f) => importAsset(f, undefined, false)),
        );
        // saved_path is the absolute disk path the server wrote the file to;
        // FakeCamera requires an absolute path to open the image.
        fakePaths = uploadResults.map((r) => r.saved_path);
      }

      const cameraSource = kind === "real" ? (parseInt(source, 10) || source) : source;

      await addCamera({
        kind,
        source: cameraSource,
        name: trimmedName,
        width: parseInt(width, 10),
        height: parseInt(height, 10),
        fake_image_paths: kind === "fake" ? fakePaths : [],
        fps: parseFloat(fps),
      });

      // Refresh camera list in the store.
      const updated = await listCameras();
      setCameras(updated);

      toast.success(`Camera "${trimmedName}" registered`);
      reset();
      onClose();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Failed to register camera: ${msg}`);
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
          <DialogTitle>Register Camera</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3 py-2">
          {/* Kind */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium">Kind</label>
            <Select value={kind} onValueChange={(v) => setKind(v as "real" | "fake")}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fake" className="text-xs">
                  Fake (file-backed)
                </SelectItem>
                <SelectItem value="real" className="text-xs">
                  Real (USB / device)
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Name */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium">Name</label>
            <Input
              className="h-8 text-xs"
              placeholder="e.g. cam0"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* Source (only for real) */}
          {kind === "real" && (
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium">Source (device index or path)</label>
              <Input
                className="h-8 text-xs"
                placeholder="0"
                value={source}
                onChange={(e) => setSource(e.target.value)}
              />
            </div>
          )}

          {/* Fake image picker */}
          {kind === "fake" && (
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium">
                Image files (leave empty for generated test pattern)
              </label>
              <Input
                className="h-8 text-xs"
                type="file"
                accept="image/*"
                multiple
                onChange={(e) => setImageFiles(Array.from(e.target.files ?? []))}
              />
              {imageFiles.length > 0 && (
                <span className="text-xs text-muted-foreground">
                  {imageFiles.length} file(s) selected
                </span>
              )}
            </div>
          )}

          {/* Resolution + FPS */}
          <div className="grid grid-cols-3 gap-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium">Width</label>
              <Input
                className="h-8 text-xs"
                type="number"
                min={1}
                value={width}
                onChange={(e) => setWidth(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium">Height</label>
              <Input
                className="h-8 text-xs"
                type="number"
                min={1}
                value={height}
                onChange={(e) => setHeight(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium">FPS</label>
              <Input
                className="h-8 text-xs"
                type="number"
                min={1}
                max={120}
                step={0.5}
                value={fps}
                onChange={(e) => setFps(e.target.value)}
              />
            </div>
          </div>
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
