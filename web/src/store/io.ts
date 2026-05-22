/**
 * I/O state store (Phase 4).
 *
 * Holds connection status records, per-connection signal maps, live value
 * snapshots, and a ring-buffer of recent WS events.
 *
 * Notes:
 * - The `connections` and `signalMap` slices are persisted under
 *   `poc-io-config-v1` so that operator-configured connections survive a
 *   browser refresh.
 * - `lastValues` uses last-writer-wins: any incoming WS event that carries a
 *   value overwrites the previous entry for that "<conn>.<signal>" key.
 * - `recentEvents` is capped at 200 entries; older events are dropped from the
 *   front via `slice(-200)`.
 * - `selectedConnection` is session-only and is not persisted.
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { persist, createJSONStorage } from "zustand/middleware";
import type {
  IoConnectionStatusModel,
  SignalSpecModel,
  IoValueSnapshotModel,
  IoEventModel,
} from "@/api/types";

// ---------------------------------------------------------------------------
// Shape
// ---------------------------------------------------------------------------

export interface IoStoreState {
  connections: Record<string, IoConnectionStatusModel>;
  signalMap: Record<string, SignalSpecModel[]>;
  lastValues: Record<string, IoValueSnapshotModel>;
  recentEvents: IoEventModel[];
  selectedConnection: string | null;

  setConnections: (next: Record<string, IoConnectionStatusModel>) => void;
  upsertConnection: (status: IoConnectionStatusModel) => void;
  removeConnection: (name: string) => void;
  setSignalMap: (conn: string, signals: SignalSpecModel[]) => void;
  applyEvent: (event: IoEventModel) => void;
  selectConnection: (name: string | null) => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useIoStore = create<IoStoreState>()(
  subscribeWithSelector(
    persist(
      (set) => ({
        connections: {},
        signalMap: {},
        lastValues: {},
        recentEvents: [],
        selectedConnection: null,

        setConnections: (next) =>
          set(() => ({
            connections: next,
          })),

        upsertConnection: (status) =>
          set((state) => ({
            connections: { ...state.connections, [status.name]: status },
          })),

        removeConnection: (name) =>
          set((state) => {
            const nextConns = { ...state.connections };
            delete nextConns[name];
            const nextMap = { ...state.signalMap };
            delete nextMap[name];
            const nextValues: Record<string, IoValueSnapshotModel> = {};
            for (const [key, snap] of Object.entries(state.lastValues)) {
              if (snap.connection !== name) {
                nextValues[key] = snap;
              }
            }
            return {
              connections: nextConns,
              signalMap: nextMap,
              lastValues: nextValues,
              selectedConnection:
                state.selectedConnection === name
                  ? null
                  : state.selectedConnection,
            };
          }),

        setSignalMap: (conn, signals) =>
          set((state) => ({
            signalMap: { ...state.signalMap, [conn]: signals },
          })),

        applyEvent: (event) =>
          set((state) => {
            const nextValues = { ...state.lastValues };

            // Update lastValues when the event carries a value.
            if (
              event.signal !== null &&
              event.value !== null &&
              event.type === "value_changed"
            ) {
              const key = `${event.connection}.${event.signal}`;
              const existing = nextValues[key];
              // Derive kind from existing snapshot or fall back to a neutral default.
              nextValues[key] = {
                connection: event.connection,
                signal: event.signal,
                kind: existing?.kind ?? "digital_in",
                value: event.value,
                monotonic_s: event.monotonic_s,
              };
            }

            // Update connection status when the event carries a status change.
            let nextConns = state.connections;
            if (event.type === "connection_changed" && event.status !== null) {
              const existing = state.connections[event.connection];
              if (existing !== undefined) {
                nextConns = {
                  ...nextConns,
                  [event.connection]: {
                    ...existing,
                    status: event.status,
                    last_error: event.error_message ?? null,
                  },
                };
              }
            }

            // Surface error events in the connection card's last_error field.
            if (event.type === "error") {
              const existing = nextConns[event.connection];
              if (existing !== undefined) {
                nextConns = {
                  ...nextConns,
                  [event.connection]: {
                    ...existing,
                    last_error: event.error_message ?? null,
                  },
                };
              }
            }

            // Also update write_ack into lastValues.
            if (
              event.type === "write_ack" &&
              event.signal !== null &&
              event.value !== null
            ) {
              const key = `${event.connection}.${event.signal}`;
              const existing = nextValues[key];
              nextValues[key] = {
                connection: event.connection,
                signal: event.signal,
                kind: existing?.kind ?? "digital_out",
                value: event.value,
                monotonic_s: event.monotonic_s,
              };
            }

            return {
              connections: nextConns,
              lastValues: nextValues,
              // Append and cap at 200 — older events dropped from front.
              recentEvents: [...state.recentEvents, event].slice(-200),
            };
          }),

        selectConnection: (name) => set({ selectedConnection: name }),

        reset: () =>
          set({
            connections: {},
            signalMap: {},
            lastValues: {},
            recentEvents: [],
            selectedConnection: null,
          }),
      }),
      {
        name: "poc-io-config-v1",
        storage: createJSONStorage(() => localStorage),
        // Persist only operator-configured data; transient runtime state excluded.
        partialize: (state) => ({
          connections: state.connections,
          signalMap: state.signalMap,
        }),
      },
    ),
  ),
);
