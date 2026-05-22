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
import { usePlanningStore } from "@/store/planning";
import type { PlanProgressFrame } from "@/api/types";

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
        usePlanningStore.getState().applyProgress(frame);
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
