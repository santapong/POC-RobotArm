// arm-screens.jsx — all screens for the 6-DOF arm fleet

// ── FLEET · factory cell grid ────────────────────────────────────────────
function ArmCellIcon({ status, size = 28 }) {
  const c = {
    ACTIVE:"#4ade80",IDLE:"#7a8a96",TELEOP:"#e879f9",FAULT:"#ef4444",OFFLINE:"#475461"
  }[status] || "#7a8a96";
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ display: "block" }}>
      <rect x="9" y="18" width="6" height="3" fill={c} opacity="0.8" />
      <rect x="10.5" y="15" width="3" height="3" fill={c} opacity="0.6" />
      <line x1="12" y1="15" x2="6" y2="9" stroke={c} strokeWidth="2" strokeLinecap="round" />
      <line x1="6" y1="9" x2="16" y2="6" stroke={c} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="6" cy="9" r="1.4" fill="#06090d" stroke={c} strokeWidth="1" />
      <circle cx="16" cy="6" r="1.2" fill="#06090d" stroke={c} strokeWidth="1" />
      <rect x="15" y="4" width="3" height="3" fill={c} opacity="0.5" />
    </svg>
  );
}

function FactoryMap({ fleet, selectedId, onSelect }) {
  const [hover, setHover] = React.useState(null);
  return (
    <div className="factorymap">
      <svg className="floormap-grid" viewBox="0 0 1000 600" preserveAspectRatio="none">
        <defs>
          <pattern id="fg1" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(120,180,200,.06)" strokeWidth="1"/>
          </pattern>
        </defs>
        <rect width="1000" height="600" fill="url(#fg1)" />
        {/* conveyor lanes */}
        {[180, 360, 540].map((y, i) => (
          <g key={y}>
            <rect x="40" y={y - 6} width="920" height="12" fill="rgba(56,189,248,.05)" stroke="rgba(56,189,248,.20)" />
            <text x="48" y={y - 10} fill="rgba(56,189,248,.55)" fontSize="9" fontFamily="JetBrains Mono">CONVEYOR · LINE-{i+1}</text>
            {/* arrows */}
            {[100, 240, 380, 520, 660, 800].map(x => (
              <polygon key={x} points={`${x},${y-3} ${x+8},${y} ${x},${y+3}`} fill="rgba(56,189,248,.5)" />
            ))}
          </g>
        ))}
        {/* zone labels */}
        <text x="48" y="30" fill="rgba(74,222,128,.55)" fontSize="10" fontFamily="JetBrains Mono">BAY-07 · ASSEMBLY FLOOR · 36 CELLS</text>
        <text x="952" y="30" textAnchor="end" fill="rgba(74,222,128,.55)" fontSize="10" fontFamily="JetBrains Mono">SHIFT-B · 06:14 UTC</text>
      </svg>

      <div className="cells">
        {fleet.map(r => {
          const isSel = r.id === selectedId;
          const isHov = hover === r.id;
          const sc = {
            ACTIVE:"var(--ok)",IDLE:"var(--fg-mute)",TELEOP:"var(--magenta)",FAULT:"var(--err)",OFFLINE:"var(--off)"
          }[r.status];
          return (
            <button
              key={r.id}
              className={"cell" + (isSel ? " sel" : "") + " st-" + r.status}
              onClick={() => onSelect(r.id)}
              onMouseEnter={() => setHover(r.id)}
              onMouseLeave={() => setHover(null)}
              style={{ "--sc": sc }}
            >
              <div className="cell-hd">
                <span className="mono cell-id">{r.id}</span>
                <StatusDot status={r.status} size={6} />
              </div>
              <div className="cell-body">
                <ArmCellIcon status={r.status} size={26} />
                <div className="cell-meta">
                  <div className="mono" style={{ fontSize: 9, color: "var(--fg-mute)" }}>{r.callsign}</div>
                  <div className="mono" style={{ fontSize: 9, color: sc }}>{r.status}</div>
                </div>
              </div>
              <div className="cell-task mono">{r.task}</div>
              <div className="cell-foot">
                <span className="mono" style={{ fontSize: 8, color: "var(--dim)" }}>{r.tool}</span>
                <span className="mono" style={{ fontSize: 8, color: r.temp > 55 ? "var(--warn)" : "var(--dim)" }}>{r.temp}°C</span>
              </div>
              {r.status === "ACTIVE" && <div className="cell-pulse" />}
            </button>
          );
        })}
      </div>

      <div className="floor-hud tl">
        <Crosshair color="var(--ok)" />
        <div>
          <div className="tag dim">FACILITY</div>
          <div className="mono" style={{ fontSize: 12 }}>BAY-07 · EAST</div>
          <div className="tag dim" style={{ marginTop: 2 }}>FLOOR 04 · 1240 m² · {fleet.length} ARMS</div>
        </div>
      </div>
    </div>
  );
}

