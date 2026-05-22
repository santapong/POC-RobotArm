/**
 * Application root — wires up WS hooks, catalog preload, and the layout shell.
 *
 * Mounts the Toaster (sonner) and all dialog components so they are always
 * available regardless of which panel is active.
 */

import { useEffect } from "react";
import { Toaster } from "@/components/ui/sonner";
import { Layout } from "./components/Layout";
import { FileDialogs } from "./components/FileDialogs";
import { AboutDialog } from "./components/AboutDialog";
import { useTelemetry } from "./ws/useTelemetry";
import { useEvents } from "./ws/useEvents";
import { useVisionDetections } from "./ws/useVisionDetections";
import { useCatalogStore } from "./store/catalog";
import { useStationStore } from "./store/station";
import { getCatalog } from "./api/robots";
import { getStation } from "./api/station";

export default function App() {
  // Activate WebSocket hooks at root level so they persist for the app lifetime
  useTelemetry();
  useEvents();
  useVisionDetections();

  const setCatalog = useCatalogStore((s) => s.setCatalog);
  const setStation = useStationStore((s) => s.setStation);

  // Preload catalog and initial station on mount
  useEffect(() => {
    void getCatalog()
      .then(setCatalog)
      .catch(() => {
        // Server may not be running yet; WS reconnect handles retry implicitly
      });

    void getStation()
      .then(setStation)
      .catch(() => undefined);
  }, [setCatalog, setStation]);

  return (
    <div className="h-full w-full">
      <Layout />
      <FileDialogs />
      <AboutDialog />
      <Toaster />
    </div>
  );
}
