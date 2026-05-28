// screen-fleet.jsx — floor map + robot table

function FloorMap({ fleet, selectedId, onSelect, density }) {
  const ref = React.useRef();
  const [hover, setHover] = React.useState(null);

  return (
    <div className="floormap" ref={ref}>
      {/* grid */}
      <svg className="floormap-grid" viewBox="0 0 1000 700" preserveAspectRatio="none">
        <defs>
          <pattern id="g1" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(120,180,200,.06)" strokeWidth="1"/>
          </pattern>
          <pattern id="g2" width="200" height="200" patternUnits="userSpaceOnUse">
            <path d="M 200 0 L 0 0 0 200" fill="none" stroke="rgba(120,180,200,.12)" strokeWidth="1"/>
          </pattern>
        </defs>
        <rect width="1000" height="700" fill="url(#g1)" />
        <rect width="1000" height="700" fill="url(#g2)" />

        {/* zones */}
        <g>
          <rect x="40" y="40" width="380" height="240" fill="rgba(74,222,128,.04)" stroke="rgba(74,222,128,.25)" strokeDasharray="4 4" />
          <text x="56" y="60" fill="rgba(74,222,128,.7)" fontSize="11" fontFamily="JetBrains Mono">ZONE A · ASSEMBLY</text>

          <rect x="440" y="40" width="520" height="240" fill="rgba(56,189,248,.04)" stroke="rgba(56,189,248,.22)" strokeDasharray="4 4" />
          <text x="456" y="60" fill="rgba(56,189,248,.7)" fontSize="11" fontFamily="JetBrains Mono">ZONE B · KITTING</text>

          <rect x="40" y="300" width="240" height="360" fill="rgba(232,121,249,.04)" stroke="rgba(232,121,249,.22)" strokeDasharray="4 4" />
          <text x="56" y="320" fill="rgba(232,121,249,.7)" fontSize="11" fontFamily="JetBrains Mono">DOCK · LOAD</text>

          <rect x="300" y="300" width="380" height="220" fill="rgba(251,191,36,.03)" stroke="rgba(251,191,36,.22)" strokeDasharray="4 4" />
          <text x="316" y="320" fill="rgba(251,191,36,.7)" fontSize="11" fontFamily="JetBrains Mono">ZONE C · INSPECTION</text>

          <rect x="700" y="300" width="260" height="220" fill="rgba(56,189,248,.04)" stroke="rgba(56,189,248,.22)" strokeDasharray="4 4" />
          <text x="716" y="320" fill="rgba(56,189,248,.7)" fontSize="11" fontFamily="JetBrains Mono">CHARGE-01..06</text>
          {/* charge bays */}
          {[0,1,2,3,4,5].map(i => (
            <rect key={i} x={720 + (i%3)*72} y={340 + Math.floor(i/3)*64} width="56" height="48" fill="rgba(56,189,248,.08)" stroke="rgba(56,189,248,.4)" />
          ))}

          <rect x="300" y="540" width="660" height="120" fill="rgba(120,180,200,.02)" stroke="rgba(120,180,200,.18)" strokeDasharray="4 4" />
          <text x="316" y="560" fill="rgba(150,180,200,.55)" fontSize="11" fontFamily="JetBrains Mono">CORRIDOR · NAV</text>

          {/* waypoints */}
          {[[140,200],[340,160],[600,160],[840,180],[180,440],[420,440],[580,440],[820,440],[480,600],[760,600]].map(([x,y], i) => (
            <g key={i}>
              <circle cx={x} cy={y} r="3" fill="none" stroke="rgba(150,180,200,.4)" />
              <text x={x+6} y={y+3} fill="rgba(150,180,200,.4)" fontSize="9" fontFamily="JetBrains Mono">W{String(i+1).padStart(2,"0")}</text>
            </g>
          ))}
        </g>

        {/* path traces for active robots */}
        {fleet.filter(r => r.status === "ACTIVE").slice(0, 6).map((r, i) => {
          const x = r.x * 1000, y = r.y * 700;
          const dx = Math.cos(r.heading * Math.PI/180) * 60;
          const dy = Math.sin(r.heading * Math.PI/180) * 60;
          return (
            <line key={r.id} x1={x} y1={y} x2={x + dx} y2={y + dy}
              stroke="rgba(74,222,128,.35)" strokeWidth="1" strokeDasharray="2 3" />
          );
        })}

        {/* robots */}
        {fleet.map(r => {
          const x = r.x * 1000, y = r.y * 700;
          const isSel = r.id === selectedId;
          const isHover = hover === r.id;
          const c = {
            ACTIVE: "#4ade80", IDLE: "#7a8a96", CHARGING: "#38bdf8",
            TELEOP: "#e879f9", FAULT: "#ef4444", OFFLINE: "#475461",
          }[r.status];
          return (
            <g key={r.id}
               onClick={() => onSelect(r.id)}
               onMouseEnter={() => setHover(r.id)}
               onMouseLeave={() => setHover(null)}
               style={{ cursor: "pointer" }}
            >
              {(isSel || isHover) && (
                <>
                  <circle cx={x} cy={y} r="20" fill="none" stroke={c} strokeOpacity="0.3" />
                  <circle cx={x} cy={y} r="14" fill="none" stroke={c} strokeOpacity="0.55" strokeDasharray="3 2" />
                </>
              )}
              {r.status === "ACTIVE" && (
                <circle cx={x} cy={y} r="10" fill="none" stroke={c} strokeOpacity="0.4">
                  <animate attributeName="r" from="6" to="14" dur="2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.6" to="0" dur="2s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx={x} cy={y} r="5" fill={c} stroke="#06090d" strokeWidth="1.5" />
              {/* heading tick */}
              <line x1={x} y1={y}
                x2={x + Math.cos(r.heading * Math.PI/180) * 9}
                y2={y + Math.sin(r.heading * Math.PI/180) * 9}
                stroke={c} strokeWidth="1.5" />
              {(isSel || isHover || density === "comfy") && (
                <text x={x + 9} y={y - 6} fill={c} fontSize="9" fontFamily="JetBrains Mono">{r.id}</text>
              )}
            </g>
          );
        })}
      </svg>

      {/* HUD overlays */}
      <div className="floor-hud tl">
        <Crosshair color="var(--ok)" />
        <div>
          <div className="tag dim">FACILITY</div>
          <div className="mono" style={{ fontSize: 12 }}>HELIX·BAY-07</div>
          <div className="tag dim" style={{ marginTop: 2 }}>FLOOR 04 · 1240 m²</div>
        </div>
      </div>
      <div className="floor-hud tr">
        <div>
          <div className="tag dim">VIEW</div>
          <div className="mono" style={{ fontSize: 12 }}>SCHEMATIC · 1:80</div>
        </div>
        <div style={{ display:"flex", gap: 4 }}>
          {["SCHEMATIC","BLUEPRINT","SATELLITE"].map((m, i) =>
            <button key={m} className={"chip" + (i===0?" on":"")}>{m}</button>
          )}
        </div>
      </div>
      <div className="floor-hud bl">
        <div className="tag dim">LEGEND</div>
        <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
          {[
            ["ACTIVE","var(--ok)"],
            ["IDLE","var(--fg-mute)"],
            ["CHARGE","var(--info)"],
            ["TELEOP","var(--magenta)"],
            ["FAULT","var(--err)"],
          ].map(([k,c]) => (
            <div key={k} style={{ display:"flex", gap: 5, alignItems:"center" }}>
              <span style={{ width: 7, height: 7, background: c, borderRadius: "50%" }} />
              <span className="tag" style={{ color: c }}>{k}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="floor-hud br">
        <div className="mono dim" style={{ fontSize: 10 }}>X 042.18m  Y 028.74m</div>
        <div className="mono dim" style={{ fontSize: 10 }}>SCAN-AGE 0.3s</div>
      </div>
    </div>
  );
}

function FleetTable({ fleet, selectedId, onSelect }) {
  const [sort, setSort] = React.useState({ key: "id", dir: 1 });
  const sorted = React.useMemo(() => {
    const a = [...fleet];
    a.sort((x, y) => {
      const xv = x[sort.key], yv = y[sort.key];
      if (xv < yv) return -1 * sort.dir;
      if (xv > yv) return 1 * sort.dir;
      return 0;
    });
    return a;
  }, [fleet, sort]);
  const hdr = (k, label, w) => (
    <th style={{ width: w }} onClick={() => setSort(s => ({ key: k, dir: s.key === k ? -s.dir : 1 }))}>
      <span>{label}</span>
      <span className="dim" style={{ marginLeft: 4 }}>{sort.key === k ? (sort.dir > 0 ? "▲" : "▼") : ""}</span>
    </th>
  );

  return (
    <div className="table-wrap">
      <table className="dtable">
        <thead>
          <tr>
            {hdr("id", "ID", 60)}
            {hdr("callsign", "CALLSIGN", 80)}
            {hdr("status", "ST", 60)}
            {hdr("zone", "ZONE", 70)}
            {hdr("task", "TASK", null)}
            {hdr("battery", "BAT", 70)}
            {hdr("temp", "T°", 40)}
            {hdr("latencyMs", "PING", 50)}
            {hdr("uptime", "UP·h", 50)}
            {hdr("fw", "FW", 60)}
          </tr>
        </thead>
        <tbody>
          {sorted.map(r => {
            const bc = r.battery > 50 ? "var(--ok)" : r.battery > 20 ? "var(--warn)" : "var(--err)";
            return (
              <tr key={r.id}
                  className={r.id === selectedId ? "sel" : ""}
                  onClick={() => onSelect(r.id)}>
                <td className="mono"><StatusDot status={r.status} size={6} /> <span style={{ marginLeft: 6 }}>{r.id}</span></td>
                <td>{r.callsign}</td>
                <td className="mono" style={{ color: {
                  ACTIVE:"var(--ok)",IDLE:"var(--fg-mute)",CHARGING:"var(--info)",
                  TELEOP:"var(--magenta)",FAULT:"var(--err)",OFFLINE:"var(--off)"
                }[r.status] }}>{r.status}</td>
                <td className="mono dim">{r.zone}</td>
                <td className="mono" style={{ color: "var(--fg-mute)" }}>{r.task}</td>
                <td>
                  <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                    <Bar value={r.battery} color={bc} />
                    <span className="mono" style={{ fontSize: 10, color: bc, minWidth: 22 }}>{r.battery}</span>
                  </div>
                </td>
                <td className="mono" style={{ color: r.temp > 55 ? "var(--warn)" : "var(--fg)" }}>{r.temp}</td>
                <td className="mono dim">{r.latencyMs != null ? r.latencyMs : "—"}</td>
                <td className="mono dim">{r.uptime}</td>
                <td className="mono dim">{r.fw}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FleetScreen({ fleet, selectedId, onSelect, alerts, density, onGoto }) {
  const [filter, setFilter] = React.useState("ALL");
  const filtered = filter === "ALL" ? fleet : fleet.filter(r => r.status === filter);

  return (
    <div className="screen fleet">
      <div className="screen-l">
        <Panel title="FACILITY · LIVE MAP" right={
          <div style={{ display: "flex", gap: 4 }}>
            {["ALL","ACTIVE","FAULT","TELEOP","CHARGING"].map(k =>
              <button key={k} className={"chip" + (filter === k ? " on" : "")} onClick={() => setFilter(k)}>{k}</button>
            )}
          </div>
        } pad={false}>
          <FloorMap fleet={filtered} selectedId={selectedId} onSelect={(id) => { onSelect(id); }} density={density} />
        </Panel>
        <Panel title="FLEET ROSTER" right={
          <div className="mono dim" style={{ fontSize: 10 }}>
            {filtered.length}/{fleet.length} ROBOTS · SORT BY HEADER
          </div>
        } pad={false}>
          <FleetTable fleet={filtered} selectedId={selectedId} onSelect={onSelect} />
        </Panel>
      </div>
      <div className="screen-r">
        <SelectedCard robot={fleet.find(r => r.id === selectedId)} onGoto={onGoto} />
        <AlertsFeed alerts={alerts} />
        <FleetMiniStats fleet={fleet} />
      </div>
    </div>
  );
}

function SelectedCard({ robot, onGoto }) {
  if (!robot) {
    return (
      <Panel title="SELECTION">
        <div style={{ padding: "24px 8px", textAlign: "center", color: "var(--dim)" }}>
          <div className="mono" style={{ fontSize: 12 }}>NO ROBOT SELECTED</div>
          <div className="tag dim" style={{ marginTop: 4 }}>Click any robot on the map or roster</div>
        </div>
      </Panel>
    );
  }
  const series = useSeries(parseInt(robot.id.slice(2)), 40, 50, 30);
  return (
    <Panel title={`◉ ${robot.id} · ${robot.callsign}`} right={
      <span className="mono" style={{ fontSize: 10, color: "var(--dim)" }}>{robot.hex}</span>
    }>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 10, marginBottom: 10 }}>
        <Stat label="STATUS" value={robot.status} color={{
          ACTIVE:"var(--ok)",IDLE:"var(--fg-mute)",CHARGING:"var(--info)",
          TELEOP:"var(--magenta)",FAULT:"var(--err)",OFFLINE:"var(--off)"
        }[robot.status]} />
        <Stat label="ZONE" value={robot.zone} />
        <Stat label="BATTERY" value={`${robot.battery}%`} sub={`${(robot.battery * 0.95).toFixed(1)} kWh`} />
        <Stat label="UPTIME" value={`${robot.uptime}h`} sub="continuous" />
        <Stat label="PING" value={robot.latencyMs != null ? `${robot.latencyMs}ms` : "—"} />
        <Stat label="CORE T°" value={`${robot.temp}°C`} color={robot.temp > 55 ? "var(--warn)" : undefined} />
      </div>
      <div style={{ marginBottom: 8 }}>
        <div className="tag dim">TASK</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--fg)" }}>{robot.task}</div>
      </div>
      <div style={{ marginBottom: 10 }}>
        <div style={{ display:"flex", justifyContent:"space-between" }}>
          <span className="tag dim">CPU LOAD · last 30s</span>
          <span className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>{robot.cpu}%</span>
        </div>
        <Sparkline data={series} width={232} height={32} color="var(--ok)" />
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <button className="btn primary" onClick={() => onGoto("robot")}>OPEN DETAIL ›</button>
        <button className="btn" onClick={() => onGoto("teleop")}>TELEOP</button>
        <button className="btn danger">E·STOP</button>
      </div>
    </Panel>
  );
}

function AlertsFeed({ alerts }) {
  return (
    <Panel title="ALERTS · LIVE" right={<span className="tag dim">REALTIME · UDP</span>} pad={false}>
      <div className="alerts">
        {alerts.map((a, i) => (
          <div key={i} className="alert">
            <span className={`sev sev-${a.sev}`}>{a.sev}</span>
            <span className="mono dim" style={{ fontSize: 10 }}>{a.ts}</span>
            <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)" }}>{a.src}</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--fg)" }}>{a.msg}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function FleetMiniStats({ fleet }) {
  const totalTasks = fleet.reduce((a,b) => a + b.tasksDone, 0);
  const totalFaults = fleet.reduce((a,b) => a + b.faults24h, 0);
  const avgUp = (fleet.reduce((a,b) => a + b.uptime, 0) / fleet.length).toFixed(1);
  const series1 = useSeries(11, 32, 60, 20);
  const series2 = useSeries(12, 32, 30, 16);
  return (
    <Panel title="FLEET PULSE · 24H">
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 10, marginBottom: 10 }}>
        <Stat label="TASKS DONE" value={totalTasks.toLocaleString()} sub="+14 last hr" color="var(--ok)" />
        <Stat label="FAULTS" value={totalFaults} sub={`${(totalFaults/fleet.length).toFixed(2)}/robot`} color="var(--warn)" />
        <Stat label="AVG UPTIME" value={`${avgUp}h`} />
        <Stat label="MTBF" value="412h" sub="↑ 4.2%" color="var(--ok)" />
      </div>
      <div>
        <div className="tag dim">THROUGHPUT · units/min</div>
        <Sparkline data={series1} width={232} height={28} color="var(--ok)" />
      </div>
      <div style={{ marginTop: 6 }}>
        <div className="tag dim">FAULT RATE · ‰</div>
        <Sparkline data={series2} width={232} height={28} color="var(--warn)" />
      </div>
    </Panel>
  );
}

Object.assign(window, { FleetScreen });
