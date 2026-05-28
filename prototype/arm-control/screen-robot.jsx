// screen-robot.jsx — robot detail + teleop

// Stylized humanoid skeleton viz with joint highlights
function HumanoidSkeleton({ width = 320, height = 420, joints, faultJoints = [] }) {
  // points (front-facing humanoid)
  const cx = width / 2;
  const P = {
    head: [cx, 50], neck: [cx, 90],
    shoulderL: [cx - 60, 100], shoulderR: [cx + 60, 100],
    elbowL: [cx - 86, 168], elbowR: [cx + 86, 168],
    wristL: [cx - 96, 240], wristR: [cx + 96, 240],
    chest: [cx, 130], hip: [cx, 220],
    hipL: [cx - 32, 230], hipR: [cx + 32, 230],
    kneeL: [cx - 36, 318], kneeR: [cx + 36, 318],
    ankleL: [cx - 40, 392], ankleR: [cx + 40, 392],
  };
  const seg = (a, b, key, lbl) => {
    const fault = faultJoints.includes(key);
    return <line key={lbl} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]}
      stroke={fault ? "var(--err)" : "var(--ok)"} strokeOpacity={fault ? 0.9 : 0.55}
      strokeWidth="2" />;
  };
  const dot = (p, k, big = false) => {
    const fault = faultJoints.includes(k);
    const c = fault ? "var(--err)" : "var(--ok)";
    return (
      <g key={k}>
        <circle cx={p[0]} cy={p[1]} r={big ? 6 : 4} fill={c} stroke="#06090d" strokeWidth="1.5" />
        {fault && (
          <circle cx={p[0]} cy={p[1]} r="9" fill="none" stroke={c}>
            <animate attributeName="r" from="5" to="14" dur="1.4s" repeatCount="indefinite" />
            <animate attributeName="opacity" from="0.7" to="0" dur="1.4s" repeatCount="indefinite" />
          </circle>
        )}
      </g>
    );
  };

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      {/* grid backdrop */}
      <defs>
        <pattern id="hgrid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(120,180,200,.06)" strokeWidth="1"/>
        </pattern>
        <radialGradient id="hglow" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stopColor="rgba(74,222,128,.08)" />
          <stop offset="100%" stopColor="rgba(74,222,128,0)" />
        </radialGradient>
      </defs>
      <rect width={width} height={height} fill="url(#hgrid)" />
      <rect width={width} height={height} fill="url(#hglow)" />

      {/* axes */}
      <line x1="0" y1={height/2} x2={width} y2={height/2} stroke="rgba(120,180,200,.1)" strokeDasharray="2 4" />
      <line x1={cx} y1="0" x2={cx} y2={height} stroke="rgba(120,180,200,.1)" strokeDasharray="2 4" />

      {/* head */}
      <circle cx={P.head[0]} cy={P.head[1]} r="22" fill="none" stroke="var(--ok)" strokeOpacity="0.55" strokeWidth="2" />
      <circle cx={P.head[0]-8} cy={P.head[1]-4} r="2" fill="var(--ok)" />
      <circle cx={P.head[0]+8} cy={P.head[1]-4} r="2" fill="var(--ok)" />
      <line x1={P.head[0]-6} y1={P.head[1]+8} x2={P.head[0]+6} y2={P.head[1]+8} stroke="var(--ok)" strokeOpacity="0.55" strokeWidth="1.5" />

      {/* skeleton */}
      {seg(P.head, P.neck, null, "head-neck")}
      {seg(P.neck, P.chest, null, "neck-chest")}
      {seg(P.chest, P.shoulderL, null, "c-sl")}
      {seg(P.chest, P.shoulderR, null, "c-sr")}
      {seg(P.shoulderL, P.elbowL, "SHOULDER_L_PITCH", "sl-el")}
      {seg(P.shoulderR, P.elbowR, "SHOULDER_R_PITCH", "sr-er")}
      {seg(P.elbowL, P.wristL, "ELBOW_L", "el-wl")}
      {seg(P.elbowR, P.wristR, "ELBOW_R", "er-wr")}
      {seg(P.chest, P.hip, null, "ch-hp")}
      {seg(P.hip, P.hipL, null, "h-hl")}
      {seg(P.hip, P.hipR, null, "h-hr")}
      {seg(P.hipL, P.kneeL, "KNEE_L", "hl-kl")}
      {seg(P.hipR, P.kneeR, "KNEE_R", "hr-kr")}
      {seg(P.kneeL, P.ankleL, "ANKLE_L_PITCH", "kl-al")}
      {seg(P.kneeR, P.ankleR, "ANKLE_R_PITCH", "kr-ar")}

      {/* dots */}
      {Object.entries(P).map(([k, p]) => dot(p, k.toUpperCase(), k === "head"))}

      {/* COG marker */}
      <g transform={`translate(${P.hip[0]} ${P.hip[1]+6})`}>
        <circle r="10" fill="none" stroke="var(--info)" strokeDasharray="2 3" />
        <text x="14" y="3" fill="var(--info)" fontSize="9" fontFamily="JetBrains Mono">COG</text>
      </g>

      {/* labels */}
      <text x="6" y="14" fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">VIEW · FRONT · BASE_LINK</text>
      <text x={width - 6} y="14" textAnchor="end" fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">28 DoF · URDF v2.3</text>
      <text x="6" y={height - 6} fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">SCALE 1:8</text>
      <text x={width - 6} y={height - 6} textAnchor="end" fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">F=120Hz</text>
    </svg>
  );
}

