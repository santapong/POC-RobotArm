/**
 * WebSocket hook for /ws/events.
 *
 * Pipes server-push events into `useUIStore.pushEvent` and also fires
 * toast notifications via sonner. Reconnects with the same exponential
 * backoff as useTelemetry.
 */

import useWebSocket from "react-use-websocket";
import { toast } from "sonner";
import { useUIStore } from "@/store/ui";
import { useStationStore } from "@/store/station";
import { getStation } from "@/api/station";
import type { WsEvent, StationModel } from "@/api/types";

const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/events`
    : "ws://localhost:8000/ws/events";

export function useEvents(): void {
  const pushEvent = useUIStore((s) => s.pushEvent);
  const setStation = useStationStore((s) => s.setStation);

  useWebSocket(WS_URL, {
    shouldReconnect: () => true,
    reconnectAttempts: Infinity,
    reconnectInterval: (n: number) => Math.min(500 * 1.5 ** n, 10_000),
    onMessage: (event: MessageEvent) => {
      let wsEvent: WsEvent;
      try {
        wsEvent = JSON.parse(event.data as string) as WsEvent;
      } catch {
        return;
      }

      pushEvent(wsEvent);
      handleEvent(wsEvent, setStation);
    },
  });
}

function handleEvent(
  event: WsEvent,
  setStation: (s: StationModel) => void,
): void {
  switch (event.type) {
    case "robot_spawned": {
      const id = event.payload["id"] as string | undefined;
      toast.info(`Robot spawned: ${id ?? "unknown"}`);
      // Refresh station after spawn
      void getStation().then(setStation).catch(() => undefined);
      break;
    }
    case "robot_removed": {
      const id = event.payload["id"] as string | undefined;
      toast.info(`Robot removed: ${id ?? "unknown"}`);
      void getStation().then(setStation).catch(() => undefined);
      break;
    }
    case "program_emitted": {
      const vendor = event.payload["vendor"] as string | undefined;
      toast.info(`Code emitted: ${vendor ?? ""}`);
      break;
    }
    case "import_completed": {
      const filename = event.payload["filename"] as string | undefined;
      toast.info(`Import complete: ${filename ?? ""}`);
      void getStation().then(setStation).catch(() => undefined);
      break;
    }
    case "run_started": {
      toast.info("Program run started");
      break;
    }
    case "run_completed": {
      toast.info("Program run completed");
      break;
    }
    case "run_failed": {
      const err = event.payload["error"] as string | undefined;
      toast.error(`Run failed: ${err ?? "unknown error"}`);
      break;
    }
    case "error": {
      const detail = event.payload["detail"] as string | undefined;
      toast.error(detail ?? "Server error");
      break;
    }
    default:
      break;
  }
}
