// arm-app.jsx — main app for the 6-DOF arm console

// arm-specific NAV (overrides the humanoid one with PATH + CAM + IMPORT inserted)
const NAV_ARM = [
  { id: "fleet",     label: "FLEET",     hot: "1", icon: "▦" },
  { id: "robot",     label: "ROBOT",     hot: "2", icon: "◉" },
  { id: "teleop",    label: "TELEOP",    hot: "3", icon: "✦" },
  { id: "cam",       label: "CAM",       hot: "4", icon: "⦿" },
  { id: "path",      label: "PATH",      hot: "5", icon: "↝" },
  { id: "program",   label: "PROGRAM",   hot: "p", icon: "❖" },
  { id: "import",    label: "IMPORT",    hot: "6", icon: "↓" },
  { id: "tasks",     label: "MISSIONS",  hot: "7", icon: "▶" },
  { id: "scene",     label: "SCENE 3D",  hot: "8", icon: "◈" },
  { id: "analytics", label: "ANALYTICS", hot: "9", icon: "⌬" },
  { id: "logs",      label: "LOGS",      hot: "0", icon: "≡" },
  { id: "settings",  label: "CONFIG",    hot: "-", icon: "⚙" },
];
Object.assign(window, { NAV: NAV_ARM });

const TWEAK_DEFAULTS_ARM = /*EDITMODE-BEGIN*/{
  "accent": "#4ade80",
  "density": "dense",
  "showWorkspace": true,
  "armCount": 30,
  "autoRotate3D": false
}/*EDITMODE-END*/;

// override TopBar to brand as ARM·OPS
function ArmTopBar({ screen, selected, fleet, alerts, onAck }) {
  const now = useClock();
  const breath = useBreath(1, 1500, 1);
  const counts = React.useMemo(() => {
    const c = { ACTIVE: 0, IDLE: 0, TELEOP: 0, FAULT: 0, OFFLINE: 0 };
    fleet.forEach(r => c[r.status]++);
    return c;
  }, [fleet]);
  const screenLabel = (NAV.find(n => n.id === screen) || {}).label || "";
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
            <div className="tag dim" style={{ fontSize: 9 }}>6-DoF ARM FLEET · v5.22.3</div>
          </div>
        </div>
        <div className="breadcrumb">
          <span className="dim">FACILITY</span>
          <span>BAY-07 / EAST</span>
          <span className="dim">›</span>
          <span style={{ color: "var(--ok)" }}>{screenLabel}</span>
          {selected && (screen === "robot" || screen === "teleop" || screen === "scene" || screen === "settings") && <>
            <span className="dim">›</span>
            <span className="mono">{selected.id}</span>
            <span className="dim">{selected.callsign}</span>
          </>}
        </div>
      </div>

      <div className="topbar-r">
        <div className="topbar-counts">
          {[
            ["RUN", counts.ACTIVE, "var(--ok)"],
            ["IDL", counts.IDLE, "var(--fg-mute)"],
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

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS_ARM);
  const [fleet, setFleet] = React.useState(() => buildFleet(t.armCount));
  const [screen, setScreen] = React.useState("fleet");
  const [selectedId, setSelectedId] = React.useState("ARM-003");
  const [alerts] = React.useState(ALERTS_INIT);

  React.useEffect(() => { setFleet(buildFleet(t.armCount)); }, [t.armCount]);

  // breathe the fleet
  React.useEffect(() => {
    const id = setInterval(() => {
      setFleet(f => f.map(r => {
        if (r.status === "OFFLINE") return r;
        const cpu = Math.max(15, Math.min(95, r.cpu + (Math.random() - 0.5) * 4));
        const temp = Math.max(34, Math.min(72, r.temp + (Math.random() - 0.5) * 1.2));
        const lat = r.latencyMs != null ? Math.max(2, r.latencyMs + (Math.random() - 0.5) * 3) : null;
        return { ...r, cpu: Math.round(cpu), temp: Math.round(temp), latencyMs: lat ? Math.round(lat) : null };
      }));
    }, 1500);
    return () => clearInterval(id);
  }, []);

  // keyboard nav 1-8
  React.useEffect(() => {
    const dn = e => {
      if (e.target && e.target.tagName === "INPUT") return;
      const item = NAV.find(n => n.hot === e.key);
      if (item) setScreen(item.id);
    };
    window.addEventListener("keydown", dn);
    return () => window.removeEventListener("keydown", dn);
  }, []);

  const selected = fleet.find(r => r.id === selectedId);
  const onGoto = s => setScreen(s);

  return (
    <div className="app" data-density={t.density} style={{ "--ok": t.accent }}>
      <ArmTopBar screen={screen} selected={selected} fleet={fleet} alerts={alerts} onAck={() => setScreen("logs")} />
      <SideNav screen={screen} onScreen={setScreen} />

      <main className="main">
        {screen === "fleet"     && <FleetScreen fleet={fleet} selectedId={selectedId} onSelect={setSelectedId} alerts={alerts} onGoto={onGoto} />}
        {screen === "robot"     && <RobotDetailScreen robot={selected} onGoto={onGoto} />}
        {screen === "teleop"    && <TeleopScreen robot={selected} onGoto={onGoto} />}
        {screen === "cam"       && <CAMScreen robot={selected} onGoto={onGoto} />}
        {screen === "path"      && <PathScreen robot={selected} />}
        {screen === "program"   && <ProgramScreen robot={selected} onGoto={onGoto} />}
        {screen === "import"    && <ImportScreen onGoto={onGoto} />}
        {screen === "tasks"     && <TasksScreen fleet={fleet} onSelect={setSelectedId} />}
        {screen === "scene"     && <SceneScreen robot={selected} />}
        {screen === "analytics" && <AnalyticsScreen fleet={fleet} />}
        {screen === "logs"      && <LogsScreen alerts={alerts} />}
        {screen === "settings"  && <SettingsScreen robot={selected} onGoto={onGoto} />}
      </main>

      <BottomBar fleet={fleet} />

      <TweaksPanel>
        <TweakSection label="Display" />
        <TweakColor label="Accent" value={t.accent}
          options={["#4ade80","#38bdf8","#fbbf24","#e879f9","#f97316"]}
          onChange={v => setTweak("accent", v)} />
        <TweakRadio label="Density" value={t.density}
          options={["dense","comfy"]} onChange={v => setTweak("density", v)} />
        <TweakSection label="3D Viewer" />
        <TweakToggle label="Show workspace" value={t.showWorkspace}
          onChange={v => setTweak("showWorkspace", v)} />
        <TweakToggle label="Auto-rotate" value={t.autoRotate3D}
          onChange={v => setTweak("autoRotate3D", v)} />
        <TweakSection label="Fleet" />
        <TweakSlider label="Arm count" value={t.armCount} min={6} max={60} unit=""
          onChange={v => setTweak("armCount", v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