function CameraFeed({ label, sub, color = "var(--ok)", noise = true, big = false, scene = "warehouse" }) {
  const t = useBreath(label.length, 800, 1);
  const lines = useSeries(label.charCodeAt(0), 60, 50, 30);
  return (
    <div className="camera" style={{ aspectRatio: big ? "16/9" : "4/3" }}>
      {/* synthetic scene */}
      <svg viewBox="0 0 400 300" preserveAspectRatio="none" style={{ position:"absolute", inset:0, width:"100%", height:"100%" }}>
        <defs>
          <linearGradient id={"cg"+label} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#0a1410" />
            <stop offset="100%" stopColor="#020404" />
          </linearGradient>
        </defs>
        <rect width="400" height="300" fill={`url(#cg${label})`} />
        {/* perspective floor */}
        {scene === "warehouse" && <>
          {[160,180,200,220,240,260,280].map((y, i) => (
            <line key={y} x1={50 - i*10} y1={y} x2={350 + i*10} y2={y} stroke="rgba(74,222,128,.22)" strokeWidth="0.7" />
          ))}
          {[-2,-1,0,1,2].map(k => (
            <line key={k} x1={200 + k*60} y1={150} x2={200 + k*200} y2={290} stroke="rgba(74,222,128,.18)" strokeWidth="0.7" />
          ))}
          <rect x="120" y="120" width="40" height="60" fill="rgba(120,180,200,.18)" stroke="rgba(120,180,200,.35)" />
          <rect x="240" y="100" width="56" height="80" fill="rgba(120,180,200,.18)" stroke="rgba(120,180,200,.35)" />
          <rect x="180" y="140" width="32" height="38" fill="rgba(232,121,249,.18)" stroke="rgba(232,121,249,.5)" />
        </>}
        {scene === "grip" && <>
          <rect x="80" y="80" width="240" height="160" fill="rgba(56,189,248,.05)" stroke="rgba(56,189,248,.35)" />
          <circle cx="200" cy="160" r="48" fill="rgba(232,121,249,.15)" stroke="rgba(232,121,249,.6)" strokeWidth="1.5" />
          <line x1="200" y1="100" x2="200" y2="80" stroke="var(--magenta)" strokeWidth="2" />
          <line x1="155" y1="120" x2="245" y2="120" stroke="rgba(232,121,249,.4)" strokeDasharray="3 3" />
        </>}
        {/* HUD reticle */}
        <line x1="195" y1="150" x2="205" y2="150" stroke="var(--ok)" strokeWidth="1.5" />
        <line x1="200" y1="145" x2="200" y2="155" stroke="var(--ok)" strokeWidth="1.5" />
        <circle cx="200" cy="150" r="14" fill="none" stroke="var(--ok)" strokeOpacity="0.6" />
        <circle cx="200" cy="150" r="30" fill="none" stroke="var(--ok)" strokeOpacity="0.3" strokeDasharray="2 4" />

        {/* corner brackets */}
        {[[10,10,1,1],[390,10,-1,1],[10,290,1,-1],[390,290,-1,-1]].map(([x,y,dx,dy], i) => (
          <g key={i} stroke={color} strokeWidth="1.5" fill="none">
            <line x1={x} y1={y} x2={x + dx*14} y2={y} />
            <line x1={x} y1={y} x2={x} y2={y + dy*14} />
          </g>
        ))}

        {/* scanline */}
        <line x1="0" x2="400" y1={150 + t * 80} y2={150 + t * 80} stroke={color} strokeOpacity="0.18" strokeWidth="1" />

        {/* noise */}
        {noise && Array.from({length: 14}).map((_, i) => (
          <rect key={i} x={(i*37)%400} y={(i*97)%300} width="1" height="1" fill="rgba(180,200,210,.3)" />
        ))}
      </svg>

      {/* HUD text */}
      <div className="cam-hud-tl">
        <span className="mono" style={{ color }}>● REC</span>
        <span className="mono dim" style={{ marginLeft: 8 }}>{label}</span>
      </div>
      <div className="cam-hud-tr mono dim">{sub}</div>
      <div className="cam-hud-bl mono dim">f/2.4 · 1/240s · ISO 800</div>
      <div className="cam-hud-br mono" style={{ color }}>{Math.floor(60 + t*3)}fps</div>
    </div>
  );
}

