// app.jsx — main app shell + routing

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#4ade80",
  "density": "dense",
  "showGrid": true,
  "robotCount": 30,
  "mapStyle": "schematic"
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [fleet, setFleet] = React.useState(() => buildFleet(t.robotCount));
  const [screen, setScreen] = React.useState("fleet");
  const [selectedId, setSelectedId] = React.useState("H-003");
  const [alerts, setAlerts] = React.useState(ALERTS_INIT);

  // rebuild fleet if count changes
  React.useEffect(() => {
    setFleet(buildFleet(t.robotCount));
  }, [t.robotCount]);

  // breathe the fleet — battery/cpu drift, occasional status flicker
  React.useEffect(() => {
    const id = setInterval(() => {
      setFleet(f => f.map(r => {
        if (r.status === "OFFLINE") return r;
        const dB = r.status === "CHARGING" ? +0.05 : -0.04;
        const cpu = Math.max(15, Math.min(95, r.cpu + (Math.random() - 0.5) * 4));
        const temp = Math.max(34, Math.min(72, r.temp + (Math.random() - 0.5) * 1.2));
        const lat = r.latencyMs != null ? Math.max(4, r.latencyMs + (Math.random() - 0.5) * 4) : null;
        const battery = Math.max(0, Math.min(100, r.battery + dB));
        return { ...r, cpu: Math.round(cpu), temp: Math.round(temp), latencyMs: lat ? Math.round(lat) : null, battery: +battery.toFixed(1) };
      }));
    }, 1500);
    return () => clearInterval(id);
  }, []);

  // keyboard navigation: 1–8 hops between screens
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
  const onSelect = id => setSelectedId(id);
  const onGoto = s => setScreen(s);

  return (
    <div className="app" data-density={t.density} style={{ "--ok": t.accent }}>
      <TopBar screen={screen} selected={selected} fleet={fleet} alerts={alerts} onAck={() => setScreen("logs")} />
      <SideNav screen={screen} onScreen={setScreen} />

      <main className="main">
        {screen === "fleet" && <FleetScreen fleet={fleet} selectedId={selectedId} onSelect={onSelect} alerts={alerts} density={t.density} onGoto={onGoto} />}
        {screen === "robot" && <RobotDetailScreen robot={selected} onGoto={onGoto} />}
        {screen === "teleop" && <TeleopScreen robot={selected} onGoto={onGoto} />}
        {screen === "tasks" && <TasksScreen fleet={fleet} onSelect={onSelect} />}
        {screen === "scene" && <SceneScreen robot={selected} />}
        {screen === "analytics" && <AnalyticsScreen fleet={fleet} />}
        {screen === "logs" && <LogsScreen alerts={alerts} />}
        {screen === "settings" && <SettingsScreen robot={selected} onGoto={onGoto} />}
      </main>

      <BottomBar fleet={fleet} />

      <TweaksPanel>
        <TweakSection label="Display" />
        <TweakColor label="Accent" value={t.accent}
          options={["#4ade80","#38bdf8","#fbbf24","#e879f9","#f97316"]}
          onChange={v => setTweak("accent", v)} />
        <TweakRadio label="Density" value={t.density}
          options={["dense","comfy"]}
          onChange={v => setTweak("density", v)} />
        <TweakToggle label="Grid overlay" value={t.showGrid}
          onChange={v => setTweak("showGrid", v)} />
        <TweakSection label="Fleet" />
        <TweakSlider label="Robot count" value={t.robotCount} min={6} max={60} unit=""
          onChange={v => setTweak("robotCount", v)} />
        <TweakSelect label="Map style" value={t.mapStyle}
          options={["schematic","blueprint","satellite"]}
          onChange={v => setTweak("mapStyle", v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
