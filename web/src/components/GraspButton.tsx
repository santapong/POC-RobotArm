/**
 * Grasp preview button.
 *
 * Calls `POST /detectors/<name>/run {return_grasp: true}` on the selected
 * detector + camera, displays the grasp pose xyz/quat in a toast, and
 * optionally previews the joint solution in the sim via `POST /api/vision/grasp_preview`.
 */

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { runDetector, graspPreview } from "@/api/vision";
import { useVisionStore } from "@/store/vision";
import { useStationStore } from "@/store/station";
import { ApiError } from "@/api/client";

interface Props {
  /** Whether to also call graspPreview after detecting (drives the sim). */
  preview?: boolean;
}

export function GraspButton({ preview = false }: Props) {
  const selectedCamera = useVisionStore((s) => s.selectedCamera);
  const selectedDetector = useVisionStore((s) => s.selectedDetector);
  const cameras = useVisionStore((s) => s.cameras);
  const detectors = useVisionStore((s) => s.detectors);
  // Pick first robot in station (parity with the jog-panel pattern in Layout.tsx).
  const firstRobotId = useStationStore((s) => s.station?.robots?.[0]?.name ?? null);

  const [busy, setBusy] = useState(false);

  const cameraNames = Object.keys(cameras);
  const detectorNames = Object.keys(detectors);

  const activeCam = selectedCamera ?? cameraNames[0] ?? null;
  const activeDet = selectedDetector ?? detectorNames[0] ?? null;

  const disabled = activeCam === null || activeDet === null || busy;

  async function handleGrasp() {
    if (activeCam === null || activeDet === null) return;
    setBusy(true);
    try {
      const resp = await runDetector(activeDet, {
        camera: activeCam,
        return_grasp: true,
        plane_z_m: 0.0,
      });

      if (resp.grasps.length === 0) {
        toast.warning("No grasps returned — check detections");
        return;
      }

      const g = resp.grasps[0];
      const [x, y, z] = g.xyz_m;
      const [qw, qx, qy, qz] = g.quat_wxyz;
      toast.success(
        `Grasp: xyz=[${x.toFixed(3)}, ${y.toFixed(3)}, ${z.toFixed(3)}] ` +
          `q=[${qw.toFixed(3)}, ${qx.toFixed(3)}, ${qy.toFixed(3)}, ${qz.toFixed(3)}]`,
      );

      if (preview) {
        if (firstRobotId === null) {
          toast.warning("No robot in station — cannot run grasp preview");
        } else {
          try {
            const previewResp = await graspPreview({
              robot_id: firstRobotId,
              grasp: g,
              preview_mode: "ik_only",
            });
            if (previewResp.reachable) {
              toast.info("Sim preview updated — pose is reachable");
            } else {
              const detail = previewResp.error
                ? ` (${previewResp.error})`
                : ` residual ${previewResp.ik_residual_m.toFixed(4)} m`;
              toast.warning(`Pose unreachable${detail}`);
            }
          } catch (previewErr) {
            const msg = previewErr instanceof ApiError ? previewErr.detail : String(previewErr);
            toast.error(`Preview failed: ${msg}`);
          }
        }
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Grasp failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button
      size="sm"
      variant="default"
      disabled={disabled}
      onClick={() => void handleGrasp()}
      title={
        activeCam === null
          ? "No camera selected"
          : activeDet === null
            ? "No detector selected"
            : `Run ${activeDet} on ${activeCam} and return grasp pose`
      }
    >
      {busy ? "Running..." : "Grasp"}
    </Button>
  );
}
