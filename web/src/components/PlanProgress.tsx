/**
 * PlanProgress — compact stage + percent-bar widget.
 *
 * Subscribes to the active plan's stage and progress from `usePlanningStore`.
 * Renders nothing when no plan is active.
 */

import { usePlanningStore } from "@/store/planning";

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  ik: "Inverse kinematics",
  sampling: "Sampling",
  optimizing: "Optimizing",
  parameterising: "Parameterising",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

// Stage-based heuristic is intentional: the server heartbeat publishes
// percent=0.5 for every in-progress plan regardless of true progress,
// so using frame.percent would cause the bar to jump back on each frame.
const STAGE_PERCENT: Record<string, number> = {
  queued: 0,
  ik: 10,
  sampling: 30,
  optimizing: 70,
  parameterising: 85,
  completed: 100,
  failed: 100,
  cancelled: 100,
};

export function PlanProgress(): JSX.Element | null {
  const activePlanId = usePlanningStore((s) => s.activePlanId);
  const plans = usePlanningStore((s) => s.plans);

  if (activePlanId === null) return null;

  const record = plans[activePlanId];
  if (!record) return null;

  const pct = STAGE_PERCENT[record.stage] ?? 0;
  const label = STAGE_LABELS[record.stage] ?? record.stage;

  const isTerminal =
    record.stage === "completed" ||
    record.stage === "failed" ||
    record.stage === "cancelled";

  const barColor = record.stage === "failed" || record.stage === "cancelled"
    ? "bg-destructive"
    : record.stage === "completed"
    ? "bg-green-500"
    : "bg-primary";

  return (
    <div className="mt-1 space-y-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        {!isTerminal && <span>{pct}%</span>}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-primary/20">
        <div
          className={`h-full transition-[width] duration-300 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
