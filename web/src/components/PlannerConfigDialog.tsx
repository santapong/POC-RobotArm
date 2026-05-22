/**
 * PlannerConfigDialog — modal for editing advanced planner/optimizer/
 * parameteriser settings.
 *
 * Backed by `usePlanningStore.config`. All edits are local until the user
 * clicks Save, which calls `setConfig(...)` and closes the dialog.
 */

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { usePlanningStore } from "@/store/planning";
import type { OptimizerConfigModel, ParameteriserConfigModel, PlannerConfigModel } from "@/api/types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PlannerConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PlannerConfigDialog({ open, onOpenChange }: PlannerConfigDialogProps): JSX.Element {
  const storeConfig = usePlanningStore((s) => s.config);
  const setConfig = usePlanningStore((s) => s.setConfig);

  // Local draft state — committed on Save.
  const [smoothingIterations, setSmoothingIterations] = useState(
    storeConfig.smoothing_iterations,
  );
  const [rangeRad, setRangeRad] = useState(storeConfig.range_rad);
  const [clearanceM, setClearanceM] = useState(storeConfig.clearance_m);
  const [optimizerEnabled, setOptimizerEnabled] = useState(
    storeConfig.optimizer.enabled,
  );
  const [optimizerMaxIter, setOptimizerMaxIter] = useState(
    storeConfig.optimizer.max_iterations,
  );
  const [qdScale, setQdScale] = useState(storeConfig.parameteriser.qd_scale);
  const [qddScale, setQddScale] = useState(storeConfig.parameteriser.qdd_scale);
  const [gridPoints, setGridPoints] = useState(storeConfig.parameteriser.grid_points);

  // Re-sync draft whenever the dialog opens (store may have changed).
  useEffect(() => {
    if (open) {
      setSmoothingIterations(storeConfig.smoothing_iterations);
      setRangeRad(storeConfig.range_rad);
      setClearanceM(storeConfig.clearance_m);
      setOptimizerEnabled(storeConfig.optimizer.enabled);
      setOptimizerMaxIter(storeConfig.optimizer.max_iterations);
      setQdScale(storeConfig.parameteriser.qd_scale);
      setQddScale(storeConfig.parameteriser.qdd_scale);
      setGridPoints(storeConfig.parameteriser.grid_points);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function handleSave() {
    const plannerPatch: Partial<PlannerConfigModel> = {
      smoothing_iterations: smoothingIterations,
      range_rad: rangeRad,
      clearance_m: clearanceM,
    };
    const optimizerPatch: OptimizerConfigModel = {
      ...storeConfig.optimizer,
      enabled: optimizerEnabled,
      max_iterations: optimizerMaxIter,
    };
    const parameteriserPatch: ParameteriserConfigModel = {
      ...storeConfig.parameteriser,
      qd_scale: qdScale,
      qdd_scale: qddScale,
      grid_points: gridPoints,
    };
    setConfig({
      ...plannerPatch,
      optimizer: optimizerPatch,
      parameteriser: parameteriserPatch,
    });
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Planner configuration</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2 text-sm">
          {/* Planner section */}
          <fieldset className="space-y-3">
            <legend className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Planner
            </legend>

            <div className="flex items-center justify-between gap-4">
              <label className="shrink-0">Smoothing iterations</label>
              <input
                type="number"
                className="w-20 rounded border bg-background px-2 py-0.5 text-right text-xs"
                value={smoothingIterations}
                min={0}
                step={1}
                onChange={(e) =>
                  setSmoothingIterations(Math.max(0, parseInt(e.target.value, 10) || 0))
                }
              />
            </div>

            <div className="space-y-1">
              <div className="flex justify-between">
                <label>Range (rad)</label>
                <span className="text-xs text-muted-foreground">{rangeRad.toFixed(2)}</span>
              </div>
              <Slider
                min={0.05}
                max={2.0}
                step={0.05}
                value={[rangeRad]}
                onValueChange={([v]) => setRangeRad(v)}
              />
            </div>

            <div className="flex items-center justify-between gap-4">
              <label className="shrink-0">Clearance (m)</label>
              <input
                type="number"
                className="w-24 rounded border bg-background px-2 py-0.5 text-right text-xs"
                value={clearanceM}
                min={0}
                step={0.001}
                onChange={(e) =>
                  setClearanceM(Math.max(0, parseFloat(e.target.value) || 0))
                }
              />
            </div>
          </fieldset>

          {/* Optimizer section */}
          <fieldset className="space-y-3">
            <legend className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Optimizer
            </legend>

            <div className="flex items-center gap-2">
              <input
                id="optimizer-enabled"
                type="checkbox"
                checked={optimizerEnabled}
                onChange={(e) => setOptimizerEnabled(e.target.checked)}
                className="h-3.5 w-3.5"
              />
              <label htmlFor="optimizer-enabled">Enabled</label>
            </div>

            <div className="flex items-center justify-between gap-4">
              <label className="shrink-0">Max iterations</label>
              <input
                type="number"
                className="w-20 rounded border bg-background px-2 py-0.5 text-right text-xs"
                value={optimizerMaxIter}
                min={1}
                step={1}
                disabled={!optimizerEnabled}
                onChange={(e) =>
                  setOptimizerMaxIter(Math.max(1, parseInt(e.target.value, 10) || 1))
                }
              />
            </div>
          </fieldset>

          {/* Parameteriser section */}
          <fieldset className="space-y-3">
            <legend className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Parameteriser
            </legend>

            <div className="space-y-1">
              <div className="flex justify-between">
                <label>Velocity scale</label>
                <span className="text-xs text-muted-foreground">{qdScale.toFixed(2)}</span>
              </div>
              <Slider
                min={0.1}
                max={1.0}
                step={0.05}
                value={[qdScale]}
                onValueChange={([v]) => setQdScale(v)}
              />
            </div>

            <div className="space-y-1">
              <div className="flex justify-between">
                <label>Acceleration scale</label>
                <span className="text-xs text-muted-foreground">{qddScale.toFixed(2)}</span>
              </div>
              <Slider
                min={0.1}
                max={1.0}
                step={0.05}
                value={[qddScale]}
                onValueChange={([v]) => setQddScale(v)}
              />
            </div>

            <div className="flex items-center justify-between gap-4">
              <label className="shrink-0">Grid points</label>
              <input
                type="number"
                className="w-20 rounded border bg-background px-2 py-0.5 text-right text-xs"
                value={gridPoints}
                min={16}
                step={1}
                onChange={(e) =>
                  setGridPoints(Math.max(16, parseInt(e.target.value, 10) || 16))
                }
              />
            </div>
          </fieldset>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
