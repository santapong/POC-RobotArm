/**
 * Hand-eye calibration wizard — 3-step shadcn Dialog.
 *
 * Step 0: Intrinsic capture.
 *   - User snaps N>=5 frames via GET /cameras/<n>/snapshot (no overlay).
 *   - On "Solve", calls POST /calibrate/intrinsic with the collected blobs.
 *
 * Step 1: Hand-eye pose-pair capture.
 *   - Reads tcp_xyz_m / tcp_quat_wxyz / joints_rad from useTelemetryStore.
 *   - Calls POST /charuco_pose to get R_target2cam / t_target2cam.
 *   - Converts quat to rotation matrix via quatToRotMatrix.
 *   - Accumulates N>=3 PosePairModel entries.
 *
 * Step 2: Solve hand-eye.
 *   - User picks method (park / tsai / horaud / andreff / daniilidis).
 *   - Calls POST /calibrate/hand-eye with pose_pairs + method + mount.
 */

import { useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { calibrateIntrinsic, calibrateHandEye, charucoPose } from "@/api/vision";
import { useVisionStore } from "@/store/vision";
import { getStateRef as getTelemetryStateRef } from "@/store/telemetry";
import { quatToRotMatrix } from "@/lib/math";
import { ApiError } from "@/api/client";
import type { PosePairModel } from "@/api/types";

type HandEyeMethod = "tsai" | "park" | "horaud" | "andreff" | "daniilidis";

interface WizardState {
  step: 0 | 1 | 2;
  intrinsicFrames: File[];
  posePairs: PosePairModel[];
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CalibrationWizard({ open, onClose }: Props) {
  const selectedCamera = useVisionStore((s) => s.selectedCamera);
  const cameras = useVisionStore((s) => s.cameras);
  const setIntrinsics = useVisionStore((s) => s.setIntrinsics);
  const setExtrinsics = useVisionStore((s) => s.setExtrinsics);

  const cameraNames = Object.keys(cameras);
  const activeCam = selectedCamera ?? cameraNames[0] ?? null;

  const [state, setState] = useState<WizardState>({
    step: 0,
    intrinsicFrames: [],
    posePairs: [],
  });
  const [method, setMethod] = useState<HandEyeMethod>("park");
  const [mount, setMount] = useState<"eye_to_hand" | "eye_in_hand">("eye_to_hand");
  const [busy, setBusy] = useState(false);

  function resetWizard() {
    setState({ step: 0, intrinsicFrames: [], posePairs: [] });
    setMethod("park");
    setMount("eye_to_hand");
    setBusy(false);
  }

  // ----- Step 0: snap a calibration frame -----

  async function handleSnapIntrinsic() {
    if (activeCam === null) return;
    setBusy(true);
    try {
      const resp = await fetch(
        `/api/vision/cameras/${encodeURIComponent(activeCam)}/snapshot?overlay=0`,
      );
      if (!resp.ok) {
        toast.error(`Snapshot failed: HTTP ${resp.status}`);
        return;
      }
      const blob = await resp.blob();
      const file = new File([blob], `snap_${state.intrinsicFrames.length}.jpg`, {
        type: "image/jpeg",
      });
      setState((prev) => ({
        ...prev,
        intrinsicFrames: [...prev.intrinsicFrames, file],
      }));
      toast.info(`Snapshot ${state.intrinsicFrames.length + 1} captured`);
    } catch (err) {
      toast.error(`Snapshot error: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleSolveIntrinsic() {
    if (activeCam === null || state.intrinsicFrames.length < 5) {
      toast.error("Need at least 5 frames for intrinsic calibration");
      return;
    }
    setBusy(true);
    try {
      const result = await calibrateIntrinsic(activeCam, state.intrinsicFrames);
      setIntrinsics(activeCam, result);
      toast.success(`Intrinsics solved: fx=${result.fx.toFixed(1)}, fy=${result.fy.toFixed(1)}`);
      setState((prev) => ({ ...prev, step: 1 }));
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Intrinsic calibration failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  // ----- Step 1: capture a pose pair -----

  async function handleCapturePair() {
    if (activeCam === null) return;
    setBusy(true);
    try {
      // Read current TCP / joint state from the vanilla store ref (safe in async).
      const telState = getTelemetryStateRef();
      const tcp_xyz_m = telState.tcp_xyz_m;
      const tcp_quat_wxyz = telState.tcp_quat_wxyz;

      // Build R_gripper2base from the TCP quaternion.
      const R_gripper2base = quatToRotMatrix(tcp_quat_wxyz);
      const t_gripper2base: [number, number, number] = [...tcp_xyz_m];

      // Detect ChArUco board in the current camera frame.
      const charuco = await charucoPose(activeCam);
      const R_target2cam = charuco.R_target2cam;
      const t_target2cam = charuco.t_target2cam;

      const pair: PosePairModel = {
        R_gripper2base,
        t_gripper2base,
        R_target2cam,
        t_target2cam,
      };

      setState((prev) => ({
        ...prev,
        posePairs: [...prev.posePairs, pair],
      }));
      toast.info(`Pose pair ${state.posePairs.length + 1} captured`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Pair capture failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  // ----- Step 2: solve hand-eye -----

  async function handleSolveHandEye() {
    if (activeCam === null || state.posePairs.length < 3) {
      toast.error("Need at least 3 pose pairs for hand-eye calibration");
      return;
    }
    setBusy(true);
    try {
      const result = await calibrateHandEye(activeCam, {
        pose_pairs: state.posePairs,
        method,
        mount,
        reference_frame: "world",
      });
      setExtrinsics(activeCam, result);
      const [tx, ty, tz] = result.t_cam_in_world;
      toast.success(
        `Hand-eye solved (${method}): t=[${tx.toFixed(3)}, ${ty.toFixed(3)}, ${tz.toFixed(3)}]`,
      );
      resetWizard();
      onClose();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Hand-eye calibration failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  const stepTitles = [
    "Step 1 of 3 — Intrinsic Calibration",
    "Step 2 of 3 — Hand-Eye Pose Pairs",
    "Step 3 of 3 — Solve Hand-Eye",
  ];

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          resetWizard();
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Calibration Wizard</DialogTitle>
          <DialogDescription>{stepTitles[state.step]}</DialogDescription>
        </DialogHeader>

        {/* ---- Step 0: Intrinsic ---- */}
        {state.step === 0 && (
          <div className="flex flex-col gap-3 py-2">
            {activeCam === null ? (
              <p className="text-xs text-destructive">No camera selected — close and select one first.</p>
            ) : (
              <>
                <p className="text-xs text-muted-foreground">
                  Place a ChArUco board in view, then snap at least 5 frames from
                  different angles. Press "Solve" when ready.
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void handleSnapIntrinsic()}
                    disabled={busy || activeCam === null}
                  >
                    Snap ({state.intrinsicFrames.length})
                  </Button>
                  {state.intrinsicFrames.length > 0 && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs text-destructive"
                      onClick={() =>
                        setState((prev) => ({ ...prev, intrinsicFrames: [] }))
                      }
                      disabled={busy}
                    >
                      Clear
                    </Button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Frames captured: {state.intrinsicFrames.length} / 5 minimum
                </p>
              </>
            )}
          </div>
        )}

        {/* ---- Step 1: Pose pairs ---- */}
        {state.step === 1 && (
          <div className="flex flex-col gap-3 py-2">
            <p className="text-xs text-muted-foreground">
              Jog the robot to different poses, place the ChArUco board in view,
              then press "Capture pair". Repeat at least 3 times.
            </p>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void handleCapturePair()}
                disabled={busy || activeCam === null}
              >
                Capture pair ({state.posePairs.length})
              </Button>
              {state.posePairs.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-xs text-destructive"
                  onClick={() => setState((prev) => ({ ...prev, posePairs: [] }))}
                  disabled={busy}
                >
                  Clear
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Pairs captured: {state.posePairs.length} / 3 minimum
            </p>
          </div>
        )}

        {/* ---- Step 2: Solve ---- */}
        {state.step === 2 && (
          <div className="flex flex-col gap-3 py-2">
            <p className="text-xs text-muted-foreground">
              Select the solver method and camera mount type, then solve.
            </p>

            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Method</label>
                <Select value={method} onValueChange={(v) => setMethod(v as HandEyeMethod)}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(["park", "tsai", "horaud", "andreff", "daniilidis"] as HandEyeMethod[]).map(
                      (m) => (
                        <SelectItem key={m} value={m} className="text-xs">
                          {m}
                        </SelectItem>
                      ),
                    )}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium">Mount</label>
                <Select
                  value={mount}
                  onValueChange={(v) => setMount(v as "eye_to_hand" | "eye_in_hand")}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="eye_to_hand" className="text-xs">
                      Eye-to-hand (static)
                    </SelectItem>
                    <SelectItem value="eye_in_hand" className="text-xs">
                      Eye-in-hand (wrist)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              {state.posePairs.length} pose pair(s) collected.
            </p>
          </div>
        )}

        <DialogFooter className="flex flex-row gap-2">
          {/* Back */}
          {state.step > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setState((prev) => ({ ...prev, step: (prev.step - 1) as 0 | 1 | 2 }))
              }
              disabled={busy}
            >
              Back
            </Button>
          )}

          {/* Cancel */}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              resetWizard();
              onClose();
            }}
            disabled={busy}
          >
            Cancel
          </Button>

          {/* Primary action */}
          {state.step === 0 && (
            <Button
              size="sm"
              onClick={() => void handleSolveIntrinsic()}
              disabled={busy || state.intrinsicFrames.length < 5 || activeCam === null}
            >
              {busy ? "Solving..." : "Solve Intrinsics"}
            </Button>
          )}
          {state.step === 1 && (
            <Button
              size="sm"
              onClick={() =>
                setState((prev) => ({ ...prev, step: 2 }))
              }
              disabled={state.posePairs.length < 3}
            >
              Next
            </Button>
          )}
          {state.step === 2 && (
            <Button
              size="sm"
              onClick={() => void handleSolveHandEye()}
              disabled={busy || state.posePairs.length < 3 || activeCam === null}
            >
              {busy ? "Solving..." : "Solve Hand-Eye"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
