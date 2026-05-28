// App shell + screen router. All 11 screens + console are now live.

import { useEffect, useMemo, useState } from "react";
import type { Alert, Robot } from "@/types";
import { ALERTS_INIT, buildFleet } from "@/lib/fleet";
import { useGlobalShortcuts } from "@/hooks/useKeyboard";
import { useUiStore } from "@/store/useUiStore";
import { TopBar } from "@/components/shell/TopBar";
// Left sidenav removed — navigation is now driven by the ROBOT page's
// right-edge toolbox rail (and the HOME button in the topbar to return).
import { BottomBar } from "@/components/shell/BottomBar";
import { TweaksPanel } from "@/components/shell/TweaksPanel";
import { CommandConsole } from "@/components/console/CommandConsole";
import { FleetScreen } from "@/screens/FleetScreen";
// RobotDetailScreen removed from routing — INSPECT now lives inside the
// ROBOT page's toolbox rail as a flyout panel, no longer a separate screen.
import { TeleopScreen } from "@/screens/TeleopScreen";
import { CAMScreen } from "@/screens/CAMScreen";
import { PathScreen } from "@/screens/PathScreen";
import { ProgramScreen } from "@/screens/ProgramScreen";
import { ImportScreen } from "@/screens/ImportScreen";
import { TasksScreen } from "@/screens/TasksScreen";
import { SceneScreen } from "@/screens/SceneScreen";
import { AnalyticsScreen } from "@/screens/AnalyticsScreen";
import { LogsScreen } from "@/screens/LogsScreen";
import { SettingsScreen } from "@/screens/SettingsScreen";

export default function App() {
  useGlobalShortcuts();

  const screen = useUiStore(s => s.screen);
  const selectedId = useUiStore(s => s.selectedId);
  const accent = useUiStore(s => s.tweaks.accent);
  const density = useUiStore(s => s.tweaks.density);
  const armCount = useUiStore(s => s.tweaks.armCount);
  const setScreen = useUiStore(s => s.setScreen);

  const [fleet, setFleet] = useState<Robot[]>(() => buildFleet(armCount));
  const [alerts] = useState<Alert[]>(ALERTS_INIT);

  useEffect(() => { setFleet(buildFleet(armCount)); }, [armCount]);

  // jitter the live counters
  useEffect(() => {
    const id = setInterval(() => {
      setFleet(f => f.map(r => {
        if (r.status === "OFFLINE") return r;
        const cpu = Math.max(15, Math.min(95, r.cpu + (Math.random() - 0.5) * 4));
        const temp = Math.max(34, Math.min(72, r.temp + (Math.random() - 0.5) * 1.2));
        const lat = r.latencyMs != null ? Math.max(2, r.latencyMs + (Math.random() - 0.5) * 3) : null;
        return { ...r, cpu: Math.round(cpu), temp: Math.round(temp), latencyMs: lat != null ? Math.round(lat) : null };
      }));
    }, 1500);
    return () => clearInterval(id);
  }, []);

  const selected = useMemo(() => fleet.find(r => r.id === selectedId), [fleet, selectedId]);

  return (
    <div
      className="app"
      data-density={density}
      style={{ "--ok": accent } as React.CSSProperties}
    >
      <TopBar fleet={fleet} alerts={alerts} selected={selected} onAck={() => setScreen("logs")} />
      <main className="main">
        {screen === "fleet"     && <FleetScreen fleet={fleet} alerts={alerts} />}
        {screen === "robot"     && <FleetScreen fleet={fleet} alerts={alerts} />}
        {screen === "teleop"    && <TeleopScreen robot={selected} />}
        {screen === "cam"       && <CAMScreen robot={selected} />}
        {screen === "path"      && <PathScreen robot={selected} />}
        {screen === "program"   && <ProgramScreen robot={selected} />}
        {screen === "import"    && <ImportScreen />}
        {screen === "tasks"     && <TasksScreen fleet={fleet} />}
        {screen === "scene"     && <SceneScreen robot={selected} />}
        {screen === "analytics" && <AnalyticsScreen fleet={fleet} />}
        {screen === "logs"      && <LogsScreen alerts={alerts} />}
        {screen === "settings"  && <SettingsScreen robot={selected} />}
      </main>
      <BottomBar fleet={fleet} />
      <TweaksPanel />
      <CommandConsole />
    </div>
  );
}
