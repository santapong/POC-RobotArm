/**
 * PlanPanel — two-column layout for the Plan tab.
 *
 * Left column: planner configuration controls (kind, start joints, goal
 *   selector, obstacles, timeout, configure dialog), action buttons (Plan,
 *   Cancel, Execute), progress widget, and result summary.
 * Right column: TrajectoryPreview scrubber.
 */

import { useState } from "react";
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
import { Slider } from "@/components/ui/slider";
import { usePlanningStore } from "@/store/planning";
import { useTelemetryStore } from "@/store/telemetry";
import { useStationStore } from "@/store/station";
import { useVisionStore } from "@/store/vision";
import { createPlan, cancelPlan, executePlan } from "@/api/planning";
import { ApiError } from "@/api/client";
import { PlanProgress } from "./PlanProgress";
import { PlannerConfigDialog } from "./PlannerConfigDialog";
import { TrajectoryPreview } from "./TrajectoryPreview";
import type { PlannerKindModel, PlanRequestModel } from "@/api/types";

// ---------------------------------------------------------------------------
// Goal mode type
// ---------------------------------------------------------------------------

type GoalMode = "current_pose" | "grasp_from_detection" | "manual_joints";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PlanPanel(): JSX.Element {
  const station = useStationStore((s) => s.station);
  const joints_rad = useTelemetryStore((s) => s.joints_rad);
  const selectedCamera = useVisionStore((s) => s.selectedCamera);
  const lastGrasps = useVisionStore((s) => s.lastGrasps);

  const config = usePlanningStore((s) => s.config);
  const activePlanId = usePlanningStore((s) => s.activePlanId);
  const plans = usePlanningStore((s) => s.plans);
  const setConfig = usePlanningStore((s) => s.setConfig);
  const setPlan = usePlanningStore((s) => s.setPlan);
  const setActive = usePlanningStore((s) => s.setActive);

  const [configOpen, setConfigOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [planningUnavailable, setPlanningUnavailable] = useState(false);

  // Start joints — "Use current" latches the live joints_rad.
  const [startJoints, setStartJoints] = useState<number[]>(joints_rad);

  // Goal mode
  const [goalMode, setGoalMode] = useState<GoalMode>("current_pose");

  // Manual joints goal inputs (one per DOF of startJoints)
  const [manualGoalJoints, setManualGoalJoints] = useState<number[]>(() =>
    joints_rad.map(() => 0),
  );

  // Obstacle multi-select (all fixture names, user-toggled subset)
  const fixtureNames = station?.fixtures.map((f) => f.name) ?? [];
  const [selectedObstacles, setSelectedObstacles] = useState<string[]>([]);

  function toggleObstacle(name: string) {
    setSelectedObstacles((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  }

  // Derived: robot_id (first robot in station)
  const robotId = station?.robots[0]?.name ?? null;

  // Grasp availability for "grasp_from_detection" option
  const activeCamGrasps = selectedCamera ? (lastGrasps[selectedCamera] ?? []) : [];
  const graspAvailable = activeCamGrasps.length > 0;

  // Active plan record
  const activePlan = activePlanId !== null ? plans[activePlanId] : null;
  const isRunning = activePlan?.status === "running";
  const isCompleted = activePlan?.status === "completed";

  // Build PlanRequestModel from current UI state
  function buildRequest(): PlanRequestModel | null {
    if (!robotId) return null;

    let goal_q: number[] | null = null;
    let goal_pose_xyz_m: [number, number, number] | null = null;
    let goal_pose_quat_wxyz: [number, number, number, number] | null = null;

    if (goalMode === "manual_joints") {
      goal_q = [...manualGoalJoints];
    } else if (goalMode === "grasp_from_detection") {
      const grasp = activeCamGrasps[0];
      if (!grasp) return null;
      goal_pose_xyz_m = grasp.xyz_m;
      goal_pose_quat_wxyz = grasp.quat_wxyz;
    } else {
      // current_pose — use the current TCP as goal pose; requires telemetry
      // to have a valid reading. We fall back to manual_joints if no pose is
      // available by sending current joints as goal.
      goal_q = [...joints_rad];
    }

    return {
      robot_id: robotId,
      q_start: [...startJoints],
      goal_q,
      goal_pose_xyz_m,
      goal_pose_quat_wxyz,
      obstacles: selectedObstacles,
      planner: {
        kind: config.kind,
        timeout_s: config.timeout_s,
        smoothing_iterations: config.smoothing_iterations,
        range_rad: config.range_rad,
        clearance_m: config.clearance_m,
        qdd_max_rad_s2_default: config.qdd_max_rad_s2_default,
      },
      optimizer: config.optimizer,
      parameteriser: config.parameteriser,
    };
  }

  async function handlePlan() {
    const req = buildRequest();
    if (!req) return;
    setBusy(true);
    try {
      const resp = await createPlan(req);
      // Seed the record so PlanProgress renders immediately.
      setPlan({
        plan_id: resp.plan_id,
        status: resp.status,
        stage: "queued",
        request: req,
        created_at: Date.now() / 1000,
        finished_at: null,
        elapsed_s: null,
        sampler_path_length: 0,
        optimizer_iterations: 0,
        parameteriser_grid_points: 0,
        cache_hit: false,
        error_code: null,
        error_message: null,
        singularity_hint: [],
        trajectory: null,
      });
      setActive(resp.plan_id);
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
        if (err.code === "PLANNING_UNAVAILABLE") {
          setPlanningUnavailable(true);
        }
      } else {
        toast.error(String(err));
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!activePlanId) return;
    setBusy(true);
    try {
      const updated = await cancelPlan(activePlanId);
      setPlan(updated);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Cancel failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleExecute() {
    if (!activePlanId) return;
    setBusy(true);
    try {
      await executePlan(activePlanId, { dt_s: 0.01 });
      toast.info("Execution started");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Execute failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full gap-2 overflow-hidden p-2">
      {/* Left column: controls */}
      <div className="flex w-52 shrink-0 flex-col gap-2 overflow-y-auto">
        {/* Planner kind */}
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Planner
        </div>
        <Select
          value={config.kind}
          onValueChange={(v) => setConfig({ kind: v as PlannerKindModel })}
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue placeholder="Planner kind" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="rrt" className="text-xs">RRT</SelectItem>
            <SelectItem value="rrt_star" className="text-xs">RRT*</SelectItem>
            <SelectItem value="prm" className="text-xs">PRM</SelectItem>
          </SelectContent>
        </Select>

        {/* Timeout */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Timeout</span>
            <span>{config.timeout_s.toFixed(1)} s</span>
          </div>
          <Slider
            min={0.5}
            max={30}
            step={0.5}
            value={[config.timeout_s]}
            onValueChange={([v]) => setConfig({ timeout_s: v })}
          />
        </div>

        <Button
          size="sm"
          variant="outline"
          className="text-xs"
          onClick={() => setConfigOpen(true)}
        >
          Configure...
        </Button>

        <Separator />

        {/* Start joints */}
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Start joints (rad)
        </div>
        <div className="space-y-0.5 text-xs text-muted-foreground">
          {startJoints.map((v, i) => (
            <div key={i} className="flex justify-between">
              <span>J{i + 1}</span>
              <span>{v.toFixed(3)}</span>
            </div>
          ))}
        </div>
        <Button
          size="sm"
          variant="outline"
          className="text-xs"
          onClick={() => setStartJoints([...joints_rad])}
        >
          Use current
        </Button>

        <Separator />

        {/* Goal selector */}
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Goal
        </div>
        <Select
          value={goalMode}
          onValueChange={(v) => setGoalMode(v as GoalMode)}
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue placeholder="Goal type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="current_pose" className="text-xs">Current pose</SelectItem>
            <SelectItem
              value="grasp_from_detection"
              className="text-xs"
              disabled={!graspAvailable}
            >
              Grasp from detection
            </SelectItem>
            <SelectItem value="manual_joints" className="text-xs">Manual joints</SelectItem>
          </SelectContent>
        </Select>

        {goalMode === "manual_joints" && (
          <div className="space-y-0.5">
            {manualGoalJoints.map((v, i) => (
              <div key={i} className="flex items-center gap-1">
                <span className="w-6 shrink-0 text-xs text-muted-foreground">J{i + 1}</span>
                <input
                  type="number"
                  className="w-full rounded border bg-background px-1 py-0.5 text-xs"
                  value={v}
                  step={0.01}
                  onChange={(e) => {
                    const next = [...manualGoalJoints];
                    next[i] = parseFloat(e.target.value) || 0;
                    setManualGoalJoints(next);
                  }}
                />
              </div>
            ))}
          </div>
        )}

        <Separator />

        {/* Obstacles */}
        {fixtureNames.length > 0 && (
          <>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Obstacles
            </div>
            <div className="space-y-1">
              {fixtureNames.map((name) => (
                <label key={name} className="flex items-center gap-1.5 text-xs">
                  <input
                    type="checkbox"
                    checked={selectedObstacles.includes(name)}
                    onChange={() => toggleObstacle(name)}
                    className="h-3 w-3"
                  />
                  {name}
                </label>
              ))}
            </div>
            <Separator />
          </>
        )}

        {/* Action buttons */}
        <Button
          size="sm"
          className="text-xs"
          onClick={() => void handlePlan()}
          disabled={robotId === null || busy || planningUnavailable}
        >
          Plan
        </Button>

        {isRunning && (
          <Button
            size="sm"
            variant="destructive"
            className="text-xs"
            onClick={() => void handleCancel()}
            disabled={busy}
          >
            Cancel
          </Button>
        )}

        <PlanProgress />

        {/* Result summary */}
        {activePlan && (
          <div className="rounded border p-2 text-xs space-y-0.5">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Status</span>
              <span>{activePlan.status}</span>
            </div>
            {activePlan.elapsed_s !== null && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Elapsed</span>
                <span>{activePlan.elapsed_s.toFixed(2)} s</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Path length</span>
              <span>{activePlan.sampler_path_length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Opt. iter.</span>
              <span>{activePlan.optimizer_iterations}</span>
            </div>
            {activePlan.cache_hit && (
              <div className="text-green-600 dark:text-green-400">Cache hit</div>
            )}
            {activePlan.error_code && (
              <div className="text-destructive">
                {activePlan.error_code}: {activePlan.error_message}
              </div>
            )}
          </div>
        )}

        <Button
          size="sm"
          variant="default"
          className="text-xs"
          onClick={() => void handleExecute()}
          disabled={!isCompleted || busy}
        >
          Execute
        </Button>
      </div>

      {/* Right column: trajectory preview */}
      <div className="min-w-0 flex-1 overflow-hidden">
        <TrajectoryPreview />
      </div>

      {/* Dialogs */}
      <PlannerConfigDialog open={configOpen} onOpenChange={setConfigOpen} />
    </div>
  );
}
