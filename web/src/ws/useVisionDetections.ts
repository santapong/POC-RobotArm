/**
 * WebSocket hook for /ws/vision/detections.
 *
 * Pipes incoming `LiveDetectionFrame` JSON into `useVisionStore.applyLiveFrame`.
 * Optionally filters frames by camera name via the server-side subscribe filter.
 * Uses the same exponential backoff as `useTelemetry`:
 *   initial 500 ms, factor 1.5, max 10 s.
 *
 * Mount once in App.tsx after `useTelemetry()` and `useEvents()`.
 */

import { useEffect } from "react";
import useWebSocket from "react-use-websocket";
import { useVisionStore } from "@/store/vision";
import type { LiveDetectionFrame } from "@/api/types";

const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/vision/detections`
    : "ws://localhost:8000/ws/vision/detections";

export function useVisionDetections(subscribeCamera?: string): void {
  const { sendJsonMessage, readyState } = useWebSocket(WS_URL, {
    shouldReconnect: () => true,
    reconnectAttempts: Infinity,
    reconnectInterval: (n: number) => Math.min(500 * 1.5 ** n, 10_000),
    onMessage: (event: MessageEvent) => {
      try {
        const frame = JSON.parse(event.data as string) as LiveDetectionFrame;
        useVisionStore.getState().applyLiveFrame(frame);
      } catch {
        // Malformed frame — ignore silently
      }
    },
  });

  // Send optional camera subscription filter after connection opens.
  useEffect(() => {
    if (readyState === 1 /* OPEN */ && subscribeCamera !== undefined) {
      sendJsonMessage({ subscribe: `camera/${subscribeCamera}` });
    }
  }, [readyState, subscribeCamera, sendJsonMessage]);
}
