// screen-teleop.jsx — direct control + scene 3D viewer

function Joystick({ label, x, y, color = "var(--magenta)" }) {
  return (
    <div className="joystick">
      <div className="tag dim">{label}</div>
      <svg width="160" height="160" viewBox="-1 -1 2 2">
        <defs>
          <radialGradient id={"jg"+label} cx="0" cy="0" r="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle r="1" fill={`url(#jg${label})`} stroke={color} strokeOpacity="0.5" strokeWidth="0.01" />
        <circle r="0.66" fill="none" stroke={color} strokeOpacity="0.25" strokeWidth="0.008" strokeDasharray="0.04 0.03" />
        <circle r="0.33" fill="none" stroke={color} strokeOpacity="0.25" strokeWidth="0.008" strokeDasharray="0.04 0.03" />
        <line x1="-1" y1="0" x2="1" y2="0" stroke={color} strokeOpacity="0.2" strokeWidth="0.006" />
        <line x1="0" y1="-1" x2="0" y2="1" stroke={color} strokeOpacity="0.2" strokeWidth="0.006" />
        <line x1="0" y1="0" x2={x} y2={y} stroke={color} strokeWidth="0.02" />
        <circle cx={x} cy={y} r="0.08" fill={color} stroke="#06090d" strokeWidth="0.02" />
        <circle cx={x} cy={y} r="0.14" fill="none" stroke={color} strokeOpacity="0.5" strokeWidth="0.01" />
      </svg>
      <div className="mono" style={{ fontSize: 10, color: "var(--fg-mute)", textAlign:"center" }}>
        X{x.toFixed(2)} Y{y.toFixed(2)}
      </div>
    </div>
  );
}

