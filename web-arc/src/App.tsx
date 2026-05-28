// App shell: top bar / side nav / main / bottom bar / tweaks. The fleet
// breathes (cpu/temp/latency jitter every 1.5 s), the 3D and screens land
// in P3 and P4. Each screen is rendered as a "porting" placeholder for now;
// flipping to the real components is a one-line swap per screen.

import { useEffect, useMemo, useState } from "react";
import type { Alert, Robot } from "@/types";
import { ALERTS_INIT, buildFleet } from "@/lib/fleet";
import { useGlobalShortcuts } from "@/hooks/useKeyboard";
import { useUiStore, type Screen } from "@/store/useUiStore";
import { Panel } from "@/components/common";
import { TopBar } from "@/components/shell/TopBar";
import { SideNav } from "@/components/shell/SideNav";
import { BottomBar } from "@/components/shell/BottomBar";
import { TweaksPanel } from "@/components/shell/TweaksPanel";
import { NAV } from "@/components/shell/nav";

const SCREEN_BLURB: Record<Screen, string> = {
  fleet:     "Factory cell grid + selected-robot rail (P4).",
  robot:     "Robot detail: TCP pose, joint table, I/O bits (P4).",
  teleop:    "Cartesian / joint jog pendant + 3D arm (P3 + P4).",
  cam:       "Surface-pick path generation (P3 + P4).",
  path:      "Trajectory editor + playback (P3 + P4).",
  program:   "Operation tree hub, post output, save/load (P4).",
  import:    "Asset library + program editor (P4).",
  tasks:     "Mission queue + Gantt (P4).",
  scene:     "Multi-arm 3D scene (P3 + P4).",
  analytics: "KPIs, throughput, heatmaps (P4).",
  logs:      "Streaming alert log + diagnostics (P4).",
  settings:  "PID, safety limits, sensors, OTA (P4).",
};

export default function App() {
  useGlobalShortcuts();

  const selectedId = useUiStore(s => s.selectedId);
  const accent = useUiStore(s => s.tweaks.accent);
  const density = useUiStore(s => s.tweaks.density);
  const armCount = useUiStore(s => s.tweaks.armCount);
  const setScreen = useUiStore(s => s.setScreen);

  const [fleet, setFleet] = useState<Robot[]>(() => buildFleet(armCount));
  const [alerts] = useState<Alert[]>(ALERTS_INIT);

  // re-seed when fleet size changes
  useEffect(() => { setFleet(buildFleet(armCount)); }, [armCount]);

  // small per-tick jitter so the live counters / sparklines move
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
    <div className="app" data-density={density} style={{ "--ok": accent } as React.CSSProperties}>
      <TopBar fleet={fleet} alerts={alerts} selected={selected} onAck={() => setScreen("logs")} />
      <SideNav />
      <main className="main">
        <ScreenPlaceholder />
      </main>
      <BottomBar fleet={fleet} />
      <TweaksPanel />
    </div>
  );
}

function ScreenPlaceholder() {
  const screen = useUiStore(s => s.screen);
  const item = NAV.find(n => n.id === screen);
  return (
    <div className="screen" style={{ display: "grid", placeItems: "center" }}>
      <Panel
        title={`▸ ${item?.label ?? screen.toUpperCase()}`}
        style={{ maxWidth: 480 }}
        right={<span className="mono dim" style={{ fontSize: 10 }}>{item?.hot}</span>}
      >
        <p className="mono" style={{ fontSize: 12, color: "var(--fg-mute)", margin: 0 }}>
          {SCREEN_BLURB[screen]}
        </p>
        <hr className="hr" />
        <p className="mono dim" style={{ fontSize: 11, margin: 0 }}>
          Shell + stores + libs are live. Real screen lands in the next phase.
          Try ↶/↷ and ⌘S in the meantime — the doc store accepts edits via the
          command console (P4).
        </p>
      </Panel>
    </div>
  );
}
