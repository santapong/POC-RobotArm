// screen-aux.jsx — Tasks, Analytics, Logs, Settings

function TasksScreen({ fleet, onSelect }) {
  const missions = [
    { id: "M-4421", name: "BIN-PICK · LINE-2 BATCH 17", pri: "P1", state: "RUNNING",  prog: 64, assignee: "H-003", eta: "12:42", wp: 12, started: "06:02:18" },
    { id: "M-4420", name: "PALLET XFER · DOCK→KITTING", pri: "P0", state: "RUNNING",  prog: 38, assignee: "H-008", eta: "13:18", wp: 8,  started: "06:08:42" },
    { id: "M-4419", name: "KIT ASSEMBLY · MOTOR-V4",    pri: "P2", state: "RUNNING",  prog: 88, assignee: "H-011", eta: "12:34", wp: 24, started: "05:14:09" },
    { id: "M-4418", name: "INSPECT LINE-2 · QA PASS",    pri: "P1", state: "RUNNING",  prog: 22, assignee: "H-014", eta: "13:44", wp: 16, started: "06:21:51" },
    { id: "M-4417", name: "TOOLCHANGE · T3 → T7",         pri: "P3", state: "QUEUED",   prog: 0,  assignee: "—",     eta: "13:01", wp: 4,  started: "—" },
    { id: "M-4416", name: "WAYPOINT-NAV · CHARGE-02",    pri: "P3", state: "QUEUED",   prog: 0,  assignee: "—",     eta: "12:58", wp: 6,  started: "—" },
    { id: "M-4415", name: "BIN-PICK · LINE-2 BATCH 16", pri: "P1", state: "DONE",     prog: 100,assignee: "H-003", eta: "—",     wp: 12, started: "05:42:12" },
    { id: "M-4414", name: "RECEIVING-DOCK-1 INTAKE",     pri: "P2", state: "FAILED",   prog: 41, assignee: "H-022", eta: "—",     wp: 9,  started: "05:36:30" },
    { id: "M-4413", name: "MANIP·PRECISION-A",           pri: "P2", state: "DONE",     prog: 100,assignee: "H-007", eta: "—",     wp: 6,  started: "05:11:08" },
  ];
  const stateColor = { RUNNING:"var(--ok)", QUEUED:"var(--info)", DONE:"var(--fg-mute)", FAILED:"var(--err)", PAUSED:"var(--warn)" };
  const priColor = { P0:"var(--err)", P1:"var(--warn)", P2:"var(--info)", P3:"var(--fg-mute)" };

  return (
    <div className="screen tasks">
      <div className="tasks-grid">
        <Panel title="MISSION QUEUE · 9 ACTIVE" right={
          <div style={{ display:"flex", gap: 6 }}>
            <button className="chip on">ALL</button>
            <button className="chip">RUNNING</button>
            <button className="chip">QUEUED</button>
            <button className="chip">FAILED</button>
            <button className="btn primary" style={{ marginLeft: 8 }}>+ NEW MISSION</button>
          </div>
        } pad={false} style={{ gridColumn: "1 / span 2" }}>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th style={{ width: 70 }}>ID</th>
                  <th style={{ width: 50 }}>PRI</th>
                  <th style={{ width: 90 }}>STATE</th>
                  <th>MISSION</th>
                  <th style={{ width: 90 }}>ASSIGNEE</th>
                  <th style={{ width: 60 }}>WP</th>
                  <th style={{ width: 200 }}>PROGRESS</th>
                  <th style={{ width: 70 }}>ETA</th>
                </tr>
              </thead>
              <tbody>
                {missions.map(m => (
                  <tr key={m.id}>
                    <td className="mono">{m.id}</td>
                    <td className="mono" style={{ color: priColor[m.pri] }}>{m.pri}</td>
                    <td className="mono" style={{ color: stateColor[m.state] }}>
                      <StatusDot status={m.state === "RUNNING" ? "ACTIVE" : m.state === "FAILED" ? "FAULT" : "IDLE"} size={6} />
                      <span style={{ marginLeft: 6 }}>{m.state}</span>
                    </td>
                    <td className="mono" style={{ color: "var(--fg)" }}>{m.name}</td>
                    <td className="mono"
                        style={{ cursor: m.assignee !== "—" ? "pointer" : "default", color: "var(--info)" }}
                        onClick={() => m.assignee !== "—" && onSelect(m.assignee)}>{m.assignee}</td>
                    <td className="mono dim">{m.wp}</td>
                    <td>
                      <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                        <Bar value={m.prog} color={stateColor[m.state]} />
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
            {missions.filter(m => m.state !== "QUEUED").map((m, i) => {
              const startH = m.started === "—" ? 6 : parseInt(m.started.slice(0,2)) + parseInt(m.started.slice(3,5))/60;
              const left = ((startH - 6) / 8) * 100;
              const width = Math.max(4, (m.prog/100 * 1.5)) * 4;
              return (
                <div key={m.id} className="gantt-row">
                  <div className="gantt-label mono">{m.assignee !== "—" ? m.assignee : m.id}</div>
                  <div className="gantt-track">
                    <div className="gantt-bar" style={{ left: `${left}%`, width: `${width}%`, background: stateColor[m.state] }}>
                      <span className="mono" style={{ fontSize: 9, padding: "0 4px" }}>{m.id}</span>
                    </div>
                  </div>
                </div>
              );
            })}
            {/* NOW line */}
            <div className="gantt-now" style={{ left: `${((6.5 - 6) / 8) * 100}%` }}>
              <span className="mono" style={{ fontSize: 9, color: "var(--err)" }}>NOW</span>
            </div>
          </div>
        </Panel>

        <Panel title="MISSION COMPOSER · NEW">
          <div className="form-row">
            <span className="tag dim">NAME</span>
            <input className="inp" defaultValue="PALLET-XFER · DOCK→KITTING" />
          </div>
          <div className="form-row">
            <span className="tag dim">PRIORITY</span>
            <div style={{ display:"flex", gap: 4 }}>
              {["P0","P1","P2","P3"].map((p, i) =>
                <button key={p} className={"chip" + (i===1?" on":"")} style={{ color: priColor[p] }}>{p}</button>
              )}
            </div>
          </div>
          <div className="form-row">
            <span className="tag dim">ASSIGNEE</span>
            <select className="inp">
              <option>AUTO · FIRST AVAILABLE</option>
              <option>H-003 · ORION</option>
              <option>H-008 · APOLLO</option>
              <option>H-011 · PERSEUS</option>
            </select>
          </div>
          <div className="form-row">
            <span className="tag dim">START</span>
            <input className="inp" defaultValue="ASAP" />
          </div>
          <div className="form-row">
            <span className="tag dim">CONSTRAINTS</span>
            <div style={{ display:"flex", gap: 4, flexWrap:"wrap" }}>
              <button className="chip on">SAFE-SPEED</button>
              <button className="chip on">HUMAN-AWARE</button>
              <button className="chip">SOLO</button>
              <button className="chip">PRECISION</button>
            </div>
          </div>
          <div className="form-row">
            <span className="tag dim">WAYPOINTS</span>
            <div className="mono dim" style={{ fontSize: 10 }}>W01 → W04 → W07 → W12</div>
          </div>
          <button className="btn primary" style={{ width: "100%", marginTop: 8 }}>QUEUE MISSION ›</button>
        </Panel>

        <Panel title="ROBOT AVAILABILITY">
          <div className="tag dim" style={{ marginBottom: 6 }}>READY · NOW</div>
          {fleet.filter(r => r.status === "IDLE").slice(0, 6).map(r => (
            <div key={r.id} className="avail-row" onClick={() => onSelect(r.id)}>
              <StatusDot status="IDLE" size={6} />
              <span className="mono" style={{ fontSize: 11 }}>{r.id}</span>
              <span style={{ fontSize: 10, color: "var(--fg-mute)" }}>{r.callsign}</span>
              <span className="mono dim" style={{ fontSize: 10, marginLeft: "auto" }}>BAT {r.battery}%</span>
            </div>
          ))}
          <hr className="hr" />
          <div className="tag dim" style={{ marginBottom: 6 }}>FREE AFTER · CURRENT</div>
          {fleet.filter(r => r.status === "ACTIVE").slice(0, 5).map(r => (
            <div key={r.id} className="avail-row" onClick={() => onSelect(r.id)}>
              <StatusDot status="ACTIVE" size={6} />
              <span className="mono" style={{ fontSize: 11 }}>{r.id}</span>
              <span style={{ fontSize: 10, color: "var(--fg-mute)" }}>{r.callsign}</span>
              <span className="mono dim" style={{ fontSize: 10, marginLeft: "auto" }}>~{Math.floor(8 + (parseInt(r.id.slice(2))%30))}m</span>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

// ── Analytics ──
function BigChart({ data, color, label, height = 100 }) {
  if (!data?.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * 800;
    const y = height - ((v - min) / range) * (height - 10) - 5;
    return [x, y];
  });
  const path = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const area = path + ` L800,${height} L0,${height} Z`;
  return (
    <svg viewBox={`0 0 800 ${height}`} preserveAspectRatio="none" style={{ width: "100%", height, display: "block" }}>
      <defs>
        <linearGradient id={"bc"+label} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map(p =>
        <line key={p} x1="0" y1={height*p} x2="800" y2={height*p} stroke="rgba(120,180,200,.08)" />
      )}
      <path d={area} fill={`url(#bc${label})`} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.4" />
    </svg>
  );
}

function AnalyticsScreen({ fleet }) {
  const s1 = useSeries(101, 120, 65, 18);
  const s2 = useSeries(102, 120, 30, 24);
  const s3 = useSeries(103, 120, 78, 8);
  const s4 = useSeries(104, 120, 42, 32);

  // status histogram
  const counts = { ACTIVE:0,IDLE:0,CHARGING:0,TELEOP:0,FAULT:0,OFFLINE:0 };
  fleet.forEach(r => counts[r.status]++);
  const total = fleet.length;

  return (
    <div className="screen analytics">
      <div className="kpi-row">
        <Panel><Stat label="THROUGHPUT · 24H" value="14,218" sub="+8.4% vs prev" color="var(--ok)" /></Panel>
        <Panel><Stat label="UPTIME · FLEET" value="94.2%" sub="SLA 95.0%" color="var(--warn)" /></Panel>
        <Panel><Stat label="MTBF" value="412h" sub="up from 384h" color="var(--ok)" /></Panel>
        <Panel><Stat label="ENERGY · 24H" value="218 kWh" sub="$26.40 grid" /></Panel>
        <Panel><Stat label="FAULTS · 24H" value="38" sub="−12 vs avg" color="var(--ok)" /></Panel>
        <Panel><Stat label="TELEOP · 24H" value="2.4 h" sub="3.1% of runtime" /></Panel>
      </div>

      <Panel title="THROUGHPUT · UNITS/HOUR · LAST 48H" right={<span className="tag dim">120 SAMPLES · BIN=24min</span>}>
        <BigChart data={s1} color="#4ade80" label="thrupt" height={160} />
      </Panel>

      <div className="analytics-grid">
        <Panel title="FAULT RATE · ‰" right={<span className="tag dim">7 DAYS</span>}>
          <BigChart data={s2} color="#fbbf24" label="fault" height={120} />
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 8, marginTop: 8 }}>
            <Stat label="LIDAR" value="0.42" sub="incl. dropout" />
            <Stat label="JOINT-STALL" value="0.18" sub="↓" color="var(--ok)" />
            <Stat label="GRIP-MISS" value="0.31" sub="↑" color="var(--warn)" />
            <Stat label="NETWORK" value="0.04" sub="stable" />
          </div>
        </Panel>

        <Panel title="ENERGY · kWh · per ROBOT">
          <div className="hbars">
            {fleet.slice(0, 12).map((r, i) => {
              const v = 4 + (i * 0.6) % 8;
              return (
                <div key={r.id} className="hbar-row">
                  <span className="mono" style={{ fontSize: 10, width: 56 }}>{r.id}</span>
                  <div style={{ flex: 1, height: 12, background: "var(--track)" }}>
                    <div style={{ height: "100%", width: `${(v/12)*100}%`, background: "var(--info)" }} />
                  </div>
                  <span className="mono dim" style={{ fontSize: 10, width: 36, textAlign: "right" }}>{v.toFixed(1)}</span>
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel title="STATUS DISTRIBUTION · NOW">
          {[
            ["ACTIVE",counts.ACTIVE,"var(--ok)"],
            ["IDLE",counts.IDLE,"var(--fg-mute)"],
            ["CHARGING",counts.CHARGING,"var(--info)"],
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

        <Panel title="NETWORK · LATENCY p50 / p95 · ms">
          <BigChart data={s4} color="#38bdf8" label="lat" height={120} />
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap: 8, marginTop: 8 }}>
            <Stat label="p50" value="12 ms" />
            <Stat label="p95" value="38 ms" />
            <Stat label="p99" value="84 ms" color="var(--warn)" />
            <Stat label="JITTER" value="1.2 ms" />
            <Stat label="LOSS" value="0.02%" color="var(--ok)" />
            <Stat label="OOO" value="0.00%" color="var(--ok)" />
          </div>
        </Panel>

        <Panel title="JOINT FAILURES · HEATMAP · 30 DAYS" style={{ gridColumn: "1 / span 2" }}>
          <div className="heatmap">
            {JOINTS.slice(0, 28).map(([name], i) => {
              const intensity = ((i * 17) % 100) / 100;
              return (
                <div key={name} className="heat-cell" title={name}
                  style={{ background: `rgba(239,68,68, ${intensity})` }}>
                  <span className="mono" style={{ fontSize: 9, color: intensity > 0.5 ? "#fff" : "var(--fg-mute)" }}>
                    {name.replace(/_/g, " ").slice(0, 8)}
                  </span>
                  <span className="mono" style={{ fontSize: 11, fontWeight: 600, color: intensity > 0.5 ? "#fff" : "var(--fg)" }}>
                    {Math.floor(intensity * 24)}
                  </span>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}

// ── Logs ──
function LogsScreen({ alerts }) {
  const fullLog = React.useMemo(() => {
    const out = [];
    const srcs = ["H-003","H-008","H-011","H-014","H-022","H-007","FLEET","OPS","NAV","PERCEPT","CTRL","SAFETY"];
    const tmpl = [
      "joint state published · 28 dof",
      "TF map→base_link · drift 0.02m",
      "Battery cell {n} voltage 3.{n}V",
      "Mission step {n} of 12 complete",
      "Force/Torque sensor calibrated · offset 0.1N",
      "Trajectory replanned · 14 wp · 8.4s",
      "Heartbeat ACK · seq 0x{n}{n}A4",
      "LIDAR scan {n}k points · 10Hz",
      "Object detected · BIN-BLUE · conf 0.98",
      "PID gains updated · joint SHOULDER_R",
      "Network: rtt {n}ms · loss 0%",
      "Self-test step {n} · PASS",
      "Camera HEAD-WIDE: exposure auto",
      "Path planner: alt route -2.1s",
    ];
    const sevs = ["DEBUG","DEBUG","DEBUG","INFO","INFO","INFO","INFO","OK","WARN","ERR"];
    let t = 6 * 3600 + 14 * 60 + 22;
    for (let i = 0; i < 80; i++) {
      const r = (i * 9301 + 49297) % 233280 / 233280;
      const n = Math.floor(r * 9);
      const msg = tmpl[Math.floor(r * tmpl.length)].replace(/\{n\}/g, () => Math.floor(r * 9));
      out.push({
        ts: `${String(Math.floor(t/3600)).padStart(2,"0")}:${String(Math.floor((t%3600)/60)).padStart(2,"0")}:${String(t%60).padStart(2,"0")}.${String(Math.floor(r*999)).padStart(3,"0")}`,
        sev: sevs[Math.floor(r * sevs.length)],
        src: srcs[Math.floor(r * srcs.length)],
        msg,
        topic: ["/joint_states","/tf","/scan","/cmd_vel","/diagnostics","/perception/dets"][Math.floor(r * 6)],
      });
      t -= Math.floor(r * 8) + 1;
    }
    return out;
  }, []);

  const [filter, setFilter] = React.useState("ALL");
  const filtered = filter === "ALL" ? fullLog : fullLog.filter(l => l.sev === filter);

  return (
    <div className="screen logs">
      <Panel title="EVENT STREAM · TAIL -F /var/log/helix.log" right={
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
              <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)", width: 70 }}>{l.src}</span>
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
          ["/joint_states", "200 Hz", "var(--ok)"],
          ["/tf",           "100 Hz", "var(--ok)"],
          ["/scan",         "10 Hz",  "var(--ok)"],
          ["/cmd_vel",      "50 Hz",  "var(--ok)"],
          ["/diagnostics",  "1 Hz",   "var(--ok)"],
          ["/camera/head/image_raw", "30 Hz", "var(--ok)"],
          ["/camera/r_wrist/depth",  "30 Hz", "var(--warn)"],
          ["/perception/dets",       "10 Hz", "var(--ok)"],
          ["/imu/data",     "200 Hz", "var(--ok)"],
        ].map(([t, hz, c]) => (
          <div key={t} className="topic-row">
            <span className="mono" style={{ fontSize: 10.5, color: "var(--info)" }}>{t}</span>
            <span className="mono" style={{ fontSize: 10, color: c }}>{hz}</span>
          </div>
        ))}
      </Panel>
      <Panel title="DIAGNOSTIC TREE">
        <div className="diag-tree">
          {[
            ["▼","FLEET","6 nodes","var(--ok)"],
            ["  ▼","H-003 · ORION","OK","var(--ok)"],
            ["    ▸","HARDWARE","OK","var(--ok)"],
            ["    ▸","PERCEPTION","OK","var(--ok)"],
            ["    ▼","CONTROL","WARN","var(--warn)"],
            ["      ◦","PID·SHOULDER_R","sat. 1.2s","var(--warn)"],
            ["    ▸","NAVIGATION","OK","var(--ok)"],
            ["  ▸","H-008 · APOLLO","OK","var(--ok)"],
            ["  ▼","H-022 · TARTARUS","ERR","var(--err)"],
            ["    ▼","HARDWARE","ERR","var(--err)"],
            ["      ◦","LIDAR-FRONT","loss 12%","var(--err)"],
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

// ── Settings ──
function SettingsScreen({ robot, onGoto }) {
  if (!robot) return (
    <div className="screen empty">
      <div style={{ textAlign:"center" }}>
        <div className="mono" style={{ fontSize: 18, color: "var(--dim)" }}>NO ROBOT SELECTED</div>
        <button className="btn primary" style={{ marginTop: 12 }} onClick={() => onGoto("fleet")}>OPEN FLEET MAP</button>
      </div>
    </div>
  );
  return (
    <div className="screen settings">
      <div className="settings-grid">
        <Panel title={`CONFIG · ${robot.id} · ${robot.callsign}`}>
          <div className="form-row"><span className="tag dim">CALLSIGN</span><input className="inp" defaultValue={robot.callsign} /></div>
          <div className="form-row"><span className="tag dim">HOSTNAME</span><input className="inp" defaultValue={`helix-${robot.id.toLowerCase()}.ops.lan`} /></div>
          <div className="form-row"><span className="tag dim">IP·v4</span><input className="inp" defaultValue={`10.42.0.${parseInt(robot.id.slice(2))}`} /></div>
          <div className="form-row"><span className="tag dim">FIRMWARE</span><input className="inp" defaultValue={robot.fw} /></div>
          <div className="form-row"><span className="tag dim">DOCK</span><select className="inp"><option>CHARGE-01</option><option>CHARGE-02</option></select></div>
          <div className="form-row">
            <span className="tag dim">MODE</span>
            <div style={{ display:"flex", gap: 4 }}>
              {["AUTONOMOUS","ASSIST","MANUAL","SHADOW"].map((m,i) => <button key={m} className={"chip" + (i===0?" on":"")}>{m}</button>)}
            </div>
          </div>
        </Panel>

        <Panel title="CONTROL · PID TUNING">
          {["BASE","TORSO","SHOULDER_L","SHOULDER_R","ELBOW_L","ELBOW_R","HIP_L","HIP_R","KNEE_L","KNEE_R"].map(j => (
            <div key={j} className="pid-row">
              <span className="mono dim" style={{ fontSize: 10, width: 90 }}>{j}</span>
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
            ["MAX VELOCITY", "1.40 m/s"],
            ["MAX ACCEL", "2.20 m/s²"],
            ["MAX TORQUE · ARM", "85 N·m"],
            ["MAX TORQUE · LEG", "180 N·m"],
            ["FORCE LIMIT · EE", "40 N"],
            ["HUMAN STOP-DISTANCE", "0.80 m"],
            ["WORKSPACE", "BAY-07 / EAST"],
            ["GEOFENCE", "x∈[-12,12] y∈[-8,8]"],
          ].map(([k, v]) => (
            <div key={k} className="form-row" style={{ alignItems:"center" }}>
              <span className="tag dim" style={{ flex: 1 }}>{k}</span>
              <input className="inp" defaultValue={v} style={{ width: 160 }} />
            </div>
          ))}
        </Panel>

        <Panel title="SENSORS · ENABLE">
          {[
            ["HEAD CAM · WIDE", true],
            ["HEAD CAM · TELE", true],
            ["WRIST CAM · L", true],
            ["WRIST CAM · R", true],
            ["LIDAR · FRONT", true],
            ["LIDAR · 360", true],
            ["IMU · TORSO", true],
            ["IMU · FOOT", true],
            ["F/T · L-WRIST", true],
            ["F/T · R-WRIST", true],
            ["MICROPHONE", false],
            ["RADAR · mmWAVE", false],
          ].map(([k, on], i) => (
            <div key={k} className="form-row" style={{ alignItems:"center", justifyContent:"space-between" }}>
              <span className="tag" style={{ color: on ? "var(--fg)" : "var(--dim)" }}>{k}</span>
              <div className={"switch" + (on ? " on" : "")}>
                <div className="switch-thumb" />
              </div>
            </div>
          ))}
        </Panel>

        <Panel title="OTA · DEPLOYMENT">
          <div className="form-row"><span className="tag dim">CHANNEL</span>
            <div style={{ display:"flex", gap: 4 }}>
              {["STABLE","BETA","NIGHTLY"].map((m,i) => <button key={m} className={"chip" + (i===0?" on":"")}>{m}</button>)}
            </div>
          </div>
          <div className="form-row"><span className="tag dim">CURRENT</span>
            <div className="mono" style={{ fontSize: 11 }}>{robot.fw} · STABLE</div>
          </div>
          <div className="form-row"><span className="tag dim">AVAILABLE</span>
            <div className="mono" style={{ fontSize: 11, color: "var(--info)" }}>2.7.122 · 18 commits ahead</div>
          </div>
          <Bar value={0} color="var(--info)" height={4} />
          <div style={{ display:"flex", gap: 6, marginTop: 10 }}>
            <button className="btn primary">STAGE</button>
            <button className="btn">ROLL BACK</button>
            <button className="btn">FORCE REBOOT</button>
          </div>
        </Panel>

        <Panel title="ACCESS · AUDIT">
          {[
            ["06:14:18", "OP·KOSTA", "TELEOP ACQUIRED", "var(--magenta)"],
            ["06:11:02", "OP·LIN",   "MISSION QUEUED ×3", "var(--info)"],
            ["06:08:42", "SYS",      "OTA STAGED 2.7.121", "var(--ok)"],
            ["05:48:14", "OP·KOSTA", "PID UPDATED SHOULDER_R", "var(--warn)"],
            ["05:32:08", "OP·DAR",   "E-STOP TEST PASS", "var(--ok)"],
            ["04:11:50", "SYS",      "REBOOT SCHEDULED", "var(--info)"],
          ].map((row, i) => (
            <div key={i} className="audit-row">
              <span className="mono dim" style={{ fontSize: 10 }}>{row[0]}</span>
              <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)" }}>{row[1]}</span>
              <span className="mono" style={{ fontSize: 10, color: row[3] }}>{row[2]}</span>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

Object.assign(window, { TasksScreen, AnalyticsScreen, LogsScreen, SettingsScreen, BigChart });
