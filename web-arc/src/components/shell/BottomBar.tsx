import type { Robot } from "@/types";
import { useBreath } from "@/hooks/useBreath";

export interface BottomBarProps { fleet: Robot[]; }

// Telemetry strip across the bottom: live uplink / bandwidth / latency /
// loss / ROS2 / grid / battery / GPS / weather / safety status.
export function BottomBar({ fleet }: BottomBarProps) {
  const breath = useBreath(2, 1000, 1);
  const bw = (24 + breath * 4).toFixed(1);
  const lat = (8 + breath * 1.5).toFixed(0);
  const onlineCount = Math.max(1, fleet.filter(r => r.status !== "OFFLINE").length);
  const avgBattery = (fleet.filter(r => r.status !== "OFFLINE").reduce((a, b) => a + b.battery, 0) / onlineCount).toFixed(0);

  const items: ReadonlyArray<readonly [string, string, string]> = [
    ["UPLINK",  "AES-256·OK",         "var(--ok)"],
    ["BW",      `${bw} Mb/s ↑↓`,      "var(--fg)"],
    ["LATENCY", `${lat} ms p50`,      "var(--fg)"],
    ["LOSS",    "0.02%",              "var(--ok)"],
    ["ROS2",    "humble · 14 nodes",  "var(--info)"],
    ["GRID",    "MAINS · 480V",       "var(--ok)"],
    ["AVG-SOC", `${avgBattery}%`,     "var(--fg)"],
    ["GPS-RTK", "FIX · 11 SV",        "var(--ok)"],
    ["WX",      "INDOOR · 22.4°C",    "var(--fg-mute)"],
    ["SAFETY",  "E-STOP ARMED",       "var(--warn)"],
  ];

  return (
    <footer className="bottombar">
      {items.map(([k, v, c]) => (
        <div key={k} className="bb-item">
          <span className="tag dim">{k}</span>
          <span className="mono" style={{ color: c, fontSize: 11 }}>{v}</span>
        </div>
      ))}
      <div style={{ flex: 1 }} />
      <div className="bb-item">
        <span className="tag dim">HEARTBEAT</span>
        <span className="mono" style={{ color: "var(--ok)", fontSize: 11 }}>
          ▮▮▮▮▯▮▮▮▮▮ {Math.floor(60 + breath * 2)} bpm
        </span>
      </div>
    </footer>
  );
}
