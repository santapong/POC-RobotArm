/**
 * Per-joint jog panel.
 *
 * One row per joint: label + uncontrolled Slider (onValueCommit fires the
 * REST call) + live numeric readback from telemetry (not tied to slider
 * thumb position to avoid the two-way snap anti-pattern).
 *
 * Joint limits fall back to [-π, π] since Phase 1 catalogs expose `dof`
 * but not individual per-axis limit arrays via the REST response.
 */

import { useCallback } from "react";
import { Slider } from "@/components/ui/slider";
import { useCatalogStore } from "@/store/catalog";
import { useTelemetryStore } from "@/store/telemetry";
import { jog } from "@/api/robots";
import { debounce } from "@/lib/debounce";
import { ApiError } from "@/api/client";
import { toast } from "sonner";

const PI = Math.PI;

interface JogPanelProps {
  robotId: string;
}

interface JointRowProps {
  index: number;
  robotId: string;
  jointLabel: string;
  min: number;
  max: number;
}

function JointRow({ index, robotId, jointLabel, min, max }: JointRowProps) {
  // Live position display from telemetry — reactive selector read
  const valueRad = useTelemetryStore((s) => s.joints_rad[index] ?? 0);

  // Debounced jog call — 50 ms as per spec
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const debouncedJog = useCallback(
    debounce((value_rad: number) => {
      void jog(robotId, { joint_index: index, value_rad }).catch((err) => {
        const msg = err instanceof ApiError ? err.detail : String(err);
        toast.error(`Jog failed: ${msg}`);
      });
    }, 50),
    [robotId, index],
  );

  function handleCommit(values: number[]) {
    const v = values[0];
    if (v !== undefined) {
      debouncedJog(v);
    }
  }

  return (
    <div className="flex items-center gap-2 px-3 py-0.5">
      {/* Joint index */}
      <span className="w-8 shrink-0 text-right text-xs text-muted-foreground">
        J{index + 1}
      </span>
      {/* Joint label */}
      <span className="w-20 shrink-0 truncate text-xs">{jointLabel}</span>

      {/* Uncontrolled slider — onValueCommit triggers REST call */}
      <div className="flex-1">
        <Slider
          min={min}
          max={max}
          step={0.001}
          defaultValue={[valueRad]}
          onValueCommit={handleCommit}
          className="h-4"
        />
      </div>

      {/* Live numeric readback from telemetry — does NOT drive slider position */}
      <span className="w-16 shrink-0 text-right font-mono text-xs tabular-nums">
        {valueRad.toFixed(3)}
      </span>
    </div>
  );
}

export function JogPanel({ robotId }: JogPanelProps) {
  const catalogEntries = useCatalogStore((s) => s.entries);
  const telemetryDof = useTelemetryStore((s) => s.joints_rad.length);

  // Try to match the catalog entry by robot id or catalog name prefix
  const entry = catalogEntries.find(
    (e) => e.name === robotId || robotId.startsWith(e.name),
  ) ?? catalogEntries[0];

  const dof = entry?.dof ?? telemetryDof;

  if (dof === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
        No joint data available
      </div>
    );
  }

  // Phase 1: flat [-π, π] range for all joints. Per-axis limits require
  // catalog extension (tracked as follow-up).
  const limits: { min: number; max: number; label: string }[] = Array.from(
    { length: dof },
    (_, i) => ({
      min: -PI,
      max: PI,
      label: `joint_${i + 1}`,
    }),
  );

  return (
    <div className="flex h-full flex-col overflow-y-auto py-1">
      <div className="border-b px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Jog — {robotId}
      </div>
      {limits.map((lim, i) => (
        <JointRow
          key={i}
          index={i}
          robotId={robotId}
          jointLabel={lim.label}
          min={lim.min}
          max={lim.max}
        />
      ))}
    </div>
  );
}
