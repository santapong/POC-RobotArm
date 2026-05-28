// PROGRAM screen: the Robotmaster-style operation tree. Reads job from
// useDocStore, mutates via apply() so every edit flows through undo/redo +
// autosave. Includes the NEW / SAVE / LOAD / undo / redo header buttons
// and the OPEN-IN-PATH hand-off.

import { useEffect, useMemo, useState } from "react";
import type { Job, OpKind, Operation, Part, Strategy } from "@/types";
import type { SurfaceHit } from "@/components/three/CAMViewer3D";
import { PART_LIBRARY, TCP_LIBRARY, TOOL_LIBRARY, findPart, findTool } from "@/lib/catalogs";
import { ROBOT_LIBRARY, resolveRobot } from "@/lib/robots";
import { setActiveTool } from "@/lib/three/fk";
import { approxIK } from "@/lib/cam";
import { compileJob, genPicks, makeOp, opTrajectory, postProgram } from "@/lib/program";
import { downloadDoc, makeDefaultDoc, openDocFile } from "@/lib/doc";
import { Panel, SplitScreen, Stat, type SplitNode } from "@/components/common";
import { CAMViewer3D } from "@/components/three/CAMViewer3D";
import { useCanRedo, useCanUndo, useDoc, useDocStore } from "@/store/useDocStore";
import { useUiStore } from "@/store/useUiStore";

interface Props { robot: { reach: number } | undefined; }

const OP_KIND_COLOR: Record<OpKind, string> = {
  PICKPLACE: "var(--info)", WELD: "var(--warn)", MILL: "var(--magenta)", DISPENSE: "var(--ok)",
};