function TeleopScreen({ robot, onGoto }) {
  const [vx, setVx] = React.useState(0.42);
  const [vy, setVy] = React.useState(-0.18);
  const [wz, setWz] = React.useState(0.1);
  const [gripL, setGripL] = React.useState(34);
  const [gripR, setGripR] = React.useState(82);
  const [keys, setKeys] = React.useState(new Set());

  React.useEffect(() => {
    const dn = e => {
      if (["w","a","s","d","q","e"].includes(e.key)) {
        setKeys(s => new Set(s).add(e.key));
      }
    };
    const up = e => setKeys(s => { const n = new Set(s); n.delete(e.key); return n; });
    window.addEventListener("keydown", dn); window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", dn); window.removeEventListener("keyup", up); };
  }, []);

  if (!robot) return (
    <div className="screen empty">
      <div style={{ textAlign:"center" }}>
        <div className="mono" style={{ fontSize: 18, color: "var(--dim)" }}>SELECT A ROBOT TO TELEOP</div>
        <button className="btn primary" style={{ marginTop: 12 }} onClick={() => onGoto("fleet")}>OPEN FLEET MAP</button>
      </div>
    </div>
  );

  const breath = useBreath(99, 600, 1);

  return (
    <div className="screen teleop">
      <Panel title={`◉ TELEOP · ${robot.id} · ${robot.callsign}`} right={
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <div className="mono" style={{ fontSize: 11, color: "var(--magenta)" }}>● LINK · CTRL TAKEN BY OP·KOSTA</div>
          <div className="mono dim" style={{ fontSize: 10 }}>RTT {robot.latencyMs}ms · JITTER 1.2ms</div>
        </div>
      } pad={false} style={{ gridColumn: "1 / -1" }}>
        <CameraFeed label="HEAD-WIDE · TELEOP" sub={`${robot.id} · LIVE · ${Math.floor(60 + breath)} fps`} color="var(--magenta)" big />
      </Panel>

      <div className="teleop-grid">
        <Panel title="DRIVE · BASE">
          <div style={{ display: "flex", justifyContent: "space-around", marginBottom: 8 }}>
            <Joystick label="LEFT · TRANSLATE" x={vx} y={vy} />
            <Joystick label="RIGHT · ROTATE" x={wz} y={0} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns:"1fr 1fr 1fr", gap: 6, marginTop: 6 }}>
            <Stat label="V·X" value={`${vx.toFixed(2)} m/s`} mono />
            <Stat label="V·Y" value={`${vy.toFixed(2)} m/s`} mono />
            <Stat label="ω·Z" value={`${wz.toFixed(2)} rad/s`} mono />
          </div>
          <div style={{ marginTop: 10 }}>
            <div className="tag dim">KEYBOARD · LIVE</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, marginTop: 4 }}>
              {[["","W",""],["A","S","D"],["Q","","E"]].flat().map((k, i) => (
                <div key={i} className={"key" + (keys.has(k.toLowerCase()) ? " on" : "") + (!k ? " ghost" : "")}>{k}</div>
              ))}
            </div>
            <div className="mono dim" style={{ fontSize: 10, marginTop: 6 }}>WASD · TRANS · Q/E · YAW · SPACE · STOP</div>
          </div>
        </Panel>

        <Panel title="MANIPULATION · END·EFFECTORS">
          <div className="tag dim">LEFT HAND · GRIP</div>
          <Bar value={gripL} color="var(--info)" height={8} showVal />
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 6, marginTop: 6 }}>
            <Stat label="FORCE" value="12.4 N" mono />
            <Stat label="OBJECT" value="CONTACT" color="var(--ok)" />
          </div>
          <hr className="hr" />
          <div className="tag dim">RIGHT HAND · GRIP</div>
          <Bar value={gripR} color="var(--info)" height={8} showVal />
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 6, marginTop: 6 }}>
            <Stat label="FORCE" value="38.1 N" color="var(--warn)" mono />
            <Stat label="OBJECT" value="GRASP-LOCK" color="var(--magenta)" />
          </div>
          <hr className="hr" />
          <div style={{ display:"flex", gap: 4, flexWrap:"wrap" }}>
            {["OPEN-L","CLOSE-L","OPEN-R","CLOSE-R","TWIST-CW","TWIST-CCW"].map(k =>
              <button key={k} className="chip">{k}</button>
            )}
          </div>
        </Panel>

        <Panel title="JOINT TRIM · LIVE">
          {JOINTS.slice(0, 8).map(([name, lo, hi], i) => (
            <div key={name} style={{ marginBottom: 6 }}>
              <div style={{ display:"flex", justifyContent:"space-between", fontSize: 10 }}>
                <span className="mono dim">{name}</span>
                <span className="mono" style={{ color: "var(--fg)" }}>{(lo + (i*7)%(hi-lo)).toFixed(1)}°</span>
              </div>
              <div style={{ position:"relative", height: 4, background:"var(--track)" }}>
                <div style={{ position:"absolute", left: `${((i*13)%100)}%`, top:-2, width: 2, height: 8, background:"var(--magenta)" }} />
                <div style={{ position:"absolute", left: `${((i*13)%100 + 10) % 100}%`, top:-2, width: 2, height: 8, background:"var(--info)", opacity: 0.6 }} />
              </div>
            </div>
          ))}
          <button className="btn" style={{ width:"100%", marginTop: 6 }}>OPEN FULL JOINT EDITOR ›</button>
        </Panel>

        <Panel title="SAFETY · INTERLOCKS" right={<span className="mono" style={{ fontSize: 10, color: "var(--warn)" }}>ARMED</span>}>
          {[
            ["WORKSPACE BOUNDS",    "OK", "var(--ok)"],
            ["FORCE LIMIT",         "OK", "var(--ok)"],
            ["SELF-COLLISION",      "OK", "var(--ok)"],
            ["HUMAN-PROXIMITY",     "1.2m · OK", "var(--ok)"],
            ["DEADMAN-SWITCH",      "HELD", "var(--ok)"],
            ["EE-FORCE/TORQUE",     "38.1 N · WARN", "var(--warn)"],
            ["JOINT-LIMITS",        "OK", "var(--ok)"],
            ["NETWORK-LINK",        "STABLE", "var(--ok)"],
          ].map(([k, v, c]) => (
            <div key={k} style={{ display:"flex", justifyContent:"space-between", padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
              <span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span>
              <span className="mono" style={{ fontSize: 11, color: c }}>{v}</span>
            </div>
          ))}
          <button className="btn danger" style={{ width:"100%", marginTop: 10, fontSize: 14, padding: "10px" }}>⏻ EMERGENCY STOP</button>
        </Panel>
      </div>
    </div>
  );
}