function RobotDetailScreen({ robot, onGoto }) {
  if (!robot) return (
    <div className="screen empty">
      <div style={{ textAlign:"center" }}>
        <div className="mono" style={{ fontSize: 18, color: "var(--dim)" }}>NO ROBOT SELECTED</div>
        <button className="btn primary" style={{ marginTop: 12 }} onClick={() => onGoto("fleet")}>OPEN FLEET MAP</button>
      </div>
    </div>
  );

  const jstate = React.useMemo(() => jointStateFor(parseInt(robot.id.slice(2)) + 1), [robot.id]);
  const faulty = jstate.filter(j => j.err).map(j => j.name);

  const seriesCpu = useSeries(parseInt(robot.id.slice(2)) + 1, 80, robot.cpu, 16);
  const seriesNet = useSeries(parseInt(robot.id.slice(2)) + 2, 80, 45, 30);
  const seriesTemp = useSeries(parseInt(robot.id.slice(2)) + 3, 80, robot.temp, 4);
  const seriesBat = useSeries(parseInt(robot.id.slice(2)) + 4, 80, robot.battery, 2);

  return (
    <div className="screen robot">
      <div className="robot-grid">
        {/* hero panel: skeleton + key stats */}
        <Panel title={`◉ ${robot.id} · ${robot.callsign} · BODY STATE`} right={
          <div style={{ display:"flex", gap: 6 }}>
            <button className="chip on">FRONT</button><button className="chip">SIDE</button><button className="chip">TOP</button>
          </div>
        } style={{ gridColumn: "1 / span 2", gridRow: "1 / span 2" }}>
          <div style={{ display:"flex", gap: 14 }}>
            <HumanoidSkeleton joints={jstate} faultJoints={faulty} />
            <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignContent: "start" }}>
              <Stat label="STATUS" value={robot.status} color="var(--ok)" />
              <Stat label="MODE" value="AUTONOMOUS" />
              <Stat label="BATTERY" value={`${robot.battery}%`} sub={`${(robot.battery*0.95).toFixed(1)} kWh · ${(robot.battery/4).toFixed(0)}min`} />
              <Stat label="HEADING" value={`${robot.heading}°`} sub="bay-relative" />
              <Stat label="GAIT" value="BIPED·WALK" sub="0.84 m/s" />
              <Stat label="PAYLOAD" value={`${robot.payload} kg`} sub="L+R hands" />
              <Stat label="CORE T°" value={`${robot.temp}°C`} color={robot.temp > 55 ? "var(--warn)" : undefined} />
              <Stat label="UPTIME" value={`${robot.uptime}h`} />
              <Stat label="CPU" value={`${robot.cpu}%`} sub="8 cores · ARM" />
              <Stat label="RAM" value={`${robot.ram}%`} sub="32GB DDR5" />
              <div style={{ gridColumn: "1 / -1", display: "flex", gap: 6, marginTop: 4 }}>
                <button className="btn primary" onClick={() => onGoto("teleop")}>TELEOP ›</button>
                <button className="btn">PAUSE</button>
                <button className="btn">REBOOT</button>
                <button className="btn danger">E·STOP</button>
              </div>
            </div>
          </div>
        </Panel>

        {/* camera feeds */}
        <Panel title="CAM·HEAD-WIDE" right={<span className="tag dim">1920×1080 · H.265</span>} pad={false}>
          <CameraFeed label="HEAD-WIDE" sub="EXP 1/240 · GAIN 16" big />
        </Panel>
        <Panel title="CAM·R-WRIST" right={<span className="tag dim">D435i</span>} pad={false}>
          <CameraFeed label="R-WRIST" sub="DEPTH" color="var(--magenta)" scene="grip" big />
        </Panel>

        {/* joint table */}
        <Panel title="JOINT STATE · 28 DoF" right={
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span className="tag dim">UPDATING @ 200Hz</span>
            <button className="chip on">ALL</button><button className="chip">FAULTS</button><button className="chip">UPPER</button><button className="chip">LOWER</button>
          </div>
        } style={{ gridColumn: "1 / span 2" }} pad={false}>
          <div className="table-wrap small">
            <table className="dtable">
              <thead>
                <tr><th>JOINT</th><th>POS°</th><th>TGT°</th><th>VEL°/s</th><th>TQ N·m</th><th>T°</th><th>RANGE</th><th>ERR</th></tr>
              </thead>
              <tbody>
                {jstate.map(j => {
                  const pct = (j.pos - j.lo) / (j.hi - j.lo);
                  return (
                    <tr key={j.name} className={j.err ? "row-err" : ""}>
                      <td className="mono">{j.name}</td>
                      <td className="mono">{j.pos.toFixed(2)}</td>
                      <td className="mono dim">{j.tgt.toFixed(2)}</td>
                      <td className="mono dim">{j.vel.toFixed(2)}</td>
                      <td className="mono dim">{j.torque.toFixed(2)}</td>
                      <td className="mono" style={{ color: j.temp > 60 ? "var(--warn)" : "var(--fg-mute)" }}>{j.temp}</td>
                      <td style={{ width: 110 }}>
                        <div style={{ position:"relative", height: 6, background: "var(--track)" }}>
                          <div style={{ position:"absolute", left: `${pct*100}%`, top: -2, width: 2, height: 10, background: j.err ? "var(--err)" : "var(--ok)" }} />
                          <div style={{ position:"absolute", left: `${((j.tgt - j.lo)/(j.hi - j.lo))*100}%`, top: -2, width: 2, height: 10, background: "var(--info)", opacity: 0.7 }} />
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

        {/* telemetry stack */}
        <Panel title="TELEMETRY · LIVE">
          {[
            ["CPU·LOAD", seriesCpu, "var(--ok)", `${robot.cpu}%`],
            ["NET·THROUGHPUT", seriesNet, "var(--info)", `${Math.floor(seriesNet[seriesNet.length-1])} Mb/s`],
            ["CORE·TEMP", seriesTemp, robot.temp > 55 ? "var(--warn)" : "var(--ok)", `${robot.temp}°C`],
            ["BATTERY", seriesBat, "var(--info)", `${robot.battery}%`],
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

        {/* IMU + battery cells */}
        <Panel title="IMU · ORIENTATION" right={<span className="tag dim">200Hz · FUSED</span>}>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap: 8 }}>
            <Stat label="ROLL" value="+02.18°" sub="±0.04" />
            <Stat label="PITCH" value="−00.41°" sub="±0.04" />
            <Stat label="YAW" value="+126.83°" sub="MAG-N" />
            <Stat label="ACC·X" value="+0.08 g" />
            <Stat label="ACC·Y" value="+0.02 g" />
            <Stat label="ACC·Z" value="−0.99 g" />
            <Stat label="GYRO·X" value="0.012" sub="rad/s" />
            <Stat label="GYRO·Y" value="0.008" sub="rad/s" />
            <Stat label="GYRO·Z" value="0.144" sub="rad/s" />
          </div>
          <hr className="hr" />
          <div className="tag dim" style={{ marginBottom: 4 }}>BATTERY · 12-CELL PACK</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 4 }}>
            {Array.from({ length: 12 }).map((_, i) => {
              const v = 3.92 + (Math.sin(i * 1.7 + parseInt(robot.id.slice(2))) * 0.04);
              const ok = i !== 3;
              return (
                <div key={i} style={{
                  border: `1px solid ${ok ? "var(--border)" : "var(--warn)"}`,
                  padding: "4px 2px", textAlign:"center", background: ok ? "transparent" : "rgba(251,191,36,.08)"
                }}>
                  <div className="mono" style={{ fontSize: 9, color: "var(--dim)" }}>C{String(i+1).padStart(2,"0")}</div>
                  <div className="mono" style={{ fontSize: 11, color: ok ? "var(--fg)" : "var(--warn)" }}>{v.toFixed(2)}V</div>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}

Object.assign(window, { HumanoidSkeleton, CameraFeed, RobotDetailScreen });
