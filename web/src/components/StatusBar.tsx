/**
 * Status bar — mirrors the desktop's status bar showing station name and file.
 * Also displays any in-flight operation banner from useUIStore.
 */

import { useStationStore } from "@/store/station";
import { useUIStore } from "@/store/ui";
import { useTelemetryStore } from "@/store/telemetry";

export function StatusBar() {
  const station = useStationStore((s) => s.station);
  const banner = useUIStore((s) => s.operationBanner);
  const robotId = useTelemetryStore((s) => s.robot_id);
  const running = useTelemetryStore((s) => s.run_state?.active ?? false);

  const stationName = station?.name ?? "—";

  return (
    <div className="flex h-full items-center gap-4 px-2 text-xs text-muted-foreground">
      <span>
        Station: <span className="font-medium text-foreground">{stationName}</span>
      </span>
      {robotId !== null && (
        <span>
          Robot: <span className="font-medium text-foreground">{robotId}</span>
        </span>
      )}
      {running && (
        <span className="text-green-500 font-medium">Program running…</span>
      )}
      {banner.length > 0 && (
        <span className="ml-auto text-yellow-500">{banner}</span>
      )}
    </div>
  );
}
