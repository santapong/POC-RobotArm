/**
 * Root layout grid for the RobotArm web app.
 *
 * Arranges the application panels in a desktop-style grid:
 *   row 0: Toolbar (3rem)
 *   row 1: Outliner | Viewport | Inspector (1fr)
 *   row 2: CodePanel (14rem)
 *   row 3: JogPanel (8rem)
 *
 * Under md breakpoint, side panels collapse to icons. The grid
 * columns are [16rem, 1fr, 18rem].
 */

import { Outliner } from "./Outliner";
import { Viewport } from "./Viewport";
import { Inspector } from "./Inspector";
import { BottomPanel } from "./BottomPanel";
import { JogPanel } from "./JogPanel";
import { Toolbar } from "./Toolbar";
import { StatusBar } from "./StatusBar";
import { useUIStore } from "@/store/ui";
import { useStationStore } from "@/store/station";

export function Layout() {
  const selectedEntityKind = useUIStore((s) => s.selectedEntityKind);
  const selectedEntityName = useUIStore((s) => s.selectedEntityName);
  const station = useStationStore((s) => s.station);

  // Determine which robot is selected for the JogPanel
  const selectedRobotId =
    selectedEntityKind === "robot" && selectedEntityName !== null
      ? selectedEntityName
      : (station?.robots?.[0]?.name ?? null);

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      {/* Toolbar row */}
      <div className="h-12 shrink-0 border-b">
        <Toolbar />
      </div>

      {/* Main content: three-column grid */}
      <div className="grid min-h-0 flex-1 grid-cols-[16rem_1fr_18rem]">
        {/* Outliner */}
        <div className="overflow-hidden border-r">
          <Outliner />
        </div>

        {/* Viewport */}
        <div className="overflow-hidden">
          <Viewport />
        </div>

        {/* Inspector */}
        <div className="overflow-hidden border-l">
          <Inspector />
        </div>
      </div>

      {/* Bottom panel (Code + Vision tabs) */}
      <BottomPanel />

      {/* Jog panel */}
      <div className="h-32 shrink-0 border-t">
        {selectedRobotId !== null ? (
          <JogPanel robotId={selectedRobotId} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Spawn a robot to enable jogging
          </div>
        )}
      </div>

      {/* Status bar */}
      <div className="h-6 shrink-0 border-t">
        <StatusBar />
      </div>
    </div>
  );
}
