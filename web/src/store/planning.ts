/**
 * Planning state store.
 *
 * Holds plan records, active plan selection, trajectory preview state, and
 * planner/optimizer/parameteriser configuration. The `config` slice is
 * persisted to localStorage under key `poc-planning-config-v1`; plan records
 * are session-only.
 *
 * Uses `subscribeWithSelector` middleware (same as telemetry.ts) so that
 * `TrajectoryPreview` can subscribe to `previewPlaying` changes.
 *
 * Notes:
 * - `persist` partializes to `config` only; `plans` and preview state are
 *   never written to localStorage.
 * - `isPreviewActive` is a derived getter, not reactive state.
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { persist, createJSONStorage } from "zustand/middleware";
import type {
  OptimizerConfigModel,
  ParameteriserConfigModel,
  PlannerConfigModel,
  PlanProgressFrame,
  PlanRunRecord,
} from "@/api/types";

// ---------------------------------------------------------------------------
// Shape
// ---------------------------------------------------------------------------

type PlannerFullConfig = PlannerConfigModel & {
  optimizer: OptimizerConfigModel;
  parameteriser: ParameteriserConfigModel;
};

interface PlanningState {
  plans: Record<string, PlanRunRecord>;
  activePlanId: string | null;
  previewTimeS: number;
  previewPlaying: boolean;
  previewSpeed: number;
  config: PlannerFullConfig;
  isPreviewActive: () => boolean;

  setPlan: (record: PlanRunRecord) => void;
  removePlan: (planId: string) => void;
  setActive: (planId: string | null) => void;
  setPreviewTime: (t: number) => void;
  setPreviewPlaying: (p: boolean) => void;
  setPreviewSpeed: (s: number) => void;
  setConfig: (next: Partial<PlanningState["config"]>) => void;
  applyProgress: (frame: PlanProgressFrame) => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Default config values mirror Pydantic model defaults
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG: PlannerFullConfig = {
  kind: "rrt_star",
  timeout_s: 5.0,
  smoothing_iterations: 50,
  range_rad: 0.5,
  clearance_m: 0.005,
  qdd_max_rad_s2_default: null,
  optimizer: {
    enabled: false,
    max_iterations: 100,
    min_distance_m: 0.005,
    spline_degree: 5,
  },
  parameteriser: {
    qd_scale: 1.0,
    qdd_scale: 1.0,
    grid_points: 200,
  },
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const usePlanningStore = create<PlanningState>()(
  subscribeWithSelector(
    persist(
      (set, get) => ({
        plans: {},
        activePlanId: null,
        previewTimeS: 0,
        previewPlaying: false,
        previewSpeed: 1.0,
        config: { ...DEFAULT_CONFIG },

        isPreviewActive: () => {
          const s = get();
          return s.previewPlaying && s.activePlanId !== null;
        },

        setPlan: (record) =>
          set((state) => ({
            plans: { ...state.plans, [record.plan_id]: record },
          })),

        removePlan: (planId) =>
          set((state) => {
            const next = { ...state.plans };
            delete next[planId];
            return { plans: next };
          }),

        setActive: (planId) =>
          set({ activePlanId: planId, previewTimeS: 0, previewPlaying: false }),

        setPreviewTime: (t) => set({ previewTimeS: t }),

        setPreviewPlaying: (p) => set({ previewPlaying: p }),

        setPreviewSpeed: (s) => set({ previewSpeed: s }),

        setConfig: (next) =>
          set((state) => ({ config: { ...state.config, ...next } })),

        applyProgress: (frame) =>
          set((state) => {
            const existing = state.plans[frame.plan_id];
            if (!existing) return state;
            return {
              plans: {
                ...state.plans,
                [frame.plan_id]: {
                  ...existing,
                  stage: frame.stage,
                },
              },
            };
          }),

        reset: () =>
          set({
            plans: {},
            activePlanId: null,
            previewTimeS: 0,
            previewPlaying: false,
            previewSpeed: 1.0,
          }),
      }),
      {
        name: "poc-planning-config-v1",
        storage: createJSONStorage(() => localStorage),
        // Only persist the config slice, not transient plan records or preview state.
        partialize: (state) => ({ config: state.config }),
      },
    ),
  ),
);
