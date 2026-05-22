/**
 * TrajectoryPreview — scrubber + playback controls for a completed plan
 * trajectory.
 *
 * Writes synthesised TelemetryFrames into `useTelemetryStore.applyFrame` at
 * ~30 Hz when playing, using linear interpolation between trajectory samples.
 * The `RobotURDF` component reads from the same store and picks up changes
 * automatically (last-writer-wins with live telemetry — banner makes it
 * visible).
 *
 * TCP xyz/quat are fetched once from `/api/station/robots/{id}/state` at
 * preview start and held constant; forward-kinematics fidelity is acceptable
 * for scrub preview.
 *
 * Returns null when there is no active completed trajectory.
 */

import { useCallback, useEffect, useRef } from "react";
import { toast } from "sonner";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { usePlanningStore } from "@/store/planning";
import { applyFrame } from "@/store/telemetry";
import { getRobotState } from "@/api/robots";
import { ApiError } from "@/api/client";
import type { TrajectorySampleModel, TimedTrajectoryModel } from "@/api/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function lerpSample(
  a: TrajectorySampleModel,
  b: TrajectorySampleModel,
  t: number,
): TrajectorySampleModel {
  return {
    t_s: lerp(a.t_s, b.t_s, t),
    q_rad: a.q_rad.map((v, i) => lerp(v, b.q_rad[i] ?? v, t)),
    qd_rad_s: a.qd_rad_s.map((v, i) => lerp(v, b.qd_rad_s[i] ?? v, t)),
    qdd_rad_s2: a.qdd_rad_s2.map((v, i) => lerp(v, b.qdd_rad_s2[i] ?? v, t)),
  };
}

function sampleAt(traj: TimedTrajectoryModel, t: number): TrajectorySampleModel {
  const n = traj.samples.length;
  if (n === 0) return { t_s: t, q_rad: [], qd_rad_s: [], qdd_rad_s2: [] };
  if (n === 1) return traj.samples[0];

  const clamped = Math.max(0, Math.min(t, traj.duration_s));
  const idx = clamped / traj.dt_s;
  const i0 = Math.min(Math.floor(idx), n - 2);
  const i1 = i0 + 1;
  const frac = idx - i0;

  const s0 = traj.samples[i0];
  const s1 = traj.samples[i1];
  if (!s0 || !s1) return traj.samples[n - 1];
  return lerpSample(s0, s1, frac);
}

