/**
 * WebSocket hook for /ws/planning/progress.
 *
 * Pipes incoming `PlanProgressFrame` JSON into
 * `usePlanningStore.getState().applyProgress`. Sends a subscribe filter
 * `{"subscribe": "plan/<activePlanId>"}` whenever `activePlanId` changes
 * so the server fans out only the relevant plan's events.
 *
 * Uses the same exponential backoff as `useVisionDetections`:
 *   initial 500 ms, factor 1.5, max 10 s.
 *
 * Mount once in App.tsx after `useVisionDetections()`.
 */

import { useEffect } from "react";
import useWebSocket from "react-use-websocket";
import { toast } from "sonner";
import { getPlan } from "@/api/planning";
import { usePlanningStore } from "@/store/planning";
import type { PlanProgressFrame } from "@/api/types";

const TERMINAL_STAGES = new Set<PlanProgressFrame["stage"]>([
  "completed",
  "failed",
  "cancelled",
]);

const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/planning/progress`
    : "ws://localhost:8000/ws/planning/progress";

export function usePlanProgress(): void {
  const activePlanId = usePlanningStore((s) => s.activePlanId);

  const { sendJsonMessage, readyState } = useWebSocket(WS_URL, {
    shouldReconnect: () => true,
    reconnectAttempts: Infinity,
    reconnectInterval: (n: number) => Math.min(500 * 1.5 ** n, 10_000),
    onMessage: (event: MessageEvent) => {
      try {
        const frame = JSON.parse(event.data as string) as PlanProgressFrame;
        // Read the existing stage before mutating so we can detect the
        // first time this plan transitions into a terminal stage.
        const prevStage =
          usePlanningStore.getState().plans[frame.plan_id]?.stage ?? null;
        usePlanningStore.getState().applyProgress(frame);
        // Fire a single REST fetch when the plan first enters a terminal stage.
        // prevStage being non-terminal (or absent) guards against re-firing on
        // subsequent heartbeat frames that repeat the terminal stage.
        if (
          TERMINAL_STAGES.has(frame.stage) &&
          (prevStage === null || !TERMINAL_STAGES.has(prevStage))
        ) {
          getPlan(frame.plan_id).then(
            (record) => {
              usePlanningStore.getState().setPlan(record);
            },
            (err: unknown) => {
              toast.error(
                `Failed to fetch plan result: ${err instanceof Error ? err.message : String(err)}`,
              );
              // Optimistic fallback already applied by applyProgress; no
              // further action needed — the status was synced synchronously.
            },
          );
        }
      } catch {
        // Malformed frame — ignore silently
      }
    },
  });

  // Resend subscribe filter whenever activePlanId or connection state changes.
  useEffect(() => {
    if (readyState === 1 /* OPEN */ && activePlanId !== null) {
      sendJsonMessage({ subscribe: `plan/${activePlanId}` });
    }
  }, [readyState, activePlanId, sendJsonMessage]);
}
