// arm-program.jsx — Robotmaster-style PROGRAM hub: an operation tree where each
// operation binds {part, tool, TCP, strategy, params}; ops compile/post into one
// combined trajectory that hands off to the PATH editor.
// Loaded AFTER arm-cam.jsx (uses generateCAMTrajectory) and arm-tooling.jsx.

// ── footprint / pattern helpers ─────────────────────────────────────────────
function partFootprint(part) {
  const d = part.dims, c = part.pose.pos, y = partTopY(part);
  let wx, wz;
  if (part.kind === "CYLINDER") { wx = wz = d.r; }
  else if (part.kind === "STEP") { wx = d.topW / 2; wz = d.topD / 2; }
  else { wx = d.w / 2; wz = d.d / 2; }
  const inset = 0.04;
  return { x0: c[0] - wx + inset, x1: c[0] + wx - inset, z0: c[2] - wz + inset, z1: c[2] + wz - inset, y };
}

function genPicks(strategy, part) {
  const { x0, x1, z0, z1, y } = partFootprint(part);
  const n = [0, 1, 0];
  if (strategy === "CONTOUR") return [
    { point: [x0, y, z0], normal: n }, { point: [x1, y, z0], normal: n },
    { point: [x1, y, z1], normal: n }, { point: [x0, y, z1], normal: n }, { point: [x0, y, z0], normal: n },
  ];
  if (strategy === "RASTER") {
    const pts = [], passes = 5;
    for (let i = 0; i < passes; i++) {
      const z = z0 + (z1 - z0) * (i / (passes - 1));
      if (i % 2 === 0) { pts.push({ point: [x0, y, z], normal: n }); pts.push({ point: [x1, y, z], normal: n }); }
      else { pts.push({ point: [x1, y, z], normal: n }); pts.push({ point: [x0, y, z], normal: n }); }
    }
    return pts;
  }
  if (strategy === "SEAM") { const z = (z0 + z1) / 2; return [{ point: [x0, y, z], normal: n }, { point: [x1, y, z], normal: n }]; }
  return [{ point: [(x0 + x1) / 2, y, (z0 + z1) / 2], normal: n }]; // POINTS (single)
}

// ── compile the job into one trajectory ─────────────────────────────────────
function opTrajectory(op) {
  return generateCAMTrajectory(op.params.picks || [], {
    standoff: (op.params.standoff || 5) / 1000,
    approachHeight: (op.params.approach || 60) / 1000,
    vel: op.params.vel || 30, acc: op.params.acc || 40,
    tool: findTool(op.toolId),
    weave: op.kind === "WELD" ? op.params.weave : null,
  });
}

function compileJob(job) {
  const all = [];
  let tOffset = 0, pathLength = 0, sing = 0, coll = 0, reach = 0, idc = 0;
  (job.ops || []).filter(o => o.enabled).forEach((op) => {
    const t = opTrajectory(op);
    if (!t) return;
    t.waypoints.forEach((wp, wi) => {
      // drop a leading HOME only once we've already emitted waypoints, so the
      // program always starts with a HOME even if earlier ops produced nothing
      if (all.length > 0 && wi === 0 && wp.name === "HOME") return;
      all.push({ ...wp, id: ++idc, t: +(wp.t + tOffset).toFixed(3), op: op.name });
    });
    if (all.length) tOffset = all[all.length - 1].t;
    pathLength += t.pathLength || 0;
    sing += t.singularityWarnings || 0; coll += t.collisionWarnings || 0; reach += t.reachWarnings || 0;
  });
  return {
    id: "JOB-" + (job.id || "0"), name: job.name || "PROGRAM", author: job.author || "OP",
    tool: "MULTI", payload: 0,
    waypoints: all, totalTime: all.length ? all[all.length - 1].t : 0,
    pathLength, maxTCPSpeed: 0.84, maxJointVel: 142, maxJointAcc: 540,
    singularityWarnings: sing, collisionWarnings: coll, reachWarnings: reach,
  };
}