export function ProgramScreen({ robot }: Props) {
  const doc = useDocStore(useDoc);
  const job: Job = doc.job;
  const apply = useDocStore(s => s.apply);
  const replace = useDocStore(s => s.replace);
  const undo = useDocStore(s => s.undo);
  const redo = useDocStore(s => s.redo);
  const canUndo = useDocStore(useCanUndo);
  const canRedo = useDocStore(useCanRedo);
  const openInPath = useUiStore(s => s.openInPath);

  const [selId, setSelId] = useState<number>(job.ops[0]?.id ?? 1);
  const [hover, setHover] = useState<SurfaceHit | null>(null);

  const setJob = (updater: (j: Job) => Job, label?: string) =>
    apply(d => { d.job = updater(d.job); }, label);

  const op: Operation | undefined = job.ops.find(o => o.id === selId) ?? job.ops[0];
  const part: Part | null = op ? findPart(op.partId) : null;
  const tool = op ? findTool(op.toolId) : null;
  const activeRobot = resolveRobot(doc.robotId);
  const setRobot = (id: string) => apply(d => { d.robotId = id; }, "robot");

  // Drive the FK / 3D viewer's active tool from the selected op. useEffect
  // (not useMemo) because this is a side effect, not a memoized value.
  useEffect(() => { if (op) setActiveTool(findTool(op.toolId)); }, [op?.toolId]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateOp = (id: number, patch: Partial<Operation>, label?: string) =>
    setJob(j => ({ ...j, ops: j.ops.map(o => o.id === id ? { ...o, ...patch } : o) }), label);
  const updateParams = (id: number, patch: Partial<Operation["params"]>, label?: string) =>
    setJob(j => ({ ...j, ops: j.ops.map(o => o.id === id ? { ...o, params: { ...o.params, ...patch } } : o) }), label);
  const setWeave = (patch: Partial<Operation["params"]["weave"]>, label?: string) => {
    if (!op) return;
    updateParams(op.id, { weave: { ...op.params.weave, ...patch } }, label);
  };

  const addOp = (kind: OpKind) => {
    const nid = Math.max(0, ...job.ops.map(o => o.id)) + 1;
    setJob(j => ({ ...j, ops: [...j.ops, makeOp(nid, kind)] }));
    setSelId(nid);
  };
  const delOp = (id: number) => {
    setJob(j => ({ ...j, ops: j.ops.filter(o => o.id !== id) }));
    if (id === selId) {
      const rest = job.ops.filter(o => o.id !== id);
      setSelId(rest.length ? rest[0].id : 0);
    }
  };
  const moveOp = (id: number, dir: -1 | 1) => {
    setJob(j => {
      const i = j.ops.findIndex(o => o.id === id), ni = i + dir;
      if (i < 0 || ni < 0 || ni >= j.ops.length) return j;
      const ops = j.ops.slice();
      [ops[i], ops[ni]] = [ops[ni], ops[i]];
      return { ...j, ops };
    });
  };
  const regenPicks = (strategy: Strategy) =>
    setJob(j => ({ ...j, ops: j.ops.map(o => o.id === selId ? { ...o, strategy, params: { ...o.params, picks: genPicks(strategy, findPart(o.partId)) } } : o) }));

  const handleClick = (hit: SurfaceHit) => {
    if (op) updateParams(op.id, { picks: [...(op.params.picks || []), hit] });
  };

  const opTraj = useMemo(() => op ? opTrajectory(op) : null, [op]);
  const compiled = useMemo(() => compileJob(job), [job]);
  const post = useMemo(() => postProgram(compiled, job), [compiled, job]);

  const liveJoints = useMemo(() => {
    if (hover) return approxIK(hover.point, hover.normal);
    const ps = op && op.params.picks;
    if (ps && ps.length) return approxIK(ps[ps.length - 1].point, ps[ps.length - 1].normal);
    return [0, -90, 0, 0, 90, 0];
  }, [hover, op]);

  const jobPanel = (
    <Panel title={`▸ JOB · ${job.name}`} pad={false}
      right={
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <span className="mono" style={{ fontSize: 10, color: "var(--ok)", marginRight: 2 }}>
            {job.ops.filter(o => o.enabled).length}/{job.ops.length} ON
          </span>
          <span className="chip" onClick={() => replace(makeDefaultDoc(), "new")}>NEW</span>
          <span className="chip" onClick={() => downloadDoc(doc)}>SAVE</span>
          <span className="chip" onClick={() => openDocFile().then(d => replace(d, "load")).catch(() => {})}>LOAD</span>
          <span className={"chip" + (canUndo ? "" : " disabled")} onClick={() => undo()}>↶</span>
          <span className={"chip" + (canRedo ? "" : " disabled")} onClick={() => redo()}>↷</span>
        </div>
      }>
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
                <span>{findTool(o.toolId)?.name ?? "—"}</span>
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
        {(["PICKPLACE", "WELD", "MILL", "DISPENSE"] as const).map(k =>
          <button key={k} className="chip" onClick={() => addOp(k)}>＋ {k}</button>
        )}
      </div>
    </Panel>
  );

  const previewPanel = (
    <Panel title={op ? `▸ ${op.name} · ${op.kind}` : "PREVIEW"} pad={false}>
      <div className="program-3d">
        {op && part && (
          <CAMViewer3D
            key={activeRobot.id + ":" + op.id + ":" + op.toolId}
            jointAngles={liveJoints}
            picks={op.params.picks}
            generatedTrajectory={opTraj}
            part={part} tool={tool} robot={activeRobot}
            onSurfaceClick={handleClick}
            onSurfaceHover={setHover}
          />
        )}
        <div className="cam-hud-tl">
          <div className="mono" style={{ color: "var(--ok)" }}>● {((op && op.params.picks) || []).length} PICKS</div>
          <div className="mono dim" style={{ fontSize: 9 }}>{opTraj ? opTraj.waypoints.length : 0} WAYPOINTS</div>
        </div>
      </div>
    </Panel>
  );

  const inspectorPanel = (
    <Panel title="OPERATION INSPECTOR">
      {/* Project-level robot selection (saved in Doc.robotId). Above the
          op-specific fields so it's clearly not per-op. */}
      <div className="tag dim">PROJECT · ROBOT</div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "4px 0 4px" }}>
        {ROBOT_LIBRARY.map(r => (
          <button key={r.id}
            className={"chip" + (activeRobot.id === r.id ? " on" : "")}
            title={`${r.manufacturer} · ${r.payload}kg · ${(r.reach * 1000).toFixed(0)}mm reach`}
            onClick={() => setRobot(r.id)}>
            {r.name}
          </button>
        ))}
      </div>
      <div className="mono dim" style={{ fontSize: 10, marginBottom: 8 }}>
        {activeRobot.manufacturer} · {activeRobot.payload}kg · {(activeRobot.reach * 1000).toFixed(0)}mm reach · {activeRobot.dof}-DoF
      </div>
      <hr className="hr" />
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
                onClick={() => setJob(j => ({ ...j, ops: j.ops.map(o => o.id === op.id ? { ...o, partId: p.id, params: { ...o.params, picks: genPicks(o.strategy, findPart(p.id)) } } : o) }))}>
                {p.name}
              </button>
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
            {(["POINTS","CONTOUR","RASTER","SEAM"] as const).map(s => (
              <button key={s} className={"chip" + (op.strategy === s ? " on" : "")} onClick={() => regenPicks(s)}>{s}</button>
            ))}
            <button className="chip danger-chip" onClick={() => updateParams(op.id, { picks: [] })}>CLEAR</button>
          </div>

          {([
            ["standoff", "STANDOFF",   0,   50, "mm"],
            ["approach", "APPROACH",  10,  200, "mm"],
            ["vel",      "TCP SPEED",  5,  100, "%"],
            ["acc",      "ACCEL",      5,  100, "%"],
          ] as const).map(([k, lbl, mn, mx, u]) => (
            <div key={k} className="cam-slider">
              <div className="cam-slider-h"><span className="tag dim">{lbl}</span>
                <span className="mono" style={{ color: "var(--ok)" }}>{op.params[k]} {u}</span></div>
              <input type="range" className="slider" min={mn} max={mx}
                value={op.params[k]}
                onChange={e => updateParams(op.id, { [k]: +e.target.value } as Partial<Operation["params"]>, "p:" + k + ":" + op.id)} />
            </div>
          ))}

          {op.kind === "WELD" && (
            <>
              <hr className="hr" />
              <div className="tag dim">WEAVE</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "4px 0" }}>
                {(["NONE","ZIGZAG","SINE","TRIANGLE","TRAPEZOID"] as const).map(w =>
                  <button key={w} className={"chip" + (op.params.weave.type === w ? " on" : "")} onClick={() => setWeave({ type: w })}>{w}</button>
                )}
              </div>
              {op.params.weave.type !== "NONE" && (
                <>
                  <div className="cam-slider"><div className="cam-slider-h"><span className="tag dim">AMPLITUDE</span>
                      <span className="mono" style={{ color: "var(--ok)" }}>{(op.params.weave.amplitude * 1000).toFixed(0)} mm</span></div>
                    <input type="range" className="slider" min="0.001" max="0.02" step="0.001" value={op.params.weave.amplitude}
                      onChange={e => setWeave({ amplitude: +e.target.value }, "weave:amp:" + op.id)} /></div>
                  <div className="cam-slider"><div className="cam-slider-h"><span className="tag dim">WAVELENGTH</span>
                      <span className="mono" style={{ color: "var(--ok)" }}>{(op.params.weave.wavelength * 1000).toFixed(0)} mm</span></div>
                    <input type="range" className="slider" min="0.004" max="0.04" step="0.001" value={op.params.weave.wavelength}
                      onChange={e => setWeave({ wavelength: +e.target.value }, "weave:wl:" + op.id)} /></div>
                </>
              )}
            </>
          )}
        </>
      )}
    </Panel>
  );

  const postPanel = (
    <Panel title={`POST · ${job.postFormat}`} pad={false}
      right={
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {(["URScript", "GCODE", "RAPID"] as const).map(f =>
            <button key={f} className={"chip" + (job.postFormat === f ? " on" : "")}
              onClick={() => setJob(j => ({ ...j, postFormat: f }))}>{f}</button>
          )}
        </div>
      }>
      <div className="post-output">{post}</div>
    </Panel>
  );

  const compilePanel = (
    <Panel title="PROGRAM · COMPILE">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <Stat label="OPERATIONS" value={job.ops.filter(o => o.enabled).length} color="var(--ok)" />
        <Stat label="WAYPOINTS" value={compiled.waypoints.length} />
        <Stat label="CYCLE TIME" value={`${compiled.totalTime.toFixed(2)}s`} />
        <Stat label="PATH LEN" value={`${compiled.pathLength.toFixed(2)}m`} />
      </div>
      <hr className="hr" />
      <div className="tag dim">CHECKS</div>
      {([
        ["SINGULARITY", compiled.singularityWarnings],
        ["SELF-COLLISION", compiled.collisionWarnings],
        ["REACH", compiled.reachWarnings],
      ] as const).map(([k, n]) => (
        <div key={k} className="check-row">
          <span className="mono" style={{ fontSize: 10, color: n === 0 ? "var(--ok)" : "var(--err)" }}>{n === 0 ? "✓" : "✗"}</span>
          <span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span>
          <span className="mono" style={{ fontSize: 10, color: n === 0 ? "var(--ok)" : "var(--err)", marginLeft: "auto" }}>{n === 0 ? "PASS" : n}</span>
        </div>
      ))}
      <hr className="hr" />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <button className="btn primary" disabled={!compiled.waypoints.length} onClick={() => openInPath(compiled)}>OPEN IN PATH ›</button>
        <button className="btn">SIMULATE</button>
        <button className="btn">EXPORT</button>
      </div>
    </Panel>
  );

  const layout: SplitNode = {
    type: "split", direction: "v", key: "root",
    children: [
      { type: "split", direction: "h", key: "top", size: 60, children: [
        { type: "leaf", key: "job", size: 22, content: jobPanel },
        { type: "leaf", key: "preview", size: 48, content: previewPanel },
        { type: "leaf", key: "inspector", size: 30, content: inspectorPanel },
      ]},
      { type: "split", direction: "h", key: "bot", size: 40, children: [
        { type: "leaf", key: "post", size: 70, content: postPanel },
        { type: "leaf", key: "compile", size: 30, content: compilePanel },
      ]},
    ],
  };

  return (
    <>
      <SplitScreen id="program" className="screen program" node={layout} />
      {void robot}
    </>
  );
}
