// arm-path.jsx — trajectory analysis + editing screen

// Velocity profile chart with waypoint markers and playback scrubber
function VelocityChart({ profile, waypoints, playT, totalT, onScrub, height = 140, width = "100%" }) {
  const ref = React.useRef();
  const [w, setW] = React.useState(800);
  React.useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(es => setW(es[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  if (!profile || !profile.vel.length) return <div ref={ref} style={{ width, height }} />;

  const maxVel = Math.max(0.001, ...profile.vel);
  const maxAcc = Math.max(0.001, ...profile.acc);
  const H = height;
  const pad = 24;

  const velPath = profile.vel.map((v, i) => {
    const x = pad + (i / (profile.vel.length - 1)) * (w - pad * 2);
    const y = H - 18 - (v / maxVel) * (H - 36);
    return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  const velArea = velPath + ` L${w - pad},${H - 18} L${pad},${H - 18} Z`;

  const accPath = profile.acc.map((v, i) => {
    const x = pad + (i / (profile.acc.length - 1)) * (w - pad * 2);
    const y = H - 18 - (v / maxAcc) * (H - 36);
    return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");

  const playX = pad + (playT / totalT) * (w - pad * 2);

  const handleClick = (e) => {
    if (!onScrub) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const t = Math.max(0, Math.min(totalT, ((x - pad) / (w - pad * 2)) * totalT));
    onScrub(t);
  };

  return (
    <div ref={ref} style={{ width, position: "relative" }}>
      <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} onClick={handleClick} style={{ cursor: "crosshair", display: "block" }}>
        <defs>
          <linearGradient id="vp-grad" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#4ade80" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#4ade80" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* grid */}
        {[0.25, 0.5, 0.75].map(p => (
          <line key={p} x1={pad} y1={(H - 18) - p * (H - 36)} x2={w - pad} y2={(H - 18) - p * (H - 36)}
            stroke="rgba(120,180,200,.08)" strokeDasharray="2 3" />
        ))}
        <line x1={pad} y1={H - 18} x2={w - pad} y2={H - 18} stroke="rgba(120,180,200,.25)" />

        {/* waypoint markers */}
        {waypoints.map((wp, i) => {
          const x = pad + (wp.t / totalT) * (w - pad * 2);
          return (
            <g key={i}>
              <line x1={x} y1={6} x2={x} y2={H - 18} stroke="rgba(232,121,249,.25)" strokeDasharray="2 2" />
              <circle cx={x} cy={H - 18} r="3" fill="#e879f9" />
              <text x={x + 4} y={H - 6} fill="rgba(232,121,249,.75)" fontSize="9" fontFamily="JetBrains Mono">{i + 1}</text>
            </g>
          );
        })}

        {/* velocity area */}
        <path d={velArea} fill="url(#vp-grad)" />
        <path d={velPath} fill="none" stroke="#4ade80" strokeWidth="1.5" />
        {/* acceleration line */}
        <path d={accPath} fill="none" stroke="#fbbf24" strokeWidth="1.2" strokeDasharray="3 2" opacity="0.85" />

        {/* axis labels */}
        <text x="4" y="14" fill="rgba(74,222,128,.85)" fontSize="9" fontFamily="JetBrains Mono">VEL m/s · {maxVel.toFixed(2)} peak</text>
        <text x={w - 4} y="14" textAnchor="end" fill="rgba(251,191,36,.85)" fontSize="9" fontFamily="JetBrains Mono">ACC m/s² · {maxAcc.toFixed(2)} peak</text>
        <text x="4" y={H - 4} fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">0.00 s</text>
        <text x={w - 4} y={H - 4} textAnchor="end" fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">{totalT.toFixed(2)} s</text>

        {/* playback head */}
        <line x1={playX} y1={6} x2={playX} y2={H - 6} stroke="#fbbf24" strokeWidth="1.5" />
        <polygon points={`${playX - 4},6 ${playX + 4},6 ${playX},12`} fill="#fbbf24" />
        <text x={playX} y={H - 4} textAnchor="middle" fill="#fbbf24" fontSize="9" fontFamily="JetBrains Mono">{playT.toFixed(2)}s</text>
      </svg>
    </div>
  );
}

function PathScreen({ robot }) {
  const traj = window.GENERATED_TRAJECTORY || EXAMPLE_TRAJECTORY;
  const [playT, setPlayT] = React.useState(0);
  const [playing, setPlaying] = React.useState(false);
  const [speed, setSpeed] = React.useState(1);
  const [selWp, setSelWp] = React.useState(0);
  const [editTcp, setEditTcp] = React.useState(null);

  const markerRef = React.useRef([0, 0, 0]);

  // path samples + velocity profile (memoized)
  const pathPoints = React.useMemo(() => buildPathSamples(traj.waypoints, 200), []);
  const profile = React.useMemo(() => buildVelocityProfile(traj.waypoints, 200), []);

  // playback loop
  React.useEffect(() => {
    if (!playing) return;
    let raf;
    let last = performance.now();
    const step = (now) => {
      const dt = (now - last) / 1000;
      last = now;
      setPlayT(t => {
        const nt = t + dt * speed;
        if (nt >= traj.totalTime) {
          setPlaying(false);
          return traj.totalTime;
        }
        return nt;
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed]);

  // current state at playT
  const live = React.useMemo(() => interpolateAtTime(traj.waypoints, playT), [playT]);
  React.useEffect(() => {
    if (live) markerRef.current = live.tcp;
  }, [live]);

  // when selWp changes (or playT crosses), auto-select the active segment
  React.useEffect(() => {
    if (!playing) return;
    if (!live) return;
    setSelWp(live.segment);
  }, [live, playing]);

  const sel = traj.waypoints[selWp];
  const jumpTo = (i) => {
    setSelWp(i);
    setPlayT(traj.waypoints[i].t);
    setPlaying(false);
  };

  return (
    <div className="screen path">
      <div className="path-grid">
        {/* 3D path viewer */}
        <Panel title={`▸ TRAJECTORY · ${traj.name}`} right={
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span className="tag dim">ID</span>
            <span className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>{traj.id}</span>
            <span className="tag dim" style={{ marginLeft: 8 }}>BY</span>
            <span className="mono" style={{ fontSize: 10 }}>{traj.author}</span>
            <span className="tag dim" style={{ marginLeft: 8 }}>MODIFIED</span>
            <span className="mono" style={{ fontSize: 10 }}>2026-05-26 06:11</span>
          </div>
        } pad={false} style={{ gridColumn: "1 / span 2", gridRow: "1" }}>
          <div className="path-3d">
            <Arm3D
              jointAngles={live ? live.joints : traj.waypoints[0].joints}
              pathPoints={pathPoints}
              waypoints={traj.waypoints}
              selectedWaypoint={selWp}
              markerRef={markerRef}
              reach={robot ? robot.reach : 1.0}
              width="100%"
              height="100%"
            />
            <div className="cam-hud-tl">
              <div className="mono" style={{ color: "var(--ok)" }}>● PATH · 200 SAMPLES</div>
              <div className="mono dim" style={{ fontSize: 9 }}>{traj.waypoints.length} WAYPOINTS</div>
            </div>
            <div className="cam-hud-tr mono dim">drag · orbit  ·  scroll · zoom  ·  right · pan</div>

            {/* Playback controls */}
            <div className="play-bar">
              <button className="play-btn" onClick={() => setPlaying(p => !p)}>
                {playing ? "❚❚" : "▶"}
              </button>
              <button className="play-btn small" onClick={() => { setPlayT(0); setPlaying(false); }}>⏮</button>
              <button className="play-btn small" onClick={() => { setPlayT(traj.totalTime); setPlaying(false); }}>⏭</button>
              <div className="play-time mono">{playT.toFixed(2)} / {traj.totalTime.toFixed(2)}s</div>
              <input className="play-scrub" type="range" min="0" max={traj.totalTime} step="0.01"
                value={playT} onChange={e => { setPlayT(+e.target.value); setPlaying(false); }} />
              <div style={{ display: "flex", gap: 2 }}>
                {[0.25, 0.5, 1, 2].map(s =>
                  <button key={s} className={"chip" + (speed === s ? " on" : "")} onClick={() => setSpeed(s)}>{s}×</button>
                )}
              </div>
            </div>
          </div>
        </Panel>

        {/* Waypoint list */}
        <Panel title="WAYPOINTS" right={
          <div style={{ display: "flex", gap: 4 }}>
            <button className="chip">＋ INSERT</button>
            <button className="chip">DUP</button>
            <button className="chip">DEL</button>
          </div>
        } pad={false} style={{ gridColumn: "3", gridRow: "1 / span 2" }}>
          <div className="wplist">
            {traj.waypoints.map((wp, i) => {
              const isSel = i === selWp;
              const isCur = live && live.segment === i;
              return (
                <button key={wp.id} className={"wprow" + (isSel ? " sel" : "") + (isCur ? " cur" : "")}
                        onClick={() => jumpTo(i)}>
                  <div className="wprow-num">
                    <span className="mono">{String(i + 1).padStart(2, "0")}</span>
                    <span className={"wp-type " + (wp.type === "MoveL" ? "lin" : "joint")}>{wp.type}</span>
                  </div>
                  <div className="wprow-main">
                    <div className="mono wprow-name">{wp.name}</div>
                    <div className="wprow-meta mono">
                      <span>X {wp.tcp[0].toFixed(3)}</span>
                      <span>Y {wp.tcp[1].toFixed(3)}</span>
                      <span>Z {wp.tcp[2].toFixed(3)}</span>
                    </div>
                    <div className="wprow-meta mono">
                      <span style={{ color: "var(--fg-mute)" }}>v{wp.vel}%</span>
                      <span style={{ color: "var(--fg-mute)" }}>a{wp.acc}%</span>
                      <span style={{ color: wp.blend ? "var(--info)" : "var(--dim)" }}>r{wp.blend}</span>
                      {wp.dwell > 0 && <span style={{ color: "var(--warn)" }}>dwell {wp.dwell}s</span>}
                    </div>
                    {wp.io && (
                      <div className="wprow-io mono">
                        <span style={{ color: wp.io.value ? "var(--magenta)" : "var(--info)" }}>
                          {wp.io.label}
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="wprow-t mono">{wp.t.toFixed(2)}s</div>
                </button>
              );
            })}
          </div>
        </Panel>

        {/* Velocity profile */}
        <Panel title="MOTION PROFILE · TCP" right={
          <div style={{ display: "flex", gap: 10, fontSize: 10 }}>
            <span className="mono" style={{ color: "var(--ok)" }}>—— VEL</span>
            <span className="mono" style={{ color: "var(--warn)" }}>- - ACC</span>
            <span className="mono" style={{ color: "var(--magenta)" }}>| WAYPOINTS</span>
            <span className="tag dim">CLICK TO SCRUB</span>
          </div>
        } style={{ gridColumn: "1 / span 2", gridRow: "2" }}>
          <VelocityChart
            profile={profile}
            waypoints={traj.waypoints}
            playT={playT}
            totalT={traj.totalTime}
            onScrub={(t) => { setPlayT(t); setPlaying(false); }}
            height={160}
          />
        </Panel>

        {/* Selected waypoint editor */}
        <Panel title={`▸ EDIT · WP-${String(selWp + 1).padStart(2, "0")} · ${sel.name}`} style={{ gridColumn: "1 / span 2", gridRow: "3" }}>
          <div className="wp-edit-grid">
            <div className="wp-edit-col">
              <div className="form-row">
                <span className="tag dim">NAME</span>
                <input className="inp" defaultValue={sel.name} />
              </div>
              <div className="form-row">
                <span className="tag dim">MOVE TYPE</span>
                <div style={{ display: "flex", gap: 4 }}>
                  {["MoveJ","MoveL","MoveC","MoveP"].map(m =>
                    <button key={m} className={"chip" + (m === sel.type ? " on" : "")}>{m}</button>
                  )}
                </div>
              </div>
              <div className="form-row">
                <span className="tag dim">TIME · T</span>
                <input className="inp" defaultValue={`${sel.t.toFixed(2)}s`} />
              </div>
              <div className="form-row">
                <span className="tag dim">DWELL</span>
                <input className="inp" defaultValue={`${sel.dwell}s`} />
              </div>
            </div>

            <div className="wp-edit-col">
              <div className="tag dim">TCP POSE · base_link</div>
              <div className="wp-tcp">
                {[["X", "var(--err)"], ["Y", "var(--ok)"], ["Z", "var(--info)"]].map(([axis, col], i) =>
                  <div key={axis} className="wp-tcp-row">
                    <span className="tag" style={{ color: col, width: 16 }}>{axis}</span>
                    <input className="inp mono" defaultValue={sel.tcp[i].toFixed(3)} />
                    <span className="tag dim">m</span>
                  </div>
                )}
                {[["RX","var(--err)"],["RY","var(--ok)"],["RZ","var(--info)"]].map(([axis, col], i) =>
                  <div key={axis} className="wp-tcp-row">
                    <span className="tag" style={{ color: col, width: 16 }}>{axis}</span>
                    <input className="inp mono" defaultValue={sel.rot[i].toFixed(1)} />
                    <span className="tag dim">°</span>
                  </div>
                )}
              </div>
            </div>

            <div className="wp-edit-col">
              <div className="tag dim">JOINTS · J1-J6</div>
              <div className="wp-joints">
                {sel.joints.map((j, i) => (
                  <div key={i} className="wp-joint-row">
                    <span className="mono" style={{ fontSize: 9, color: "var(--ok)", width: 22 }}>J{i+1}</span>
                    <input className="inp mono" defaultValue={j.toFixed(2)} style={{ width: 70 }} />
                    <span className="tag dim">°</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="wp-edit-col">
              <div className="tag dim">MOTION · BLEND · I/O</div>
              <div className="form-row" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <span className="tag dim" style={{ width: 60 }}>VEL</span>
                <input type="range" min="1" max="100" defaultValue={sel.vel} className="slider" />
                <span className="mono" style={{ fontSize: 10, width: 40, textAlign: "right" }}>{sel.vel}%</span>
              </div>
              <div className="form-row" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <span className="tag dim" style={{ width: 60 }}>ACC</span>
                <input type="range" min="1" max="100" defaultValue={sel.acc} className="slider" />
                <span className="mono" style={{ fontSize: 10, width: 40, textAlign: "right" }}>{sel.acc}%</span>
              </div>
              <div className="form-row" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <span className="tag dim" style={{ width: 60 }}>BLEND r</span>
                <input type="range" min="0" max="100" defaultValue={sel.blend} className="slider" />
                <span className="mono" style={{ fontSize: 10, width: 40, textAlign: "right" }}>{sel.blend}mm</span>
              </div>
              <hr className="hr" />
              <div className="tag dim">I/O TRIGGER</div>
              {sel.io ? (
                <div className="iotrig">
                  <span className="mono" style={{ fontSize: 10, color: "var(--magenta)" }}>{sel.io.type}-{sel.io.ch}</span>
                  <span className="mono" style={{ fontSize: 10, color: sel.io.value ? "var(--magenta)" : "var(--info)" }}>{sel.io.value ? "HIGH" : "LOW"}</span>
                  <span className="mono" style={{ fontSize: 10, color: "var(--fg-mute)" }}>{sel.io.label}</span>
                  <button className="chip" style={{ marginLeft: "auto" }}>EDIT</button>
                </div>
              ) : (
                <button className="chip" style={{ width: "100%" }}>+ ADD I/O TRIGGER</button>
              )}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--border)" }}>
            <button className="btn primary">APPLY · LIVE</button>
            <button className="btn">TEACH FROM ARM</button>
            <button className="btn">GO TO THIS WP</button>
            <button className="btn">REVERSE PATH</button>
            <div style={{ flex: 1 }} />
            <button className="btn danger">DELETE WAYPOINT</button>
          </div>
        </Panel>

        {/* Metrics + analysis */}
        <Panel title="METRICS · ANALYSIS" style={{ gridColumn: "3", gridRow: "3" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <Stat label="CYCLE TIME" value={`${traj.totalTime.toFixed(2)}s`} color="var(--ok)" />
            <Stat label="PATH LEN" value={`${traj.pathLength.toFixed(2)}m`} />
            <Stat label="MAX TCP·v" value={`${traj.maxTCPSpeed.toFixed(2)} m/s`} />
            <Stat label="MAX J·vel" value={`${traj.maxJointVel.toFixed(0)} °/s`} />
            <Stat label="MAX J·acc" value={`${traj.maxJointAcc.toFixed(0)} °/s²`} />
            <Stat label="WAYPOINTS" value={traj.waypoints.length} />
          </div>
          <hr className="hr" />
          <div className="tag dim">CHECKS</div>
          {[
            ["SINGULARITY", traj.singularityWarnings, traj.singularityWarnings === 0 ? "var(--ok)" : "var(--warn)"],
            ["SELF-COLLISION", traj.collisionWarnings, traj.collisionWarnings === 0 ? "var(--ok)" : "var(--err)"],
            ["REACH", traj.reachWarnings, traj.reachWarnings === 0 ? "var(--ok)" : "var(--err)"],
            ["JOINT LIMITS", 0, "var(--ok)"],
            ["VEL LIMITS", 0, "var(--ok)"],
            ["ACC LIMITS", 0, "var(--ok)"],
          ].map(([k, n, c]) => (
            <div key={k} className="check-row">
              <span className="mono" style={{ fontSize: 10, color: c }}>{n === 0 ? "✓" : "✗"}</span>
              <span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span>
              <span className="mono" style={{ fontSize: 10, color: c, marginLeft: "auto" }}>{n === 0 ? "PASS" : `${n} ISSUE${n > 1 ? "S" : ""}`}</span>
            </div>
          ))}
          <hr className="hr" />
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn primary">RUN ON ROBOT ›</button>
            <button className="btn">SIMULATE</button>
            <button className="btn">EXPORT URPx</button>
            <button className="btn">EXPORT GCODE</button>
            <button className="btn">OPTIMIZE</button>
          </div>
        </Panel>
      </div>
    </div>
  );
}

Object.assign(window, { PathScreen, VelocityChart });