// ── 3D scene viewer ──
function SceneScreen({ robot }) {
  const breath = useBreath(33, 800, 1);
  return (
    <div className="screen scene">
      <Panel title="SCENE · OCCUPANCY + LIDAR · LIVE" right={
        <div style={{ display: "flex", gap: 6 }}>
          {["POINTS","MESH","VOXEL","SURFEL"].map((m,i) =>
            <button key={m} className={"chip" + (i===0?" on":"")}>{m}</button>
          )}
        </div>
      } pad={false} style={{ gridColumn: "1 / span 3" }}>
        <div className="scene-canvas">
          <svg viewBox="0 0 1000 600" preserveAspectRatio="none" style={{ position:"absolute", inset:0, width:"100%", height:"100%" }}>
            <defs>
              <radialGradient id="scenegrad" cx="50%" cy="50%" r="70%">
                <stop offset="0%" stopColor="rgba(56,189,248,.08)" />
                <stop offset="100%" stopColor="rgba(56,189,248,0)" />
              </radialGradient>
            </defs>
            <rect width="1000" height="600" fill="url(#scenegrad)" />
            {/* iso grid */}
            {Array.from({length: 16}).map((_, i) => (
              <line key={"h"+i} x1={0} y1={i*40} x2={1000} y2={i*40 - 200} stroke="rgba(56,189,248,.12)" strokeWidth="0.6" />
            ))}
            {Array.from({length: 22}).map((_, i) => (
              <line key={"v"+i} x1={i*50} y1={0} x2={i*50 + 200} y2={600} stroke="rgba(56,189,248,.12)" strokeWidth="0.6" />
            ))}
            {/* point cloud */}
            {Array.from({length: 800}).map((_, i) => {
              const r = (i * 9301 + 49297) % 233280 / 233280;
              const r2 = (i * 7919) % 1000;
              const x = (r * 900 + 50);
              const y = 100 + r * r2 * 0.5;
              const sz = 0.6 + r * 1.5;
              const col = r > 0.7 ? "#4ade80" : r > 0.4 ? "#38bdf8" : "#9ca3af";
              return <circle key={i} cx={x} cy={y % 540 + 30} r={sz} fill={col} opacity={0.4 + r * 0.5} />;
            })}
            {/* robot in scene */}
            <g transform="translate(480 360)">
              <line x1="-40" y1="0" x2="40" y2="-30" stroke="var(--ok)" strokeWidth="1.5" strokeOpacity="0.7" />
              <line x1="-40" y1="0" x2="-30" y2="100" stroke="var(--ok)" strokeWidth="1.5" strokeOpacity="0.7" />
              <line x1="40" y1="-30" x2="60" y2="80" stroke="var(--ok)" strokeWidth="1.5" strokeOpacity="0.7" />
              {/* humanoid silhouette */}
              <g transform="translate(0 -80) scale(0.6)">
                <circle r="20" cy="0" fill="none" stroke="var(--ok)" strokeWidth="2" />
                <line x1="0" y1="20" x2="0" y2="120" stroke="var(--ok)" strokeWidth="3" />
                <line x1="0" y1="40" x2="-40" y2="90" stroke="var(--ok)" strokeWidth="3" />
                <line x1="0" y1="40" x2="40" y2="90" stroke="var(--ok)" strokeWidth="3" />
                <line x1="0" y1="120" x2="-25" y2="190" stroke="var(--ok)" strokeWidth="3" />
                <line x1="0" y1="120" x2="25" y2="190" stroke="var(--ok)" strokeWidth="3" />
              </g>
              <circle r="50" fill="none" stroke="var(--ok)" strokeOpacity="0.4" strokeDasharray="3 4">
                <animate attributeName="r" from="40" to="80" dur="3s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.5" to="0" dur="3s" repeatCount="indefinite" />
              </circle>
              <text x="80" y="-20" fill="var(--ok)" fontSize="11" fontFamily="JetBrains Mono">{robot ? robot.id : "BASE_LINK"}</text>
            </g>
            {/* axis triad */}
            <g transform="translate(80 540)">
              <line x1="0" y1="0" x2="40" y2="0" stroke="#ef4444" strokeWidth="2" />
              <line x1="0" y1="0" x2="0" y2="-40" stroke="#4ade80" strokeWidth="2" />
              <line x1="0" y1="0" x2="-22" y2="22" stroke="#38bdf8" strokeWidth="2" />
              <text x="44" y="4" fill="#ef4444" fontSize="11" fontFamily="JetBrains Mono">X</text>
              <text x="-3" y="-44" fill="#4ade80" fontSize="11" fontFamily="JetBrains Mono">Y</text>
              <text x="-32" y="32" fill="#38bdf8" fontSize="11" fontFamily="JetBrains Mono">Z</text>
            </g>
          </svg>

          {/* HUD */}
          <div className="floor-hud tl">
            <div>
              <div className="tag dim">FRAME</div>
              <div className="mono" style={{ fontSize: 12 }}>map → base_link</div>
              <div className="tag dim" style={{ marginTop: 2 }}>{robot ? robot.id : "—"} · {Math.floor(40 + breath*4)} pts/ms</div>
            </div>
          </div>
          <div className="floor-hud tr">
            <div className="mono" style={{ fontSize: 10 }}>CAM</div>
            <div className="mono dim" style={{ fontSize: 10 }}>az 42°  el 28°  zoom 1.4×</div>
          </div>
          <div className="floor-hud br">
            <div className="mono dim" style={{ fontSize: 10 }}>OCC GRID  0.05m</div>
            <div className="mono dim" style={{ fontSize: 10 }}>SLAM·VIO  KF·412</div>
          </div>
        </div>
      </Panel>

      <Panel title="LAYERS">
        {["POINT CLOUD · L1","POINT CLOUD · L2","SLAM MESH","OCTOMAP","SEMANTIC SEG","COSTMAP","TRAJECTORY","WAYPOINTS","TF FRAMES","BOUNDING BOXES","HUMAN POSES"].map((l, i) => (
          <label key={l} className="row">
            <input type="checkbox" defaultChecked={i < 6} />
            <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)" }}>{l}</span>
          </label>
        ))}
      </Panel>
      <Panel title="DETECTIONS · LIVE">
        {[
          ["PERSON","99.4%","x +1.20 y −0.30","var(--info)"],
          ["BIN-RED","97.1%","x +2.10 y +0.40","var(--err)"],
          ["BIN-BLUE","96.4%","x +1.80 y −0.80","var(--info)"],
          ["PALLET","92.8%","x +3.40 y +0.10","var(--warn)"],
          ["FORKLIFT","88.2%","x +6.20 y −1.10","var(--magenta)"],
          ["GROUND","99.9%","plane z=0.00","var(--ok)"],
        ].map((d, i) => (
          <div key={i} className="det">
            <span className="dot" style={{ background: d[3] }} />
            <span className="mono" style={{ fontSize: 11 }}>{d[0]}</span>
            <span className="mono dim" style={{ fontSize: 10 }}>{d[1]}</span>
            <span className="mono dim" style={{ fontSize: 10 }}>{d[2]}</span>
          </div>
        ))}
      </Panel>
      <Panel title="LIDAR · METRICS">
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 8 }}>
          <Stat label="POINTS" value="124,418" sub="per frame" />
          <Stat label="RATE" value="10 Hz" sub="LIVOX·MID-360" />
          <Stat label="RANGE" value="40 m" sub="@ 80% refl" />
          <Stat label="FoV" value="360°" sub="× 59° v" />
          <Stat label="SLAM·DRIFT" value="0.04 m" sub="loop closed" color="var(--ok)" />
          <Stat label="CPU·NDC" value="22%" sub="GPU 41%" />
        </div>
      </Panel>
    </div>
  );
}

Object.assign(window, { TeleopScreen, SceneScreen, Joystick });