function postProgram(compiled, job) {
  const tcp = findTcp(job.activeTcpId) || { offset: [0, 0, 0] };
  const L = [];
  L.push(`# ${job.name}  ·  ${job.author}`);
  L.push(`# ${job.ops.filter(o => o.enabled).length} ops · ${compiled.waypoints.length} waypoints · ${compiled.totalTime.toFixed(2)}s · ${job.postFormat}`);
  L.push(`set_tcp(p[${tcp.offset.map(v => v.toFixed(3)).join(", ")}])`);
  L.push("");
  let cur = null;
  compiled.waypoints.forEach(wp => {
    if (wp.op !== cur) { cur = wp.op; L.push(`# — ${cur} —`); }
    const m = wp.type === "MoveL" ? "movel" : "movej";
    L.push(`${m}([${wp.joints.map(j => (j * Math.PI / 180).toFixed(3)).join(", ")}], a=${(wp.acc / 50).toFixed(2)}, v=${(wp.vel / 60).toFixed(2)}${wp.blend ? `, r=${(wp.blend / 1000).toFixed(3)}` : ""})`);
    if (wp.io) L.push(`set_digital_out(${wp.io.ch}, ${wp.io.value ? "True" : "False"})`);
    if (wp.dwell) L.push(`sleep(${wp.dwell})`);
  });
  L.push("");
  L.push("END");
  return L.join("\n");
}

const OP_KIND_COLOR = { PICKPLACE: "var(--info)", WELD: "var(--warn)", MILL: "var(--magenta)", DISPENSE: "var(--ok)" };
const OP_DEFAULT_TOOL = { PICKPLACE: "grip-2f", WELD: "mig", MILL: "spindle", DISPENSE: "disp" };
const OP_DEFAULT_PART = { PICKPLACE: "part-box", WELD: "part-plate", MILL: "part-box", DISPENSE: "part-plate" };

const DEFAULT_JOB = {
  id: "0142", name: "CELL-07 PROGRAM", author: "OP·KOSTA", activeTcpId: "tcp-tip", postFormat: "URScript",
  ops: [
    { id: 1, name: "PICK BLANK", enabled: true, kind: "PICKPLACE", partId: "part-box", toolId: "grip-2f", tcpId: "tcp-tip", strategy: "POINTS",
      params: { standoff: 5, approach: 60, vel: 40, acc: 50, weave: { ...WEAVE_DEFAULT }, picks: [{ point: [0.5, 0.15, 0], normal: [0, 1, 0] }] } },
    { id: 2, name: "WELD SEAM", enabled: true, kind: "WELD", partId: "part-plate", toolId: "mig", tcpId: "tcp-weld", strategy: "SEAM",
      params: { standoff: 2, approach: 50, vel: 25, acc: 40, weave: { type: "SINE", amplitude: 0.004, wavelength: 0.012, edgeDwell: 0.05 },
        picks: [{ point: [0.40, 0.02, 0], normal: [0, 1, 0] }, { point: [0.60, 0.02, 0], normal: [0, 1, 0] }] } },
  ],
};

