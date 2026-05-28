import { useMemo } from "react";
import type { Alert, Robot, Status } from "@/types";
import { useClock } from "@/hooks/useClock";
import { useBreath } from "@/hooks/useBreath";
import { utcDate, utcHMS } from "@/lib/format";
import { useUiStore } from "@/store/useUiStore";
import { NAV } from "./nav";

export interface TopBarProps {
  fleet: Robot[];
  alerts: Alert[];
  selected: Robot | undefined;
  onAck: () => void;
}

// ARC·OPS top bar: brand, breadcrumb, live status counters, alert pill,
// UTC clock, operator badge. Reads the current screen from the UI store so
// the breadcrumb stays in sync.
export function TopBar({ fleet, alerts, selected, onAck }: TopBarProps) {
  const now = useClock();
  const breath = useBreath(1, 1500, 1);
  const screen = useUiStore(s => s.screen);

  const counts = useMemo(() => {
    const c: Record<Status, number> = { ACTIVE: 0, IDLE: 0, TELEOP: 0, FAULT: 0, OFFLINE: 0 };
    fleet.forEach(r => { c[r.status]++; });
    return c;
  }, [fleet]);
  const screenLabel = NAV.find(n => n.id === screen)?.label ?? "";
  const openAlerts = alerts.filter(a => a.sev === "ERR" || a.sev === "WARN").length;

  return (
    <header className="topbar">
      <div className="topbar-l">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 24 24">
            <rect x="9" y="20" width="6" height="2" fill="var(--ok)" />
            <rect x="10.5" y="17" width="3" height="3" fill="var(--ok)" opacity="0.6" />
            <line x1="12" y1="17" x2="5" y2="10" stroke="var(--ok)" strokeWidth="2" strokeLinecap="round" />
            <line x1="5" y1="10" x2="17" y2="6" stroke="var(--ok)" strokeWidth="2" strokeLinecap="round" />
            <circle cx="5" cy="10" r="1.4" fill="#06090d" stroke="var(--ok)" strokeWidth="1.2" />
            <circle cx="17" cy="6" r="1.4" fill="#06090d" stroke="var(--ok)" strokeWidth="1.2" />
            <rect x="16" y="3.5" width="3" height="3" fill="var(--ok)" />
          </svg>
          <div>
            <div style={{ fontSize: 11, letterSpacing: ".18em", color: "var(--fg)" }}>ARC·OPS</div>
            <div className="tag dim" style={{ fontSize: 9 }}>6-DoF ARM FLEET · web-arc</div>
          </div>
        </div>
        <div className="breadcrumb">
          <span className="dim">FACILITY</span>
          <span>BAY-07 / EAST</span>
          <span className="dim">›</span>
          <span style={{ color: "var(--ok)" }}>{screenLabel}</span>
          {selected && (screen === "robot" || screen === "teleop" || screen === "scene" || screen === "settings") && (
            <>
              <span className="dim">›</span>
              <span className="mono">{selected.id}</span>
              <span className="dim">{selected.callsign}</span>
            </>
          )}
        </div>
      </div>

      <div className="topbar-r">
        <div className="topbar-counts">
          {([
            ["RUN", counts.ACTIVE,  "var(--ok)"],
            ["IDL", counts.IDLE,    "var(--fg-mute)"],
            ["TOP", counts.TELEOP,  "var(--magenta)"],
            ["FLT", counts.FAULT,   "var(--err)"],
            ["OFF", counts.OFFLINE, "var(--off)"],
          ] as const).map(([k, n, c]) => (
            <div key={k} className="topbar-count">
              <span className="tag dim">{k}</span>
              <span className="mono" style={{ color: c, fontSize: 13 }}>{String(n).padStart(2, "0")}</span>
            </div>
          ))}
        </div>

        <button className="alert-pill" onClick={onAck}>
          <span style={{ width: 6, height: 6, background: "var(--err)", borderRadius: "50%",
            boxShadow: `0 0 ${4 + breath * 2}px var(--err)` }} />
          <span>{openAlerts} OPEN</span>
        </button>

        <div className="clock">
          <div className="mono" style={{ fontSize: 14, color: "var(--ok)", lineHeight: 1 }}>
            {utcHMS(now)} <span className="dim">UTC</span>
          </div>
          <div className="mono dim" style={{ fontSize: 10 }}>{utcDate(now)} · SHIFT-B</div>
        </div>

        <div className="user">
          <div style={{ width: 26, height: 26, border: "1px solid var(--border)", display: "grid", placeItems: "center", fontSize: 11, color: "var(--ok)" }}>KO</div>
          <div>
            <div style={{ fontSize: 11 }}>OP·KOSTA</div>
            <div className="tag dim">CLEAR-L3</div>
          </div>
        </div>
      </div>
    </header>
  );
}