const SPEED_OPTIONS = [0.25, 0.5, 1.0, 2.0];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TrajectoryPreview(): JSX.Element | null {
  const activePlanId = usePlanningStore((s) => s.activePlanId);
  const plans = usePlanningStore((s) => s.plans);
  const previewTimeS = usePlanningStore((s) => s.previewTimeS);
  const previewPlaying = usePlanningStore((s) => s.previewPlaying);
  const previewSpeed = usePlanningStore((s) => s.previewSpeed);
  const setPreviewTime = usePlanningStore((s) => s.setPreviewTime);
  const setPreviewPlaying = usePlanningStore((s) => s.setPreviewPlaying);
  const setPreviewSpeed = usePlanningStore((s) => s.setPreviewSpeed);

  const record = activePlanId !== null ? plans[activePlanId] : undefined;
  const trajectory = record?.trajectory ?? null;

  // Cached robot state (tcp pose held constant during preview).
  const tcpRef = useRef<{
    tcp_xyz_m: [number, number, number];
    tcp_quat_wxyz: [number, number, number, number];
  } | null>(null);

  // RAF handle and timing refs for the playback loop.
  const rafRef = useRef<number | null>(null);
  const lastTimestampRef = useRef<number | null>(null);
  // currentTimeRef tracks position inside the RAF loop without stale closure issues.
  const currentTimeRef = useRef<number>(previewTimeS);

  // Keep currentTimeRef in sync with store changes from scrubbing (not playing).
  useEffect(() => {
    currentTimeRef.current = previewTimeS;
  }, [previewTimeS]);

  // Fetch robot TCP state once when preview starts.
  useEffect(() => {
    if (!previewPlaying || !record) return;
    const robotId = record.request.robot_id;
    getRobotState(robotId)
      .then((state) => {
        tcpRef.current = {
          tcp_xyz_m: state.tcp_xyz_m,
          tcp_quat_wxyz: state.tcp_quat_wxyz,
        };
      })
      .catch((err: unknown) => {
        const msg = err instanceof ApiError ? err.detail : String(err);
        toast.error(`Could not fetch robot state for preview: ${msg}`);
      });
  }, [previewPlaying, record]);

  // Apply a synthesised telemetry frame for a given time and trajectory.
  const applyPoseAt = useCallback(
    (t: number, traj: TimedTrajectoryModel) => {
      const sample = sampleAt(traj, t);
      const tcp = tcpRef.current;
      applyFrame({
        robot_id: traj.robot_id,
        joints_rad: sample.q_rad,
        tcp_xyz_m: tcp?.tcp_xyz_m ?? [0, 0, 0],
        tcp_quat_wxyz: tcp?.tcp_quat_wxyz ?? [1, 0, 0, 0],
        run_state: null,
        monotonic_s: t,
      });
    },
    [],
  );

  // Apply pose when scrubbing (not playing).
  useEffect(() => {
    if (!trajectory || previewPlaying) return;
    applyPoseAt(previewTimeS, trajectory);
  }, [previewTimeS, trajectory, previewPlaying, applyPoseAt]);

  // Playback RAF loop. Uses currentTimeRef to avoid stale closure on time.
  useEffect(() => {
    if (!previewPlaying || !trajectory) {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
        lastTimestampRef.current = null;
      }
      return;
    }

    const traj = trajectory;

    function tick(timestamp: number) {
      const last = lastTimestampRef.current;
      if (last !== null) {
        const dtMs = timestamp - last;
        const dtS = (dtMs / 1000) * previewSpeed;
        const next = Math.min(currentTimeRef.current + dtS, traj.duration_s);
        currentTimeRef.current = next;
        setPreviewTime(next);
        applyPoseAt(next, traj);
        if (next >= traj.duration_s) {
          setPreviewPlaying(false);
          lastTimestampRef.current = null;
          return;
        }
      }
      lastTimestampRef.current = timestamp;
      rafRef.current = requestAnimationFrame(tick);
    }

    lastTimestampRef.current = null;
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
        lastTimestampRef.current = null;
      }
    };
  }, [previewPlaying, trajectory, previewSpeed, setPreviewTime, setPreviewPlaying, applyPoseAt]);

  if (activePlanId === null || trajectory === null) return null;

  return (
    <div className="flex flex-col gap-2 p-2">
      {/* Preview-active banner (last-writer-wins advisory) */}
      {previewPlaying && (
        <div className="rounded bg-yellow-500/20 px-2 py-1 text-center text-xs font-medium text-yellow-700 dark:text-yellow-400">
          Preview mode — live pose suspended
        </div>
      )}

      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Trajectory preview
      </div>

      {/* Time scrubber */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{previewTimeS.toFixed(2)} s</span>
          <span>{trajectory.duration_s.toFixed(2)} s</span>
        </div>
        <Slider
          min={0}
          max={trajectory.duration_s}
          step={trajectory.dt_s}
          value={[previewTimeS]}
          onValueChange={([v]) => {
            setPreviewPlaying(false);
            setPreviewTime(v);
          }}
        />
      </div>

      {/* Playback controls */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          className="text-xs"
          onClick={() => setPreviewPlaying(!previewPlaying)}
        >
          {previewPlaying ? "Pause" : "Play"}
        </Button>

        <Button
          size="sm"
          variant="ghost"
          className="text-xs"
          onClick={() => {
            setPreviewPlaying(false);
            setPreviewTime(0);
          }}
        >
          Stop preview
        </Button>

        {/* Speed selector — plain select, no new shadcn primitive */}
        <select
          className="h-7 rounded border bg-background px-1 text-xs"
          value={previewSpeed}
          onChange={(e) => setPreviewSpeed(parseFloat(e.target.value))}
        >
          {SPEED_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>
      </div>

      {/* Sample info */}
      <div className="text-xs text-muted-foreground">
        {trajectory.samples.length} samples · dt {trajectory.dt_s.toFixed(3)} s
      </div>
    </div>
  );
}