function FleetTable({ fleet, selectedId, onSelect }) {
  const [sort, setSort] = React.useState({ key: "id", dir: 1 });
  const sorted = React.useMemo(() => {
    const a = [...fleet];
    a.sort((x, y) => x[sort.key] < y[sort.key] ? -sort.dir : x[sort.key] > y[sort.key] ? sort.dir : 0);
    return a;
  }, [fleet, sort]);
  const hdr = (k, label, w) => (
    <th style={{ width: w }} onClick={() => setSort(s => ({ key: k, dir: s.key === k ? -s.dir : 1 }))}>
      {label} <span className="dim">{sort.key === k ? (sort.dir > 0 ? "▲" : "▼") : ""}</span>
    </th>
  );
  return (
    <div className="table-wrap">
      <table className="dtable">
        <thead><tr>
          {hdr("id","ID",70)}{hdr("callsign","CALLSIGN",90)}{hdr("status","ST",60)}
          {hdr("zone","CELL",70)}{hdr("task","PROGRAM",null)}
          {hdr("tool","TOOL",80)}
          {hdr("payload","PL·kg",60)}
          {hdr("cycleTime","CYC·s",60)}
          {hdr("temp","T°",40)}{hdr("latencyMs","PING",50)}{hdr("fw","FW",80)}
        </tr></thead>
        <tbody>
          {sorted.map(r => (
            <tr key={r.id} className={r.id === selectedId ? "sel" : ""} onClick={() => onSelect(r.id)}>
              <td className="mono"><StatusDot status={r.status} size={6} /> <span style={{ marginLeft: 6 }}>{r.id}</span></td>
              <td>{r.callsign}</td>
              <td className="mono" style={{ color: {
                ACTIVE:"var(--ok)",IDLE:"var(--fg-mute)",TELEOP:"var(--magenta)",FAULT:"var(--err)",OFFLINE:"var(--off)"
              }[r.status] }}>{r.status}</td>
              <td className="mono dim">{r.zone}</td>
              <td className="mono" style={{ color: "var(--fg-mute)" }}>{r.task}</td>
              <td className="mono dim">{r.tool}</td>
              <td className="mono">{r.payload}</td>
              <td className="mono">{r.cycleTime}</td>
              <td className="mono" style={{ color: r.temp > 55 ? "var(--warn)" : "var(--fg)" }}>{r.temp}</td>
              <td className="mono dim">{r.latencyMs ?? "—"}</td>
              <td className="mono dim">{r.fw}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FleetScreen({ fleet, selectedId, onSelect, alerts, onGoto }) {
  const [filter, setFilter] = React.useState("ALL");
  const filtered = filter === "ALL" ? fleet : fleet.filter(r => r.status === filter);
  return (
    <div className="screen fleet">
      <div className="screen-l">
        <Panel title="FACTORY · LIVE CELL MAP" right={
          <div style={{ display: "flex", gap: 4 }}>
            {["ALL","ACTIVE","FAULT","TELEOP","IDLE"].map(k =>
              <button key={k} className={"chip" + (filter === k ? " on" : "")} onClick={() => setFilter(k)}>{k}</button>
            )}
          </div>
        } pad={false}>
          <FactoryMap fleet={filtered} selectedId={selectedId} onSelect={onSelect} />
        </Panel>
        <Panel title="FLEET ROSTER" right={
          <span className="mono dim" style={{ fontSize: 10 }}>{filtered.length}/{fleet.length} ARMS · SORT BY HEADER</span>
        } pad={false}>
          <FleetTable fleet={filtered} selectedId={selectedId} onSelect={onSelect} />
        </Panel>
      </div>
      <div className="screen-r">
        <SelectedCard robot={fleet.find(r => r.id === selectedId)} onGoto={onGoto} />
        <AlertsFeed alerts={alerts} />
        <FleetPulse fleet={fleet} />
      </div>
    </div>
  );
}

function SelectedCard({ robot, onGoto }) {
  if (!robot) {
    return (
      <Panel title="SELECTION">
        <div style={{ padding: "24px 8px", textAlign: "center", color: "var(--dim)" }}>
          <div className="mono" style={{ fontSize: 12 }}>NO ARM SELECTED</div>
          <div className="tag dim" style={{ marginTop: 4 }}>Click any cell or roster row</div>
        </div>
      </Panel>
    );
  }
  const series = useSeries(parseInt(robot.id.slice(4)), 40, 50, 30);
  return (
    <Panel title={`◉ ${robot.id} · ${robot.callsign}`} right={
      <span className="mono" style={{ fontSize: 10, color: "var(--dim)" }}>{robot.hex}</span>
    }>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 10, marginBottom: 10 }}>
        <Stat label="STATUS" value={robot.status} color={{
          ACTIVE:"var(--ok)",IDLE:"var(--fg-mute)",TELEOP:"var(--magenta)",FAULT:"var(--err)",OFFLINE:"var(--off)"
        }[robot.status]} />
        <Stat label="CELL" value={robot.zone} />
        <Stat label="TOOL" value={robot.tool} />
        <Stat label="PAYLOAD" value={`${robot.payload} kg`} sub={`reach ${robot.reach}m`} />
        <Stat label="CYCLE" value={`${robot.cycleTime}s`} sub={`avg`} />
        <Stat label="CORE T°" value={`${robot.temp}°C`} color={robot.temp > 55 ? "var(--warn)" : undefined} />
      </div>
      <div style={{ marginBottom: 8 }}>
        <div className="tag dim">PROGRAM</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--fg)" }}>{robot.task}</div>
      </div>
      <div style={{ marginBottom: 10 }}>
        <div style={{ display:"flex", justifyContent:"space-between" }}>
          <span className="tag dim">CPU LOAD · last 30s</span>
          <span className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>{robot.cpu}%</span>
        </div>
        <Sparkline data={series} width={232} height={32} color="var(--ok)" />
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <button className="btn primary" onClick={() => onGoto("robot")}>DETAIL ›</button>
        <button className="btn" onClick={() => onGoto("scene")}>3D CAD ›</button>
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

function FleetPulse({ fleet }) {
  const totalTasks = fleet.reduce((a,b)=>a+b.tasksDone,0);
  const totalFaults = fleet.reduce((a,b)=>a+b.faults24h,0);
  const avgCyc = (fleet.reduce((a,b)=>a+b.cycleTime,0)/fleet.length).toFixed(1);
  const series1 = useSeries(11, 32, 60, 20);
  const series2 = useSeries(12, 32, 30, 16);
  return (
    <Panel title="FLEET PULSE · 24H">
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 10, marginBottom: 10 }}>
        <Stat label="CYCLES DONE" value={totalTasks.toLocaleString()} sub="+182 last hr" color="var(--ok)" />
        <Stat label="FAULTS" value={totalFaults} sub={`${(totalFaults/fleet.length).toFixed(2)}/arm`} color="var(--warn)" />
        <Stat label="AVG CYCLE" value={`${avgCyc}s`} />
        <Stat label="OEE" value="84.2%" sub="↑ 1.1%" color="var(--ok)" />
      </div>
      <div><div className="tag dim">THROUGHPUT · units/min</div><Sparkline data={series1} width={232} height={28} color="var(--ok)" /></div>
      <div style={{ marginTop: 6 }}><div className="tag dim">FAULT RATE · ‰</div><Sparkline data={series2} width={232} height={28} color="var(--warn)" /></div>
    </Panel>
  );
}

// ── ROBOT DETAIL ─────────────────────────────────────────────────────────
function RobotDetailScreen({ robot, onGoto }) {
  if (!robot) return (
    <div className="screen empty">
      <div style={{ textAlign:"center" }}>
        <div className="mono" style={{ fontSize: 18, color: "var(--dim)" }}>NO ARM SELECTED</div>
        <button className="btn primary" style={{ marginTop: 12 }} onClick={() => onGoto("fleet")}>OPEN FLEET MAP</button>
      </div>
    </div>
  );
  const jstate = React.useMemo(() => armJointStateFor(parseInt(robot.id.slice(4)) + 1), [robot.id]);
  const faultIdx = jstate.map((j, i) => j.err ? i : -1).filter(i => i >= 0);
  const cpu = useSeries(parseInt(robot.id.slice(4)) + 1, 80, robot.cpu, 16);
  const net = useSeries(parseInt(robot.id.slice(4)) + 2, 80, 45, 30);
  const tmp = useSeries(parseInt(robot.id.slice(4)) + 3, 80, robot.temp, 4);
  const cur = useSeries(parseInt(robot.id.slice(4)) + 4, 80, 2.4, 3);

  const angles = jstate.map(j => j.pos);

  return (
    <div className="screen robot">
      <div className="robot-grid">
        <Panel title={`◉ ${robot.id} · ${robot.callsign} · KINEMATIC STATE`} right={
          <button className="btn" onClick={() => onGoto("scene")}>OPEN IN 3D CAD ›</button>
        } style={{ gridColumn: "1 / span 2", gridRow: "1 / span 2" }}>
          <div style={{ display: "flex", gap: 14 }}>
            <ArmSideView width={320} height={300} jointAngles={angles} faulty={faultIdx} />
            <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignContent: "start" }}>
              <Stat label="STATUS" value={robot.status} color="var(--ok)" />
              <Stat label="MODE" value="AUTO·EXEC" />
              <Stat label="TOOL" value={robot.tool} />
              <Stat label="PAYLOAD" value={`${robot.payload} kg`} sub={`reach ${robot.reach}m`} />
              <Stat label="TCP SPEED" value={`${robot.tcpSpeed} m/s`} sub="programmed" />
              <Stat label="CYCLE" value={`${robot.cycleTime}s`} sub={`avg`} />
              <Stat label="CORE T°" value={`${robot.temp}°C`} color={robot.temp > 55 ? "var(--warn)" : undefined} />
              <Stat label="UPTIME" value={`${robot.uptime}h`} />
              <Stat label="CPU" value={`${robot.cpu}%`} sub="6 cores · x86" />
              <Stat label="RAM" value={`${robot.ram}%`} sub="16GB DDR4" />
              <div style={{ gridColumn: "1 / -1", display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                <button className="btn primary" onClick={() => onGoto("teleop")}>TELEOP ›</button>
                <button className="btn">RUN</button>
                <button className="btn">PAUSE</button>
                <button className="btn">HOME</button>
                <button className="btn">CALIB·TCP</button>
                <button className="btn danger">E·STOP</button>
              </div>
              <div style={{ gridColumn: "1 / -1" }}>
                <div className="tag dim">CURRENT TCP POSE · base_link</div>
                <div className="tcp-pose">
                  <div><span className="tag dim">X</span> <span className="mono">{robot.tcp.x.toFixed(3)}</span> m</div>
                  <div><span className="tag dim">Y</span> <span className="mono">{robot.tcp.y.toFixed(3)}</span> m</div>
                  <div><span className="tag dim">Z</span> <span className="mono">{robot.tcp.z.toFixed(3)}</span> m</div>
                  <div><span className="tag dim">RX</span> <span className="mono">{robot.tcp.rx.toFixed(1)}</span>°</div>
                  <div><span className="tag dim">RY</span> <span className="mono">{robot.tcp.ry.toFixed(1)}</span>°</div>
                  <div><span className="tag dim">RZ</span> <span className="mono">{robot.tcp.rz.toFixed(1)}</span>°</div>
                </div>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="CAM·HEAD" right={<span className="tag dim">1920×1080 · H.265</span>} pad={false}>
          <CameraFeed label="CELL-CAM" sub="EXP 1/240 · GAIN 16" big />
        </Panel>
        <Panel title="CAM·TOOL" right={<span className="tag dim">D435i</span>} pad={false}>
          <CameraFeed label="TOOL-CAM" sub="DEPTH · 30fps" color="var(--magenta)" scene="grip" big />
        </Panel>

        <Panel title="JOINT STATE · 6 DoF" right={
          <span className="tag dim">UPDATING @ 500Hz</span>
        } style={{ gridColumn: "1 / span 2" }} pad={false}>
          <div className="table-wrap small">
            <table className="dtable">
              <thead>
                <tr><th>JOINT</th><th>POS°</th><th>TGT°</th><th>VEL°/s</th><th>TQ N·m</th><th>A</th><th>T°</th><th>RANGE</th><th>ERR</th></tr>
              </thead>
              <tbody>
                {jstate.map(j => {
                  const pct = (j.pos - j.lo) / (j.hi - j.lo);
                  return (
                    <tr key={j.name} className={j.err ? "row-err" : ""}>
                      <td className="mono" style={{ color: "var(--ok)" }}>{j.name}</td>
                      <td className="mono">{j.pos.toFixed(2)}</td>
                      <td className="mono dim">{j.tgt.toFixed(2)}</td>
                      <td className="mono dim">{j.vel.toFixed(2)}</td>
                      <td className="mono dim">{j.torque.toFixed(2)}</td>
                      <td className="mono dim">{j.current.toFixed(2)}</td>
                      <td className="mono" style={{ color: j.temp > 60 ? "var(--warn)" : "var(--fg-mute)" }}>{j.temp}</td>
                      <td style={{ width: 200 }}>
                        <div style={{ position:"relative", height: 8, background: "var(--track)" }}>
                          <div style={{ position:"absolute", left: 0, right: `${100 - ((0 - j.lo)/(j.hi-j.lo))*100}%`, top: 0, bottom: 0, background: "rgba(120,180,200,.06)" }} />
                          <div style={{ position:"absolute", left: `${pct*100}%`, top: -2, width: 3, height: 12, background: j.err ? "var(--err)" : "var(--ok)" }} />
                          <div style={{ position:"absolute", left: `${((j.tgt - j.lo)/(j.hi - j.lo))*100}%`, top: -2, width: 2, height: 12, background: "var(--info)", opacity: 0.7 }} />
                        </div>
                        <div className="mono dim" style={{ fontSize: 8, display:"flex", justifyContent:"space-between" }}>
                          <span>{j.lo}°</span><span>{j.hi}°</span>
                        </div>
                      </td>
                      <td className="mono" style={{ color: j.err ? "var(--err)" : "var(--dim)" }}>{j.err || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="TELEMETRY · LIVE">
          {[
            ["CPU·LOAD", cpu, "var(--ok)", `${robot.cpu}%`],
            ["NET·THROUGHPUT", net, "var(--info)", `${Math.floor(net[net.length-1])} Mb/s`],
            ["CORE·TEMP", tmp, robot.temp > 55 ? "var(--warn)" : "var(--ok)", `${robot.temp}°C`],
            ["TCP·CURRENT-DRAW", cur, "var(--magenta)", `${(cur[cur.length-1]/10).toFixed(2)} A`],
          ].map(([k, data, color, v]) => (
            <div key={k} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span className="tag dim">{k}</span>
                <span className="mono" style={{ fontSize: 11, color }}>{v}</span>
              </div>
              <Sparkline data={data} width={240} height={26} color={color} />
            </div>
          ))}
        </Panel>

        <Panel title="I/O · DIGITAL & ANALOG" right={<span className="tag dim">128 CH · 1kHz</span>}>
          <div className="tag dim" style={{ marginBottom: 4 }}>DIGITAL · INPUT 0-15</div>
          <div className="iogrid">
            {Array.from({length:16}).map((_,i) => {
              const on = (i*7 + parseInt(robot.id.slice(4))) % 5 < 2;
              return <div key={i} className={"iobit" + (on?" on":"")} title={`DI-${i}`}><span className="mono">{i}</span></div>;
            })}
          </div>
          <div className="tag dim" style={{ marginBottom: 4, marginTop: 8 }}>DIGITAL · OUTPUT 0-15</div>
          <div className="iogrid">
            {Array.from({length:16}).map((_,i) => {
              const on = (i*11 + parseInt(robot.id.slice(4))) % 7 < 3;
              return <div key={i} className={"iobit out" + (on?" on":"")} title={`DO-${i}`}><span className="mono">{i}</span></div>;
            })}
          </div>
          <hr className="hr" />
          <div className="tag dim" style={{ marginBottom: 4 }}>F/T SENSOR · TOOL</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
            <Stat label="FX" value="+ 2.14 N" mono />
            <Stat label="FY" value="− 1.08 N" mono />
            <Stat label="FZ" value="+18.42 N" color="var(--warn)" mono />
            <Stat label="TX" value="0.04 N·m" mono />
            <Stat label="TY" value="0.11 N·m" mono />
            <Stat label="TZ" value="0.02 N·m" mono />
          </div>
        </Panel>
      </div>
    </div>
  );
}

// ── TELEOP · TCP / CARTESIAN ─────────────────────────────────────────────
function JogButton({ label, onClick }) {
  return <button className="jogbtn" onClick={onClick}>{label}</button>;
}

function TeleopScreen({ robot, onGoto }) {
  const [coord, setCoord] = React.useState("BASE");
  const [step, setStep] = React.useState(1);
  const [speed, setSpeed] = React.useState(40);

  if (!robot) return (
    <div className="screen empty">
      <div style={{ textAlign:"center" }}>
        <div className="mono" style={{ fontSize: 18, color: "var(--dim)" }}>SELECT AN ARM TO TELEOP</div>
        <button className="btn primary" style={{ marginTop: 12 }} onClick={() => onGoto("fleet")}>OPEN FLEET MAP</button>
      </div>
    </div>
  );
  const breath = useBreath(99, 600, 1);
  const jstate = React.useMemo(() => armJointStateFor(parseInt(robot.id.slice(4)) + 1), [robot.id]);
  const angles = jstate.map(j => j.pos);

  return (
    <div className="screen teleop-arm">
      <div className="teleop-arm-grid">
        <Panel title={`◉ TELEOP · ${robot.id} · ${robot.callsign}`} right={
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span className="mono" style={{ fontSize: 11, color: "var(--magenta)" }}>● LINK · CTRL TAKEN BY OP·KOSTA</span>
            <span className="mono dim" style={{ fontSize: 10 }}>RTT {robot.latencyMs}ms · JITTER 0.4ms</span>
          </div>
        } pad={false} style={{ gridColumn: "1 / -1", gridRow: "1" }}>
          <div className="teleop-3d">
            <Arm3D jointAngles={angles} width="100%" height={420} reach={robot.reach} />
            <div className="cam-hud-tl mono" style={{ color: "var(--magenta)" }}>● LIVE · TELEOP</div>
            <div className="cam-hud-tr mono dim">{robot.id} · {Math.floor(60 + breath)} fps · {robot.tool}</div>
            <div className="cam-hud-bl mono dim">drag to orbit · scroll to zoom · right-drag to pan</div>
            <div className="cam-hud-br mono" style={{ color: "var(--ok)" }}>VIEW · ISO</div>
          </div>
        </Panel>

        <Panel title="CARTESIAN · TCP JOG">
          <div className="form-row">
            <span className="tag dim">COORDINATE FRAME</span>
            <div style={{ display:"flex", gap: 4 }}>
              {["BASE","TOOL","WORLD","USER"].map(k =>
                <button key={k} className={"chip" + (coord===k?" on":"")} onClick={() => setCoord(k)}>{k}</button>
              )}
            </div>
          </div>
          <div className="jogpad">
            {[
              ["X−", "X+"], ["Y−", "Y+"], ["Z−", "Z+"],
              ["RX−","RX+"], ["RY−","RY+"], ["RZ−","RZ+"],
            ].map(([n, p], i) => (
              <div key={i} className="jogrow">
                <span className="tag dim" style={{ width: 24 }}>{["X","Y","Z","RX","RY","RZ"][i]}</span>
                <JogButton label={n} />
                <div className="mono" style={{ width: 80, textAlign: "center", color: "var(--fg-mute)" }}>
                  {[robot.tcp.x, robot.tcp.y, robot.tcp.z, robot.tcp.rx, robot.tcp.ry, robot.tcp.rz][i]}{i>2?"°":"m"}
                </div>
                <JogButton label={p} />
              </div>
            ))}
          </div>
          <div className="form-row" style={{ marginTop: 8 }}>
            <span className="tag dim">STEP · {step}{["mm","cm","°"][Math.min(2, Math.floor(step/4))]}</span>
            <div style={{ display:"flex", gap: 4 }}>
              {[0.1, 1, 5, 10, 50].map(s => <button key={s} className={"chip" + (step===s?" on":"")} onClick={()=>setStep(s)}>{s}</button>)}
            </div>
          </div>
          <div className="form-row">
            <span className="tag dim">SPEED · {speed}%</span>
            <input type="range" min="1" max="100" value={speed} onChange={e=>setSpeed(+e.target.value)} className="slider" />
          </div>
        </Panel>

        <Panel title="JOINT JOG · J1-J6">
          {jstate.map((j, i) => (
            <div key={j.name} className="jjog">
              <span className="mono" style={{ fontSize: 10, width: 70, color: "var(--ok)" }}>{j.name}</span>
              <button className="jogbtn small">−</button>
              <div style={{ flex: 1, position:"relative", height: 18, background: "var(--track)" }}>
                <div style={{
                  position:"absolute", left: `${((j.pos - j.lo)/(j.hi-j.lo))*100}%`,
                  top: -2, width: 3, height: 22, background: "var(--ok)"
                }} />
              </div>
              <button className="jogbtn small">+</button>
              <span className="mono" style={{ fontSize: 10, width: 60, textAlign: "right" }}>{j.pos.toFixed(1)}°</span>
            </div>
          ))}
          <div style={{ display:"flex", gap:6, marginTop:10 }}>
            <button className="btn primary">HOME</button>
            <button className="btn">FREE-DRIVE</button>
            <button className="btn">RECORD PT</button>
          </div>
        </Panel>

        <Panel title="GRIPPER · TOOL I/O">
          <div className="tag dim">TOOL · {robot.tool}</div>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 6, marginTop: 6 }}>
            <Stat label="WIDTH" value="42.1 mm" mono />
            <Stat label="FORCE" value="38.4 N" color="var(--warn)" mono />
            <Stat label="OBJECT" value="GRASPED" color="var(--ok)" />
            <Stat label="SLIP" value="0.02 mm" mono />
          </div>
          <Bar value={62} color="var(--info)" height={10} showVal />
          <div style={{ display:"flex", gap: 4, marginTop: 8, flexWrap:"wrap" }}>
            <button className="chip on">OPEN</button>
            <button className="chip">CLOSE</button>
            <button className="chip">10mm</button>
            <button className="chip">50mm</button>
            <button className="chip">100mm</button>
          </div>
          <hr className="hr" />
          <div className="tag dim">SAFETY · INTERLOCKS</div>
          {[
            ["WORKSPACE","OK","var(--ok)"],
            ["FORCE LIMIT","OK","var(--ok)"],
            ["SINGULARITY","NEAR · J5","var(--warn)"],
            ["HUMAN-PROX","1.4m · OK","var(--ok)"],
            ["DEADMAN","HELD","var(--ok)"],
          ].map(([k,v,c]) =>
            <div key={k} style={{ display:"flex", justifyContent:"space-between", padding:"3px 0", borderBottom:"1px solid var(--border)" }}>
              <span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span>
              <span className="mono" style={{ fontSize: 10, color: c }}>{v}</span>
            </div>
          )}
          <button className="btn danger" style={{ width:"100%", marginTop: 10, fontSize: 13, padding: "8px" }}>⏻ EMERGENCY STOP</button>
        </Panel>
      </div>
    </div>
  );
}

// ── SCENE · FULL 3D CAD ──────────────────────────────────────────────────
function SceneScreen({ robot }) {
  const [autoRot, setAutoRot] = React.useState(false);
  const [showWS, setShowWS] = React.useState(true);
  const [showGrid, setShowGrid] = React.useState(true);
  const jstate = React.useMemo(
    () => robot ? armJointStateFor(parseInt(robot.id.slice(4)) + 1) : null,
    [robot && robot.id]
  );
  const angles = jstate ? jstate.map(j => j.pos) : [0, -60, 90, 0, 40, 0];
  const faultIdx = jstate ? jstate.map((j, i) => j.err ? i : -1).filter(i => i >= 0) : [];

  return (
    <div className="screen scene-arm">
      <Panel title="3D CAD · KINEMATIC SCENE · LIVE" right={
        <div style={{ display:"flex", gap: 6 }}>
          <button className={"chip" + (showGrid?" on":"")} onClick={()=>setShowGrid(!showGrid)}>GRID</button>
          <button className={"chip" + (showWS?" on":"")} onClick={()=>setShowWS(!showWS)}>WORKSPACE</button>
          <button className={"chip" + (autoRot?" on":"")} onClick={()=>setAutoRot(!autoRot)}>AUTO·ROTATE</button>
          <button className="chip">SHADED</button>
          <button className="chip">WIREFRAME</button>
          <button className="chip">X-RAY</button>
        </div>
      } pad={false} style={{ gridColumn: "1 / span 3" }}>
        <div className="scene-3d" key={showWS + "" + showGrid}>
          <Arm3D
            jointAngles={angles}
            faulty={faultIdx}
            showWorkspace={showWS}
            showGrid={showGrid}
            reach={robot ? robot.reach : 1.0}
            autoRotate={autoRot}
            width="100%"
            height="100%"
          />
          {/* HUD */}
          <div className="floor-hud tl">
            <Crosshair color="var(--ok)" />
            <div>
              <div className="tag dim">SUBJECT</div>
              <div className="mono" style={{ fontSize: 12, color: "var(--ok)" }}>{robot ? `${robot.id} · ${robot.callsign}` : "—"}</div>
              <div className="tag dim" style={{ marginTop: 2 }}>{robot ? `URDF · 6 DoF · reach ${robot.reach}m` : ""}</div>
            </div>
          </div>
          <div className="floor-hud tr">
            <div>
              <div className="tag dim">VIEW</div>
              <div className="mono" style={{ fontSize: 11 }}>ISO · 40° FoV</div>
            </div>
            <div style={{ display:"flex", gap: 4 }}>
              <button className="chip">FRONT</button>
              <button className="chip">SIDE</button>
              <button className="chip">TOP</button>
              <button className="chip on">ISO</button>
            </div>
          </div>
          <div className="floor-hud bl">
            <div className="mono dim" style={{ fontSize: 10 }}>L · ORBIT</div>
            <div className="mono dim" style={{ fontSize: 10 }}>R · PAN</div>
            <div className="mono dim" style={{ fontSize: 10 }}>SCROLL · ZOOM</div>
          </div>
          <div className="floor-hud br">
            <div className="mono dim" style={{ fontSize: 10 }}>FRAME RATE</div>
            <div className="mono" style={{ fontSize: 11, color: "var(--ok)" }}>60.0 fps</div>
          </div>
        </div>
      </Panel>

      <Panel title="LAYERS · SCENE">
        {["BASE FRAME","TCP FRAME","LINK MESHES","JOINT AXES","WORKSPACE","COLLISION HULLS","TRAJECTORY","WAYPOINTS","COLLISION OBJECTS","NAMED POSES","REACHABILITY MAP"].map((l, i) =>
          <label key={l} className="row">
            <input type="checkbox" defaultChecked={i < 5} />
            <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)" }}>{l}</span>
          </label>
        )}
      </Panel>

      <Panel title="JOINT ANGLES · LIVE" right={<span className="tag dim">REAL-TIME · 500Hz</span>} style={{ gridColumn: "1 / span 2" }}>
        {jstate ? jstate.map((j, i) => {
          const pct = (j.pos - j.lo) / (j.hi - j.lo);
          return (
            <div key={j.name} style={{ marginBottom: 8 }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom: 2 }}>
                <span className="mono" style={{ fontSize: 10, color: j.err ? "var(--err)" : "var(--ok)" }}>{j.name}</span>
                <span className="mono" style={{ fontSize: 10 }}>{j.pos.toFixed(2)}°</span>
              </div>
              <div style={{ position:"relative", height: 6, background: "var(--track)" }}>
                <div style={{ position:"absolute", left: `${pct*100}%`, top: -2, width: 2, height: 10, background: j.err ? "var(--err)" : "var(--ok)" }} />
                <div style={{ position:"absolute", left: `${((-j.lo)/(j.hi - j.lo))*100}%`, top: 0, bottom: 0, width: 1, background: "rgba(255,255,255,.18)" }} />
              </div>
            </div>
          );
        }) : <div className="dim mono" style={{ fontSize: 11 }}>No arm selected</div>}
      </Panel>

      <Panel title="TCP · POSE" style={{ gridColumn: "3 / span 2" }}>
        {robot && (
          <>
            <div className="tcp-pose">
              <div><span className="tag dim">X</span> <span className="mono" style={{ color: "var(--err)" }}>{robot.tcp.x.toFixed(3)}</span> m</div>
              <div><span className="tag dim">Y</span> <span className="mono" style={{ color: "var(--ok)" }}>{robot.tcp.y.toFixed(3)}</span> m</div>
              <div><span className="tag dim">Z</span> <span className="mono" style={{ color: "var(--info)" }}>{robot.tcp.z.toFixed(3)}</span> m</div>
              <div><span className="tag dim">RX</span> <span className="mono">{robot.tcp.rx.toFixed(1)}</span>°</div>
              <div><span className="tag dim">RY</span> <span className="mono">{robot.tcp.ry.toFixed(1)}</span>°</div>
              <div><span className="tag dim">RZ</span> <span className="mono">{robot.tcp.rz.toFixed(1)}</span>°</div>
            </div>
            <hr className="hr" />
            <div className="tag dim">DH PARAMETERS</div>
            <table className="dhtable">
              <thead><tr><th>i</th><th>θ</th><th>d</th><th>a</th><th>α</th></tr></thead>
              <tbody>
                {[
                  [1, "θ₁", 0.163, 0,     90],
                  [2, "θ₂", 0,    -0.42, 0],
                  [3, "θ₃", 0,    -0.39, 0],
                  [4, "θ₄", 0.13, 0,     90],
                  [5, "θ₅", 0.10, 0,    -90],
                  [6, "θ₆", 0.10, 0,     0],
                ].map(row => (
                  <tr key={row[0]}>
                    {row.map((c, i) => <td key={i} className="mono dim" style={{ fontSize: 10 }}>{c}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Panel>
    </div>
  );
}

// ── TASKS / PROGRAMS ─────────────────────────────────────────────────────
function TasksScreen({ fleet, onSelect }) {
  const missions = React.useMemo(() => [
    { id: "JOB-4421", name: "PALLETIZE · LAYER-3 · 48 cycles", pri: "P1", state: "RUNNING",  prog: 64, assignee: fleet[0]?.id, eta: "12:42", wp: 48, started: "06:02:18" },
    { id: "JOB-4420", name: "WELD-SEAM · PART-V4 · BATCH 12", pri: "P0", state: "RUNNING",  prog: 38, assignee: fleet[1]?.id, eta: "13:18", wp: 12, started: "06:08:42" },
    { id: "JOB-4419", name: "ASSEMBLE · MOTOR-V4 · KIT-A",     pri: "P2", state: "RUNNING",  prog: 88, assignee: fleet[2]?.id, eta: "12:34", wp: 24, started: "05:14:09" },
    { id: "JOB-4418", name: "INSPECT · LINE-2 · QA-PASS-3",    pri: "P1", state: "RUNNING",  prog: 22, assignee: fleet[3]?.id, eta: "13:44", wp: 96, started: "06:21:51" },
    { id: "JOB-4417", name: "GLUE-BEAD · GASKET · 240 parts",  pri: "P3", state: "QUEUED",   prog: 0,  assignee: "—", eta: "13:01", wp: 240, started: "—" },
    { id: "JOB-4416", name: "DRILL · 14 × M5",                  pri: "P3", state: "QUEUED",   prog: 0,  assignee: "—", eta: "12:58", wp: 14, started: "—" },
    { id: "JOB-4415", name: "PALLETIZE · LAYER-2 · DONE",       pri: "P1", state: "DONE",     prog: 100,assignee: fleet[0]?.id, eta: "—", wp: 48, started: "05:42:12" },
    { id: "JOB-4414", name: "DISPENSE · ADHESIVE · OP-20",      pri: "P2", state: "FAILED",   prog: 41, assignee: fleet[6]?.id, eta: "—", wp: 36, started: "05:36:30" },
    { id: "JOB-4413", name: "POLISH · FLANGE · 18 parts",       pri: "P2", state: "DONE",     prog: 100,assignee: fleet[7]?.id, eta: "—", wp: 18, started: "05:11:08" },
  ], [fleet]);
  const sc = { RUNNING:"var(--ok)", QUEUED:"var(--info)", DONE:"var(--fg-mute)", FAILED:"var(--err)" };
  const pc = { P0:"var(--err)", P1:"var(--warn)", P2:"var(--info)", P3:"var(--fg-mute)" };

  return (
    <div className="screen tasks">
      <div className="tasks-grid">
        <Panel title="JOB QUEUE · 9 PROGRAMS" right={
          <div style={{ display:"flex", gap: 6 }}>
            <button className="chip on">ALL</button>
            <button className="chip">RUNNING</button>
            <button className="chip">QUEUED</button>
            <button className="chip">FAILED</button>
            <button className="btn primary" style={{ marginLeft: 8 }}>+ NEW PROGRAM</button>
          </div>
        } pad={false} style={{ gridColumn: "1 / span 2" }}>
          <div className="table-wrap">
            <table className="dtable">
              <thead><tr>
                <th style={{ width:80 }}>ID</th><th style={{ width:50 }}>PRI</th><th style={{ width:90 }}>STATE</th>
                <th>PROGRAM</th><th style={{ width:90 }}>ASSIGNEE</th><th style={{ width:60 }}>UNITS</th>
                <th style={{ width:220 }}>PROGRESS</th><th style={{ width:70 }}>ETA</th>
              </tr></thead>
              <tbody>
                {missions.map(m => (
                  <tr key={m.id}>
                    <td className="mono">{m.id}</td>
                    <td className="mono" style={{ color: pc[m.pri] }}>{m.pri}</td>
                    <td className="mono" style={{ color: sc[m.state] }}>
                      <StatusDot status={m.state==="RUNNING"?"ACTIVE":m.state==="FAILED"?"FAULT":"IDLE"} size={6} />
                      <span style={{ marginLeft: 6 }}>{m.state}</span>
                    </td>
                    <td className="mono">{m.name}</td>
                    <td className="mono" style={{ cursor: m.assignee!=="—"?"pointer":"default", color: "var(--info)" }}
                        onClick={() => m.assignee!=="—" && onSelect(m.assignee)}>{m.assignee || "—"}</td>
                    <td className="mono dim">{m.wp}</td>
                    <td>
                      <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                        <Bar value={m.prog} color={sc[m.state]} />
                        <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)", minWidth: 26 }}>{m.prog}%</span>
                      </div>
                    </td>
                    <td className="mono dim">{m.eta}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="TIMELINE · 06:00 → 14:00" right={<span className="tag dim">UTC</span>} pad={false} style={{ gridColumn: "1 / span 2" }}>
          <div className="gantt">
            <div className="gantt-axis">
              {Array.from({ length: 9 }).map((_, i) => (
                <div key={i} className="gantt-tick">
                  <span className="mono dim" style={{ fontSize: 10 }}>{String(6+i).padStart(2,"0")}:00</span>
                </div>
              ))}
            </div>
            {missions.filter(m => m.state !== "QUEUED").map((m) => {
              const startH = m.started === "—" ? 6 : parseInt(m.started.slice(0,2)) + parseInt(m.started.slice(3,5))/60;
              const left = ((startH - 6) / 8) * 100;
              const width = Math.max(4, (m.prog/100 * 1.5)) * 4;
              return (
                <div key={m.id} className="gantt-row">
                  <div className="gantt-label mono">{m.assignee || m.id}</div>
                  <div className="gantt-track">
                    <div className="gantt-bar" style={{ left: `${left}%`, width: `${width}%`, background: sc[m.state] }}>
                      <span className="mono" style={{ fontSize: 9, padding: "0 4px" }}>{m.id}</span>
                    </div>
                  </div>
                </div>
              );
            })}
            <div className="gantt-now" style={{ left: `${((6.5 - 6) / 8) * 100}%` }}>
              <span className="mono" style={{ fontSize: 9, color: "var(--err)" }}>NOW</span>
            </div>
          </div>
        </Panel>

        <Panel title="PROGRAM COMPOSER · NEW">
          <div className="form-row"><span className="tag dim">NAME</span><input className="inp" defaultValue="PICK-PLACE · BIN-A7" /></div>
          <div className="form-row"><span className="tag dim">PRIORITY</span>
            <div style={{ display:"flex", gap: 4 }}>{["P0","P1","P2","P3"].map((p,i) =>
              <button key={p} className={"chip" + (i===1?" on":"")} style={{ color: pc[p] }}>{p}</button>)}</div>
          </div>
          <div className="form-row"><span className="tag dim">ASSIGNEE</span>
            <select className="inp">
              <option>AUTO · FIRST AVAILABLE</option>
              {fleet.slice(0,8).map(r => <option key={r.id}>{r.id} · {r.callsign}</option>)}
            </select>
          </div>
          <div className="form-row"><span className="tag dim">START</span><input className="inp" defaultValue="ASAP" /></div>
          <div className="form-row"><span className="tag dim">UNITS</span><input className="inp" defaultValue="48" /></div>
          <div className="form-row"><span className="tag dim">CONSTRAINTS</span>
            <div style={{ display:"flex", gap: 4, flexWrap:"wrap" }}>
              <button className="chip on">SAFE-SPEED</button>
              <button className="chip on">FORCE-LIMIT</button>
              <button className="chip">PRECISION</button>
              <button className="chip">FAST</button>
            </div>
          </div>
          <button className="btn primary" style={{ width: "100%", marginTop: 8 }}>QUEUE PROGRAM ›</button>
        </Panel>

        <Panel title="ARM AVAILABILITY">
          <div className="tag dim" style={{ marginBottom: 6 }}>READY · NOW</div>
          {fleet.filter(r => r.status === "IDLE").slice(0, 6).map(r => (
            <div key={r.id} className="avail-row" onClick={() => onSelect(r.id)}>
              <StatusDot status="IDLE" size={6} />
              <span className="mono" style={{ fontSize: 11 }}>{r.id}</span>
              <span style={{ fontSize: 10, color: "var(--fg-mute)" }}>{r.callsign}</span>
              <span className="mono dim" style={{ fontSize: 10, marginLeft: "auto" }}>{r.tool}</span>
            </div>
          ))}
          <hr className="hr" />
          <div className="tag dim" style={{ marginBottom: 6 }}>FREE AFTER · CURRENT</div>
          {fleet.filter(r => r.status === "ACTIVE").slice(0, 5).map(r => (
            <div key={r.id} className="avail-row" onClick={() => onSelect(r.id)}>
              <StatusDot status="ACTIVE" size={6} />
              <span className="mono" style={{ fontSize: 11 }}>{r.id}</span>
              <span style={{ fontSize: 10, color: "var(--fg-mute)" }}>{r.callsign}</span>
              <span className="mono dim" style={{ fontSize: 10, marginLeft: "auto" }}>~{Math.floor(4 + (parseInt(r.id.slice(4))%30))}m</span>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

// ── ANALYTICS ────────────────────────────────────────────────────────────
function BigChart({ data, color, label, height = 100 }) {
  if (!data?.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => [(i/(data.length-1))*800, height - ((v-min)/range)*(height-10) - 5]);
  const path = pts.map((p,i)=>(i?"L":"M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const area = path + ` L800,${height} L0,${height} Z`;
  return (
    <svg viewBox={`0 0 800 ${height}`} preserveAspectRatio="none" style={{ width: "100%", height, display: "block" }}>
      <defs><linearGradient id={"bc"+label} x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stopColor={color} stopOpacity="0.3" />
        <stop offset="100%" stopColor={color} stopOpacity="0" />
      </linearGradient></defs>
      {[0.25,0.5,0.75].map(p => <line key={p} x1="0" y1={height*p} x2="800" y2={height*p} stroke="rgba(120,180,200,.08)" />)}
      <path d={area} fill={`url(#bc${label})`} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.4" />
    </svg>
  );
}

function AnalyticsScreen({ fleet }) {
  const s1 = useSeries(101, 120, 65, 18);
  const s2 = useSeries(102, 120, 30, 24);
  const s4 = useSeries(104, 120, 42, 32);
  const counts = { ACTIVE:0,IDLE:0,TELEOP:0,FAULT:0,OFFLINE:0 };
  fleet.forEach(r => counts[r.status]++);
  const total = fleet.length;
  return (
    <div className="screen analytics">
      <div className="kpi-row">
        <Panel><Stat label="UNITS · 24H" value="38,412" sub="+8.4% vs prev" color="var(--ok)" /></Panel>
        <Panel><Stat label="OEE · FLEET" value="84.2%" sub="SLA 85.0%" color="var(--warn)" /></Panel>
        <Panel><Stat label="MTBF" value="612h" sub="up from 584h" color="var(--ok)" /></Panel>
        <Panel><Stat label="ENERGY · 24H" value="142 kWh" sub="$17.20 grid" /></Panel>
        <Panel><Stat label="FAULTS · 24H" value="22" sub="−8 vs avg" color="var(--ok)" /></Panel>
        <Panel><Stat label="TELEOP · 24H" value="1.2 h" sub="1.4% of runtime" /></Panel>
      </div>

      <Panel title="THROUGHPUT · UNITS/HOUR · LAST 48H" right={<span className="tag dim">120 SAMPLES · BIN=24min</span>}>
        <BigChart data={s1} color="#4ade80" label="thrupt" height={160} />
      </Panel>

      <div className="analytics-grid">
        <Panel title="FAULT MODES · ‰" right={<span className="tag dim">7 DAYS</span>}>
          <BigChart data={s2} color="#fbbf24" label="fault" height={120} />
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 8, marginTop: 8 }}>
            <Stat label="COLLISION" value="0.18" sub="all auto-recovered" />
            <Stat label="SINGULARITY" value="0.42" sub="↑" color="var(--warn)" />
            <Stat label="GRIP-MISS" value="0.31" sub="↑" color="var(--warn)" />
            <Stat label="OVERTEMP" value="0.04" sub="stable" />
          </div>
        </Panel>
        <Panel title="ENERGY · kWh · PER ARM">
          <div className="hbars">
            {fleet.slice(0, 12).map((r, i) => {
              const v = 2 + (i * 0.4) % 6;
              return (
                <div key={r.id} className="hbar-row">
                  <span className="mono" style={{ fontSize: 10, width: 70 }}>{r.id}</span>
                  <div style={{ flex: 1, height: 12, background: "var(--track)" }}>
                    <div style={{ height: "100%", width: `${(v/8)*100}%`, background: "var(--info)" }} />
                  </div>
                  <span className="mono dim" style={{ fontSize: 10, width: 36, textAlign: "right" }}>{v.toFixed(1)}</span>
                </div>
              );
            })}
          </div>
        </Panel>
        <Panel title="STATUS · NOW">
          {[
            ["ACTIVE",counts.ACTIVE,"var(--ok)"],
            ["IDLE",counts.IDLE,"var(--fg-mute)"],
            ["TELEOP",counts.TELEOP,"var(--magenta)"],
            ["FAULT",counts.FAULT,"var(--err)"],
            ["OFFLINE",counts.OFFLINE,"var(--off)"],
          ].map(([k, n, c]) => (
            <div key={k} style={{ marginBottom: 8 }}>
              <div style={{ display:"flex", justifyContent:"space-between" }}>
                <span className="tag" style={{ color: c }}>{k}</span>
                <span className="mono" style={{ fontSize: 10, color: c }}>{n}/{total} · {((n/total)*100).toFixed(0)}%</span>
              </div>
              <Bar value={n} max={total} color={c} height={6} />
            </div>
          ))}
        </Panel>
        <Panel title="NETWORK · LATENCY · ms">
          <BigChart data={s4} color="#38bdf8" label="lat" height={120} />
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap: 8, marginTop: 8 }}>
            <Stat label="p50" value="6 ms" /><Stat label="p95" value="22 ms" /><Stat label="p99" value="48 ms" color="var(--warn)" />
            <Stat label="JITTER" value="0.4 ms" /><Stat label="LOSS" value="0.01%" color="var(--ok)" /><Stat label="OOO" value="0.00%" color="var(--ok)" />
          </div>
        </Panel>
        <Panel title="JOINT FAILURES · 30 DAYS" style={{ gridColumn: "1 / span 2" }}>
          <div className="heatmap heatmap-6">
            {JOINTS6.map(([name], i) => {
              const intensity = ((i * 23 + 11) % 100) / 100;
              return (
                <div key={name} className="heat-cell" title={name}
                  style={{ background: `rgba(239,68,68, ${intensity})` }}>
                  <span className="mono" style={{ fontSize: 10, color: intensity > 0.5 ? "#fff" : "var(--fg-mute)" }}>{name}</span>
                  <span className="mono" style={{ fontSize: 14, fontWeight: 600, color: intensity > 0.5 ? "#fff" : "var(--fg)" }}>{Math.floor(intensity * 32)}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}

// ── LOGS ─────────────────────────────────────────────────────────────────
function LogsScreen({ alerts }) {
  const fullLog = React.useMemo(() => {
    const out = [];
    const srcs = ["ARM-003","ARM-008","ARM-011","ARM-014","ARM-022","ARM-007","FLEET","OPS","KIN","PERCEPT","CTRL","SAFETY"];
    const tmpl = [
      "joint state published · 6 DoF",
      "TF base_link→tcp0 · delta 0.{n}mm",
      "joint J{n} torque {n}.{n} N·m",
      "Program step {n} of 48 complete · cycle {n}.{n}s",
      "F/T sensor zeroed · offset 0.1N",
      "IK solved · 14 wp · 0.84s",
      "Heartbeat ACK · seq 0x{n}{n}A4",
      "TCP velocity {n}.{n}{n} m/s",
      "Object detected · BIN-RED · conf 0.98",
      "PID gains updated · J{n}",
      "Network: rtt {n}ms · loss 0%",
      "Self-test step {n} · PASS",
      "Cell-cam exposure auto · gain {n}",
      "Path planner: re-route +0.2s",
      "Singularity check · cond {n}.{n}",
    ];
    const sevs = ["DEBUG","DEBUG","DEBUG","INFO","INFO","INFO","INFO","OK","WARN","ERR"];
    let t = 6*3600 + 14*60 + 22;
    for (let i = 0; i < 80; i++) {
      const r = (i * 9301 + 49297) % 233280 / 233280;
      const msg = tmpl[Math.floor(r * tmpl.length)].replace(/\{n\}/g, () => Math.floor(r * 9));
      out.push({
        ts: `${String(Math.floor(t/3600)).padStart(2,"0")}:${String(Math.floor((t%3600)/60)).padStart(2,"0")}:${String(t%60).padStart(2,"0")}.${String(Math.floor(r*999)).padStart(3,"0")}`,
        sev: sevs[Math.floor(r * sevs.length)],
        src: srcs[Math.floor(r * srcs.length)],
        msg,
        topic: ["/joint_states","/tf","/tcp_pose","/cmd_vel","/diagnostics","/perception/dets","/ft_sensor"][Math.floor(r * 7)],
      });
      t -= Math.floor(r * 8) + 1;
    }
    return out;
  }, []);
  const [filter, setFilter] = React.useState("ALL");
  const filtered = filter === "ALL" ? fullLog : fullLog.filter(l => l.sev === filter);

  return (
    <div className="screen logs">
      <Panel title="EVENT STREAM · tail -f /var/log/arm-ops.log" right={
        <div style={{ display: "flex", gap: 6 }}>
          {["ALL","ERR","WARN","INFO","DEBUG","OK"].map(k =>
            <button key={k} className={"chip" + (filter === k ? " on" : "")} onClick={() => setFilter(k)}>{k}</button>
          )}
          <input className="inp" placeholder="grep ›" style={{ width: 140, marginLeft: 6 }} />
        </div>
      } pad={false} style={{ gridColumn: "1 / span 3" }}>
        <div className="logstream">
          {filtered.map((l, i) => (
            <div key={i} className="logline">
              <span className="mono dim" style={{ fontSize: 10 }}>{l.ts}</span>
              <span className={`sev sev-${l.sev}`}>{l.sev}</span>
              <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)", width: 80 }}>{l.src}</span>
              <span className="mono" style={{ fontSize: 10, color: "var(--info)", width: 150 }}>{l.topic}</span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--fg)" }}>{l.msg}</span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="ALERT INBOX">
        {alerts.map((a, i) => (
          <div key={i} className="alert">
            <span className={`sev sev-${a.sev}`}>{a.sev}</span>
            <span className="mono dim" style={{ fontSize: 10 }}>{a.ts}</span>
            <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)" }}>{a.src}</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--fg)" }}>{a.msg}</span>
          </div>
        ))}
      </Panel>
      <Panel title="TOPICS · RATES">
        {[
          ["/joint_states","500 Hz","var(--ok)"],["/tf","100 Hz","var(--ok)"],
          ["/tcp_pose","500 Hz","var(--ok)"],["/cmd_vel","250 Hz","var(--ok)"],
          ["/diagnostics","1 Hz","var(--ok)"],["/camera/cell/image_raw","30 Hz","var(--ok)"],
          ["/camera/tool/depth","30 Hz","var(--warn)"],["/perception/dets","10 Hz","var(--ok)"],
          ["/ft_sensor","1000 Hz","var(--ok)"],
        ].map(([t,hz,c]) => (
          <div key={t} className="topic-row">
            <span className="mono" style={{ fontSize: 10.5, color: "var(--info)" }}>{t}</span>
            <span className="mono" style={{ fontSize: 10, color: c }}>{hz}</span>
          </div>
        ))}
      </Panel>
      <Panel title="DIAGNOSTIC TREE">
        <div className="diag-tree">
          {[
            ["▼","FLEET","30 arms","var(--ok)"],
            ["  ▼","ARM-003 · ORION","OK","var(--ok)"],
            ["    ▸","HARDWARE","OK","var(--ok)"],
            ["    ▸","KINEMATICS","OK","var(--ok)"],
            ["    ▼","CONTROL","WARN","var(--warn)"],
            ["      ◦","PID·J3","sat. 1.2s","var(--warn)"],
            ["    ▸","SAFETY","OK","var(--ok)"],
            ["  ▸","ARM-008 · APOLLO","OK","var(--ok)"],
            ["  ▼","ARM-022 · TARTARUS","ERR","var(--err)"],
            ["    ▼","HARDWARE","ERR","var(--err)"],
            ["      ◦","J4·ENCODER","CRC fail","var(--err)"],
          ].map(([prefix, name, val, c], i) => (
            <div key={i} className="diag-row">
              <span className="mono" style={{ fontSize: 10, color: "var(--dim)", whiteSpace:"pre" }}>{prefix}</span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--fg)" }}>{name}</span>
              <span className="mono" style={{ fontSize: 10, color: c, marginLeft: "auto" }}>{val}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

// ── SETTINGS · per arm ───────────────────────────────────────────────────
function SettingsScreen({ robot, onGoto }) {
  if (!robot) return (
    <div className="screen empty">
      <div style={{ textAlign:"center" }}>
        <div className="mono" style={{ fontSize: 18, color: "var(--dim)" }}>NO ARM SELECTED</div>
        <button className="btn primary" style={{ marginTop: 12 }} onClick={() => onGoto("fleet")}>OPEN FLEET MAP</button>
      </div>
    </div>
  );
  return (
    <div className="screen settings">
      <div className="settings-grid">
        <Panel title={`CONFIG · ${robot.id} · ${robot.callsign}`}>
          <div className="form-row"><span className="tag dim">CALLSIGN</span><input className="inp" defaultValue={robot.callsign} /></div>
          <div className="form-row"><span className="tag dim">HOSTNAME</span><input className="inp" defaultValue={`${robot.id.toLowerCase()}.cell.lan`} /></div>
          <div className="form-row"><span className="tag dim">IP·v4</span><input className="inp" defaultValue={`10.42.0.${parseInt(robot.id.slice(4))}`} /></div>
          <div className="form-row"><span className="tag dim">FIRMWARE</span><input className="inp" defaultValue={robot.fw} /></div>
          <div className="form-row"><span className="tag dim">CELL</span><input className="inp" defaultValue={robot.zone} /></div>
          <div className="form-row"><span className="tag dim">TOOL</span>
            <select className="inp" defaultValue={robot.tool}>
              <option>GRIPPER-2F</option><option>GRIPPER-3F</option><option>SUCTION</option>
              <option>WELDER-MIG</option><option>DISPENSER</option><option>DRILL-T7</option>
            </select>
          </div>
          <div className="form-row"><span className="tag dim">MODE</span>
            <div style={{ display:"flex", gap: 4 }}>
              {["AUTONOMOUS","ASSIST","MANUAL","SHADOW"].map((m,i) => <button key={m} className={"chip" + (i===0?" on":"")}>{m}</button>)}
            </div>
          </div>
        </Panel>

        <Panel title="CONTROL · PID PER JOINT">
          {JOINTS6.map(([j]) => (
            <div key={j} className="pid-row">
              <span className="mono dim" style={{ fontSize: 10, width: 110 }}>{j}</span>
              {[["KP",24.4],["KI",0.18],["KD",1.92]].map(([k,v]) => (
                <div key={k} style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <span className="tag dim" style={{ fontSize: 9 }}>{k}</span>
                  <input className="inp" defaultValue={v} style={{ width: 56 }} />
                </div>
              ))}
            </div>
          ))}
          <button className="btn primary" style={{ width:"100%", marginTop: 8 }}>APPLY · LIVE</button>
        </Panel>

        <Panel title="SAFETY · LIMITS">
          {[
            ["MAX TCP VELOCITY", "1.50 m/s"],
            ["MAX TCP ACCEL",    "2.50 m/s²"],
            ["MAX JOINT VEL",    "180 °/s"],
            ["MAX TORQUE · ARM", "60 N·m"],
            ["FORCE LIMIT · TCP","40 N"],
            ["HUMAN STOP-DIST",  "0.50 m"],
            ["WORKSPACE",        robot.zone],
            ["GEOFENCE · X",     "−1.0…+1.0 m"],
            ["GEOFENCE · Z",     "0.05…1.20 m"],
          ].map(([k, v]) => (
            <div key={k} className="form-row" style={{ flexDirection:"row", alignItems:"center" }}>
              <span className="tag dim" style={{ flex: 1 }}>{k}</span>
              <input className="inp" defaultValue={v} style={{ width: 160 }} />
            </div>
          ))}
        </Panel>

        <Panel title="TCP CALIBRATION">
          <div className="form-row"><span className="tag dim">METHOD</span>
            <div style={{ display:"flex", gap: 4 }}>{["4-POINT","SPHERE","FREE-DRIVE"].map((m,i) =>
              <button key={m} className={"chip" + (i===0?" on":"")}>{m}</button>)}</div>
          </div>
          <div className="tag dim">CURRENT TCP · TOOL FRAME</div>
          <div className="tcp-pose">
            <div><span className="tag dim">X</span> <span className="mono">0.000</span> m</div>
            <div><span className="tag dim">Y</span> <span className="mono">0.000</span> m</div>
            <div><span className="tag dim">Z</span> <span className="mono">0.158</span> m</div>
            <div><span className="tag dim">RX</span> <span className="mono">0.00</span>°</div>
            <div><span className="tag dim">RY</span> <span className="mono">0.00</span>°</div>
            <div><span className="tag dim">RZ</span> <span className="mono">0.00</span>°</div>
          </div>
          <hr className="hr" />
          <div className="tag dim">PAYLOAD MASS</div>
          <input className="inp" defaultValue={`${robot.payload} kg`} />
          <div style={{ display:"flex", gap:6, marginTop:10 }}>
            <button className="btn primary">RUN CALIB</button>
            <button className="btn">EXPORT</button>
          </div>
        </Panel>

        <Panel title="SENSORS · ENABLE">
          {[
            ["CELL CAM · WIDE", true],["CELL CAM · TELE", true],
            ["TOOL CAM · D435i", true],["F/T · TCP", true],
            ["LIGHT-CURTAIN · ENTRY", true],["LASER-SCANNER · 270°", true],
            ["TORQUE EST · J1-6", true],["VIBRATION · BASE", false],
            ["MICROPHONE", false],
          ].map(([k, on]) => (
            <div key={k} className="form-row" style={{ flexDirection: "row", alignItems:"center", justifyContent:"space-between" }}>
              <span className="tag" style={{ color: on ? "var(--fg)" : "var(--dim)" }}>{k}</span>
              <div className={"switch" + (on ? " on" : "")}><div className="switch-thumb" /></div>
            </div>
          ))}
        </Panel>

        <Panel title="OTA · DEPLOYMENT">
          <div className="form-row"><span className="tag dim">CHANNEL</span>
            <div style={{ display:"flex", gap: 4 }}>{["STABLE","BETA","NIGHTLY"].map((m,i) =>
              <button key={m} className={"chip" + (i===0?" on":"")}>{m}</button>)}</div>
          </div>
          <div className="form-row" style={{ flexDirection:"row", justifyContent:"space-between" }}>
            <span className="tag dim">CURRENT</span>
            <div className="mono" style={{ fontSize: 11 }}>{robot.fw} · STABLE</div>
          </div>
          <div className="form-row" style={{ flexDirection:"row", justifyContent:"space-between" }}>
            <span className="tag dim">AVAILABLE</span>
            <div className="mono" style={{ fontSize: 11, color: "var(--info)" }}>ARC-5.22.4 · 18 commits ahead</div>
          </div>
          <Bar value={0} color="var(--info)" height={4} />
          <div style={{ display:"flex", gap: 6, marginTop: 10 }}>
            <button className="btn primary">STAGE</button>
            <button className="btn">ROLL BACK</button>
            <button className="btn">FORCE REBOOT</button>
          </div>
        </Panel>
      </div>
    </div>
  );
}

Object.assign(window, {
  FleetScreen, RobotDetailScreen, TeleopScreen, SceneScreen,
  TasksScreen, AnalyticsScreen, LogsScreen, SettingsScreen,
});
