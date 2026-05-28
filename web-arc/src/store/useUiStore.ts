// UI store (Zustand). Holds non-project state: the current screen, the
// selected robot id, display tweaks (accent / density / 3D toggles / arm count),
// whether the command console is open, and the trajectory that CAM / PROGRAM
// hand off to the PATH editor. Replaces the prototype's scattered local
// useState + window.GENERATED_TRAJECTORY global.

import { create } from "zustand";
import type { Trajectory } from "@/types";

export const SCREENS = [
  "fleet", "robot", "teleop", "cam", "path", "program",
  "import", "tasks", "scene", "analytics", "logs", "settings",
] as const;
export type Screen = typeof SCREENS[number];

export interface Tweaks {
  accent: string;
  density: "dense" | "comfy";
  showWorkspace: boolean;
  autoRotate3D: boolean;
  armCount: number;
}

interface UiState {
  screen: Screen;
  selectedId: string;
  tweaks: Tweaks;
  consoleOpen: boolean;
  pendingTrajectory: Trajectory | null;
  setScreen: (s: Screen) => void;
  setSelectedId: (id: string) => void;
  setTweak: <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => void;
  toggleConsole: () => void;
  setConsoleOpen: (open: boolean) => void;
  // Hand a compiled trajectory to the PATH editor (replaces
  // window.GENERATED_TRAJECTORY).
  openInPath: (t: Trajectory) => void;
  clearPending: () => void;
}

const TWEAK_DEFAULTS: Tweaks = {
  accent: "#4ade80",
  density: "dense",
  showWorkspace: true,
  autoRotate3D: false,
  armCount: 30,
};

export const useUiStore = create<UiState>((set) => ({
  screen: "fleet",
  selectedId: "ARM-003",
  tweaks: TWEAK_DEFAULTS,
  consoleOpen: false,
  pendingTrajectory: null,
  setScreen: (screen) => set({ screen }),
  setSelectedId: (selectedId) => set({ selectedId }),
  setTweak: (k, v) => set((s) => ({ tweaks: { ...s.tweaks, [k]: v } })),
  toggleConsole: () => set((s) => ({ consoleOpen: !s.consoleOpen })),
  setConsoleOpen: (consoleOpen) => set({ consoleOpen }),
  openInPath: (t) => set({ pendingTrajectory: t, screen: "path" }),
  clearPending: () => set({ pendingTrajectory: null }),
}));
