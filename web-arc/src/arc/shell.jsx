// shell.jsx — top bar, side nav, bottom telemetry bar

const NAV = [
  { id: "fleet",    label: "FLEET",     hot: "1", icon: "▦" },
  { id: "robot",    label: "ROBOT",     hot: "2", icon: "◉" },
  { id: "teleop",   label: "TELEOP",    hot: "3", icon: "✦" },
  { id: "tasks",    label: "MISSIONS",  hot: "4", icon: "▶" },
  { id: "scene",    label: "SCENE 3D",  hot: "5", icon: "◈" },
  { id: "analytics",label: "ANALYTICS", hot: "6", icon: "⌬" },
  { id: "logs",     label: "LOGS",      hot: "7", icon: "≡" },
  { id: "settings", label: "CONFIG",    hot: "8", icon: "⚙" },
];

function TopBar({ screen, selected, fleet, onAck, alerts }) {
  const now = useClock();
  const breath = useBreath(1, 1500, 1);
  const counts = React.useMemo(() => {
    const c = { ACTIVE: 0, IDLE: 0, CHARGING: 0, TELEOP: 0, FAULT: 0, OFFLINE: 0 };
    fleet.forEach(r => c[r.status]++);
    return c;
  }, [fleet]);
  const screenLabel = (NAV.find(n => n.id === screen) || {}).label || "";
  const openAlerts = alerts.filter(a => a.sev === "ERR" || a.sev === "WARN").length;

  return (
    <header className="topbar">
      <div className="topbar-l">
        <div className="brand">
          <svg width="20" height="20" viewBox="0 0 24 24">
            <rect x="4" y="3" width="16" height="11" fill="none" stroke="var(--ok)" strokeWidth="1.5" />
            <circle cx="9" cy="8" r="1.2" fill="var(--ok)" />
            <circle cx="15" cy="8" r="1.2" fill="var(--ok)" />
            <line x1="8" y1="14" x2="8" y2="21" stroke="var(--ok)" strokeWidth="1.5" />
            <line x1="16" y1="14" x2="16" y2="21" stroke="var(--ok)" strokeWidth="1.5" />
            <line x1="12" y1="3" x2="12" y2="1" stroke="var(--ok)" strokeWidth="1.5" />
          </svg>
          <div>
            <div style={{ fontSize: 11, letterSpacing: ".18em", color: "var(--fg)" }}>HELIX·OPS</div>
            <div className="tag dim" style={{ fontSize: 9 }}>HUMANOID FLEET CONTROL · v4.2.18</div>
          </div>
        </div>
        <div className="breadcrumb">
          <span className="dim">SECTOR</span>
          <span>BAY-07 / EAST</span>
          <span className="dim">›</span>
          <span style={{ color: "var(--ok)" }}>{screenLabel}</span>
          {screen === "robot" && selected && <>
            <span className="dim">›</span>
            <span className="mono">{selected.id}</span>
            <span className="dim">{selected.callsign}</span>
          </>}
        </div>
      </div>

      <div className="topbar-r">
        <div className="topbar-counts">
          {[
            ["ACT", counts.ACTIVE, "var(--ok)"],
            ["IDL", counts.IDLE, "var(--fg-mute)"],
            ["CHG", counts.CHARGING, "var(--info)"],
            ["TOP", counts.TELEOP, "var(--magenta)"],
            ["FLT", counts.FAULT, "var(--err)"],
            ["OFF", counts.OFFLINE, "var(--off)"],
          ].map(([k, n, c]) => (
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
          <div className="mono dim" style={{ fontSize: 10 }}>{utcDate(now)} · MISSION D+147</div>
        </div>

        <div className="user">
          <div style={{
            width: 26, height: 26, border: "1px solid var(--border)",
            display: "grid", placeItems: "center", fontSize: 11, color: "var(--ok)",
          }}>KO</div>
          <div>
            <div style={{ fontSize: 11 }}>OP·KOSTA</div>
            <div className="tag dim">CLEAR-L3</div>
          </div>
        </div>
      </div>
    </header>
  );
}

function SideNav({ screen, onScreen }) {
  return (
    <nav className="sidenav">
      {NAV.map(item => (
        <button
          key={item.id}
          className={"navbtn" + (screen === item.id ? " active" : "")}
          onClick={() => onScreen(item.id)}
          title={item.label}
        >
          <span className="navbtn-icon">{item.icon}</span>
          <span className="navbtn-label">{item.label}</span>
          <span className="navbtn-hot">{item.hot}</span>
        </button>
      ))}
      <div style={{ flex: 1 }} />
      <div className="navfoot">
        <div className="tag dim">NODE</div>
        <div className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>ops-1.lan</div>
        <div className="tag dim" style={{ marginTop: 6 }}>BUILD</div>
        <div className="mono" style={{ fontSize: 10, color: "var(--fg-mute)" }}>e7b41a · 26·May</div>
      </div>
    </nav>
  );
}

function BottomBar({ fleet }) {
  const breath = useBreath(2, 1000, 1);
  const bw = (24 + breath * 4).toFixed(1);
  const lat = (8 + breath * 1.5).toFixed(0);
  const avgBattery = (fleet.filter(r => r.status !== "OFFLINE").reduce((a, b) => a + b.battery, 0) / Math.max(1, fleet.filter(r => r.status !== "OFFLINE").length)).toFixed(0);

  const items = [
    ["UPLINK",    "AES-256·OK",         "var(--ok)"],
    ["BW",        `${bw} Mb/s ↑↓`,      "var(--fg)"],
    ["LATENCY",   `${lat} ms p50`,      "var(--fg)"],
    ["LOSS",      "0.02%",              "var(--ok)"],
    ["ROS2",      "humble · 14 nodes",  "var(--info)"],
    ["GRID",      "MAINS · 480V",       "var(--ok)"],
    ["AVG-SOC",   `${avgBattery}%`,     "var(--fg)"],
    ["GPS-RTK",   "FIX · 11 SV",        "var(--ok)"],
    ["WX",        "INDOOR · 22.4°C",    "var(--fg-mute)"],
    ["SAFETY",    "E-STOP ARMED",       "var(--warn)"],
  ];
  return (
    <footer className="bottombar">
      {items.map(([k, v, c], i) => (
        <div key={i} className="bb-item">
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

Object.assign(window, { NAV, TopBar, SideNav, BottomBar });
