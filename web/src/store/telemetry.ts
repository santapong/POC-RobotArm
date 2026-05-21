/**
 * High-rate telemetry store.
 *
 * Written at ~30 Hz from the /ws/telemetry WebSocket. R3F components must
 * read joint values inside `useFrame` via `getStateRef()` rather than a
 * Zustand selector to avoid per-frame React re-renders tearing the 3D scene.
 */

import { createStore } from "zustand/vanilla";
import { subscribeWithSelector } from "zustand/middleware";
import type { TelemetryFrame, RunStateFrame } from "@/api/types";

interface TelemetryState {
  robot_id: string | null;
  joints_rad: number[];
  tcp_xyz_m: [number, number, number];
  tcp_quat_wxyz: [number, number, number, number];
  run_state: RunStateFrame | null;
  monotonic_s: number;
  applyFrame: (frame: TelemetryFrame) => void;
}

// Vanilla store so R3F can read it without a hook.
const telemetryStore = createStore<TelemetryState>()(
  subscribeWithSelector((set) => ({
    robot_id: null,
    joints_rad: [],
    tcp_xyz_m: [0, 0, 0],
    tcp_quat_wxyz: [1, 0, 0, 0],
    run_state: null,
    monotonic_s: 0,

    applyFrame: (frame) =>
      set({
        robot_id: frame.robot_id,
        joints_rad: frame.joints_rad,
        tcp_xyz_m: frame.tcp_xyz_m,
        tcp_quat_wxyz: frame.tcp_quat_wxyz,
        run_state: frame.run_state,
        monotonic_s: frame.monotonic_s,
      }),
  })),
);

/**
 * Returns a stable reference to the vanilla store's getState function.
 * Use this inside useFrame to avoid React re-renders at 30+ Hz.
 */
export function getStateRef(): TelemetryState {
  return telemetryStore.getState();
}

// Re-export a React-compatible hook for components that do need reactive reads
// (e.g. JogPanel numeric display, StatusBar).
import { useStore } from "zustand";

export function useTelemetryStore<U>(selector: (s: TelemetryState) => U): U {
  return useStore(telemetryStore, selector);
}

// Expose applyFrame at the module level for the WS hook.
export const applyFrame = (frame: TelemetryFrame) =>
  telemetryStore.getState().applyFrame(frame);
