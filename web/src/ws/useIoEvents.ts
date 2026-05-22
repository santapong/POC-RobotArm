/**
 * WebSocket hook for /ws/io/stream.
 *
 * Pipes incoming `IoEventModel` JSON into `useIoStore.getState().applyEvent`.
 * Sends `{"subscribe": "connection/<name>"}` whenever `selectedConnection`
 * changes to scope the server fan-out to that connection's events. Sending
 * `{"subscribe": ""}` clears the filter.
 *
 * Uses the same exponential backoff as `usePlanProgress`:
 *   initial 500 ms, factor 1.5, max 10 s.
 *
 * Mount once in App.tsx after `usePlanProgress()`.
 */

import { useEffect } from "react";
import useWebSocket from "react-use-websocket";
import { useIoStore } from "@/store/io";
import type { IoEventModel } from "@/api/types";

const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/io/stream`
    : "ws://localhost:8000/ws/io/stream";

export function useIoEvents(): void {
  const selectedConnection = useIoStore((s) => s.selectedConnection);

  const { sendJsonMessage, readyState } = useWebSocket(WS_URL, {
    shouldReconnect: () => true,
    reconnectAttempts: Infinity,
    reconnectInterval: (n: number) => Math.min(500 * 1.5 ** n, 10_000),
    onMessage: (event: MessageEvent) => {
      try {
        const ioEvent = JSON.parse(event.data as string) as IoEventModel;
        useIoStore.getState().applyEvent(ioEvent);
      } catch {
        // Malformed frame — ignore silently
      }
    },
  });

  // Resend subscribe filter whenever selectedConnection or connection state changes.
  useEffect(() => {
    if (readyState !== 1 /* OPEN */) return;
    const filter =
      selectedConnection !== null ? `connection/${selectedConnection}` : "";
    sendJsonMessage({ subscribe: filter });
  }, [readyState, selectedConnection, sendJsonMessage]);
}