function ProgramScreen({ robot, onGoto }) {
  const [job, setJob] = React.useState(() => JSON.parse(JSON.stringify(DEFAULT_JOB)));
  const [selId, setSelId] = React.useState(1);
  const [hover, setHover] = React.useState(null);

  const op = job.ops.find(o => o.id === selId) || job.ops[0];
  const part = op ? findPart(op.partId) : null;
  const tool = op ? findTool(op.toolId) : null;

  // make the selected op's tool active so 3D/FK/IK all use it
  React.useEffect(() => { if (op) setActiveTool(findTool(op.toolId)); }, [op && op.toolId]);

  const updateOp = (id, patch) => setJob(j => ({ ...j, ops: j.ops.map(o => o.id === id ? { ...o, ...patch } : o) }));
  const updateParams = (id, patch) => setJob(j => ({ ...j, ops: j.ops.map(o => o.id === id ? { ...o, params: { ...o.params, ...patch } } : o) }));
  const setWeave = (patch) => updateParams(selId, { weave: { ...op.params.weave, ...patch } });

  const addOp = (kind) => {
    const nid = Math.max(0, ...job.ops.map(o => o.id)) + 1;
    const newOp = {
      id: nid, name: `${kind} ${nid}`, enabled: true, kind,
      partId: OP_DEFAULT_PART[kind], toolId: OP_DEFAULT_TOOL[kind], tcpId: "tcp-tip",
      strategy: kind === "WELD" ? "SEAM" : "POINTS",
      params: { standoff: 5, approach: 60, vel: 30, acc: 40,
        weave: kind === "WELD" ? { type: "SINE", amplitude: 0.004, wavelength: 0.012, edgeDwell: 0.05 } : { ...WEAVE_DEFAULT },
        picks: genPicks(kind === "WELD" ? "SEAM" : "POINTS", findPart(OP_DEFAULT_PART[kind])) },
    };
    setJob(j => ({ ...j, ops: [...j.ops, newOp] }));
    setSelId(nid);
  };
  const delOp = (id) => {
    setJob(j => ({ ...j, ops: j.ops.filter(o => o.id !== id) }));
    // if the deleted op was selected, move selection to a surviving op so the
    // inspector + surface-clicks don't keep targeting a now-missing id
    if (id === selId) {
      const rest = job.ops.filter(o => o.id !== id);
      setSelId(rest.length ? rest[0].id : null);
    }
  };
  const moveOp = (id, dir) => setJob(j => {
    const i = j.ops.findIndex(o => o.id === id), ni = i + dir;
    if (i < 0 || ni < 0 || ni >= j.ops.length) return j;
    const ops = j.ops.slice();[ops[i], ops[ni]] = [ops[ni], ops[i]];
    return { ...j, ops };
  });
  const regenPicks = (strategy) => { updateOp(selId, { strategy }); updateParams(selId, { picks: genPicks(strategy, part) }); };

  const handleClick = (hit) => updateParams(selId, { picks: [...(op.params.picks || []), hit] });

  const opTraj = React.useMemo(() => op ? opTrajectory(op) : null, [op]);
  const compiled = React.useMemo(() => compileJob(job), [job]);
  const post = React.useMemo(() => postProgram(compiled, job), [compiled, job]);

  const liveJoints = React.useMemo(() => {
    if (hover) return approxIK(hover.point, hover.normal);
    const ps = op && op.params.picks;
    if (ps && ps.length) return approxIK(ps[ps.length - 1].point, ps[ps.length - 1].normal);
    return [0, -90, 0, 0, 90, 0];
  }, [hover, op]);

  return (
    <div className="screen program">
      <div className="program-grid">
        {/* OPERATION TREE */}
        <Panel title={`▸ JOB · ${job.name}`} right={
          <span className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>{job.ops.filter(o => o.enabled).length}/{job.ops.length} ON</span>
        } pad={false} style={{ gridColumn: "1", gridRow: "1" }}>
          <div className="op-tree">
            {job.ops.map((o, i) => (
              <button key={o.id} className={"op-row" + (o.id === selId ? " sel" : "") + (o.enabled ? "" : " disabled")}
                      onClick={() => setSelId(o.id)}>
                <span className="mono" style={{ fontSize: 11, color: o.enabled ? "var(--ok)" : "var(--dim)" }}
                      onClick={(e) => { e.stopPropagation(); updateOp(o.id, { enabled: !o.enabled }); }}>
                  {o.enabled ? "◉" : "○"}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span className="mono" style={{ fontSize: 11, color: "var(--fg)" }}>{String(i + 1).padStart(2, "0")} {o.name}</span>
                  <span className="op-meta mono" style={{ display: "flex", gap: 8, fontSize: 9, color: "var(--fg-mute)", marginTop: 1 }}>
                    <span style={{ color: OP_KIND_COLOR[o.kind] }}>{o.kind}</span>
                    <span>{findTool(o.toolId) ? findTool(o.toolId).name : "—"}</span>
                    <span>{(o.params.picks || []).length}pt</span>
                  </span>
                </span>
                <span style={{ display: "flex", gap: 2 }}>
                  <span className="chip" style={{ padding: "1px 5px" }} onClick={(e) => { e.stopPropagation(); moveOp(o.id, -1); }}>▲</span>
                  <span className="chip" style={{ padding: "1px 5px" }} onClick={(e) => { e.stopPropagation(); moveOp(o.id, 1); }}>▼</span>
                  <span className="chip danger-chip" style={{ padding: "1px 5px" }} onClick={(e) => { e.stopPropagation(); delOp(o.id); }}>✕</span>
                </span>
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", padding: 8, borderTop: "1px solid var(--border)" }}>
            {["PICKPLACE", "WELD", "MILL", "DISPENSE"].map(k =>
              <button key={k} className="chip" onClick={() => addOp(k)}>＋ {k}</button>
            )}
          </div>
        </Panel>

        {/* 3D PREVIEW */}
        <Panel title={op ? `▸ ${op.name} · ${op.kind}` : "PREVIEW"} right={
          <span className="cam-hud-tr mono dim">click surface · add pt</span>
        } pad={false} style={{ gridColumn: "2", gridRow: "1" }}>
          <div className="program-3d">
            {op && part && (
              <CAMViewer3D
                key={op.id + ":" + op.toolId}
                jointAngles={liveJoints}
                picks={op.params.picks}
                generatedTrajectory={opTraj}
                part={part}
                tool={tool}
                onSurfaceClick={handleClick}
                onSurfaceHover={setHover}
                reach={robot ? robot.reach : 1.0}
              />
            )}
            <div className="cam-hud-tl">
              <div className="mono" style={{ color: "var(--ok)" }}>● {(op && op.params.picks || []).length} PICKS</div>
              <div className="mono dim" style={{ fontSize: 9 }}>{opTraj ? opTraj.waypoints.length : 0} WAYPOINTS</div>
            </div>
          </div>
        </Panel>

        {/* INSPECTOR */}
        <Panel title="OPERATION INSPECTOR" style={{ gridColumn: "3", gridRow: "1" }}>
          {!op ? <div className="mono dim" style={{ padding: 10 }}>No operation selected.</div> : (
            <>
              <div className="form-row">
                <span className="tag dim">NAME</span>
                <input className="inp" value={op.name} onChange={e => updateOp(op.id, { name: e.target.value })} />
              </div>
              <div className="tag dim">TOOL</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "4px 0 8px" }}>
                {TOOL_LIBRARY.map(t =>
                  <button key={t.id} className={"chip" + (op.toolId === t.id ? " on" : "")} onClick={() => updateOp(op.id, { toolId: t.id })}>{t.name}</button>
                )}
              </div>
              <div className="tag dim">PART</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "4px 0 8px" }}>
                {PART_LIBRARY.map(p =>
                  <button key={p.id} className={"chip" + (op.partId === p.id ? " on" : "")}
                          onClick={() => { updateOp(op.id, { partId: p.id }); updateParams(op.id, { picks: genPicks(op.strategy, findPart(p.id)) }); }}>{p.name}</button>
                )}
              </div>
              <div className="form-row" style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                <span className="tag dim">TCP</span>
                <select className="inp" value={op.tcpId} onChange={e => updateOp(op.id, { tcpId: e.target.value })}>
                  {TCP_LIBRARY.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>

              <hr className="hr" />
              <div className="tag dim">STRATEGY</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "4px 0 8px" }}>
                {["POINTS", "CONTOUR", "RASTER", "SEAM"].map(s =>
                  <button key={s} className={"chip" + (op.strategy === s ? " on" : "")} onClick={() => regenPicks(s)}>{s}</button>
                )}
                <button className="chip danger-chip" onClick={() => updateParams(op.id, { picks: [] })}>CLEAR</button>
              </div>

              {[["standoff", "STANDOFF", 0, 50, "mm"], ["approach", "APPROACH", 10, 200, "mm"], ["vel", "TCP SPEED", 5, 100, "%"], ["acc", "ACCEL", 5, 100, "%"]].map(([k, lbl, mn, mx, u]) => (
                <div key={k} className="cam-slider">
                  <div className="cam-slider-h"><span className="tag dim">{lbl}</span>
                    <span className="mono" style={{ color: "var(--ok)" }}>{op.params[k]} {u}</span></div>
                  <input type="range" className="slider" min={mn} max={mx} value={op.params[k]} onChange={e => updateParams(op.id, { [k]: +e.target.value })} />
                </div>
              ))}

              {op.kind === "WELD" && (
                <>
                  <hr className="hr" />
                  <div className="tag dim">WEAVE</div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "4px 0" }}>
                    {["NONE", "ZIGZAG", "SINE", "TRIANGLE", "TRAPEZOID"].map(w =>
                      <button key={w} className={"chip" + (op.params.weave.type === w ? " on" : "")} onClick={() => setWeave({ type: w })}>{w}</button>
                    )}
                  </div>
                  {op.params.weave.type !== "NONE" && (
                    <>
                      <div className="cam-slider">
                        <div className="cam-slider-h"><span className="tag dim">AMPLITUDE</span>
                          <span className="mono" style={{ color: "var(--ok)" }}>{(op.params.weave.amplitude * 1000).toFixed(0)} mm</span></div>
                        <input type="range" className="slider" min="0.001" max="0.02" step="0.001"
                          value={op.params.weave.amplitude} onChange={e => setWeave({ amplitude: +e.target.value })} />
                      </div>
                      <div className="cam-slider">
                        <div className="cam-slider-h"><span className="tag dim">WAVELENGTH</span>
                          <span className="mono" style={{ color: "var(--ok)" }}>{(op.params.weave.wavelength * 1000).toFixed(0)} mm</span></div>
                        <input type="range" className="slider" min="0.004" max="0.04" step="0.001"
                          value={op.params.weave.wavelength} onChange={e => setWeave({ wavelength: +e.target.value })} />
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </Panel>

        {/* POST OUTPUT */}
        <Panel title={`POST · ${job.postFormat}`} right={
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {["URScript", "GCODE", "RAPID"].map(f =>
              <button key={f} className={"chip" + (job.postFormat === f ? " on" : "")} onClick={() => setJob(j => ({ ...j, postFormat: f }))}>{f}</button>
            )}
          </div>
        } pad={false} style={{ gridColumn: "1 / span 2", gridRow: "2" }}>
          <div className="post-output">{post}</div>
        </Panel>

        {/* COMPILE / METRICS */}
        <Panel title="PROGRAM · COMPILE" style={{ gridColumn: "3", gridRow: "2" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <Stat label="OPERATIONS" value={job.ops.filter(o => o.enabled).length} color="var(--ok)" />
            <Stat label="WAYPOINTS" value={compiled.waypoints.length} />
            <Stat label="CYCLE TIME" value={`${compiled.totalTime.toFixed(2)}s`} />
            <Stat label="PATH LEN" value={`${compiled.pathLength.toFixed(2)}m`} />
          </div>
          <hr className="hr" />
          <div className="tag dim">CHECKS</div>
          {[["SINGULARITY", compiled.singularityWarnings], ["SELF-COLLISION", compiled.collisionWarnings], ["REACH", compiled.reachWarnings]].map(([k, n]) => (
            <div key={k} className="check-row">
              <span className="mono" style={{ fontSize: 10, color: n === 0 ? "var(--ok)" : "var(--err)" }}>{n === 0 ? "✓" : "✗"}</span>
              <span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span>
              <span className="mono" style={{ fontSize: 10, color: n === 0 ? "var(--ok)" : "var(--err)", marginLeft: "auto" }}>{n === 0 ? "PASS" : n}</span>
            </div>
          ))}
          <hr className="hr" />
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn primary" disabled={!compiled.waypoints.length} onClick={() => {
              window.GENERATED_TRAJECTORY = compiled; onGoto("path");
            }}>OPEN IN PATH ›</button>
            <button className="btn">SIMULATE</button>
            <button className="btn">EXPORT</button>
          </div>
        </Panel>
      </div>
    </div>
  );
}

Object.assign(window, { ProgramScreen, compileJob, opTrajectory, postProgram, genPicks });
