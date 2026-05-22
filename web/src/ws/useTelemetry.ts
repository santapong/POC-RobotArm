/**
 * WebSocket hook for /ws/telemetry.
 *
 * Pipes incoming JSON frames into `applyFrame` on the telemetry store.
 * After connect, subscribes the server to the first active robot by sending
 * {"subscribe": "robot/<id>"} when the station has robots.
 * Uses exponential backoff reconnect: initial 500 ms, factor 1.5, max 10 s.
 */

import { useEffect } from "react";
import useWebSocket from "react-use-websocket";
import { applyFrame } from "@/store/telemetry";
import { useStationStore } from "@/store/station";
import type { TelemetryFrame } from "@/api/types";

const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/telemetry`
    : "ws://localhost:8000/ws/telemetry";

export function useTelemetry(): void {
  const station = useStationStore((s) => s.station);
  const firstRobotId = station?.robots?.[0]?.name ?? null;

  const { sendJsonMessage, readyState } = useWebSocket(WS_URL, {
    shouldReconnect: () => true,
    reconnectAttempts: Infinity,
    reconnectInterval: (n: number) => Math.min(500 * 1.5 ** n, 10_000),
    onMessage: (event: MessageEvent) => {
      try {
        const frame = JSON.parse(event.data as string) as TelemetryFrame;
        applyFrame(frame);
      } catch {
        // Malformed frame — ignore silently
      }
    },
  });

  // Subscribe to first robot whenever connection opens or the robot changes.
  useEffect(() => {
    if (readyState === 1 /* OPEN */ && firstRobotId !== null) {
      sendJsonMessage({ subscribe: `robot/${firstRobotId}` });
    }
  }, [readyState, firstRobotId, sendJsonMessage]);
}
