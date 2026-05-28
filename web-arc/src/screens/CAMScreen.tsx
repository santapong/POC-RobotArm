// CAM screen: pick a part, click its top surface (or auto-generate
// CONTOUR/RASTER/SEAM), tune machining params + weld weave, hand off the
// generated trajectory to PATH.

import { useEffect, useMemo, useState } from "react";
import type { Part, Pick, Robot, Tool, Weave } from "@/types";
import { PART_LIBRARY, TOOL_LIBRARY, findTool } from "@/lib/catalogs";
import { partTopY } from "@/lib/three/part-mesh";
import { approxIK, generateCAMTrajectory } from "@/lib/cam";
import { setActiveTool } from "@/lib/three/fk";
import { Panel, Stat } from "@/components/common";
import { CAMViewer3D, type SurfaceHit } from "@/components/three/CAMViewer3D";
import { useUiStore } from "@/store/useUiStore";
import { useDocStore } from "@/store/useDocStore";
import { resolveRobot } from "@/lib/robots";

export interface CAMScreenProps { robot: Robot | undefined; }

const cloneJSON = <T,>(o: T): T => JSON.parse(JSON.stringify(o));

export function CAMScreen({ robot }: CAMScreenProps) {
  const openInPath = useUiStore(s => s.openInPath);
  const robotId = useDocStore(s => s.doc.robotId);
  const activeRobot = resolveRobot(robotId);

  const [toolId, setToolId] = useState("grip-2f");
  const [part, setPart] = useState<Part>(() => cloneJSON(PART_LIBRARY[0]));
  const [mode, setMode] = useState<"POINT" | "POLY" | "CONTOUR">("POLY");
  const [standoff, setStandoff] = useState(5);
  const [approach, setApproach] = useState(60);
  const [vel, setVel] = useState(30);
  const [acc, setAcc] = useState(40);
  const [orient, setOrient] = useState<"NORMAL" | "FIXED_Z" | "TANGENT">("NORMAL");
  const [weaveType, setWeaveType] = useState<Weave["type"]>("NONE");
  const [weaveAmp, setWeaveAmp] = useState(4);
  const [weaveWl, setWeaveWl] = useState(12);
  const [weaveDwell, setWeaveDwell] = useState(0.05);
  const [picks, setPicks] = useState<Pick[]>([]);
  const [hover, setHover] = useState<SurfaceHit | null>(null);

  const weave: Weave = { type: weaveType, amplitude: weaveAmp / 1000, wavelength: weaveWl / 1000, edgeDwell: weaveDwell };
  const tool: Tool | null = findTool(toolId);
  useEffect(() => { setActiveTool(findTool(toolId)); }, [toolId]);

  const setKind = (kind: Part["kind"]) => {
    const def = PART_LIBRARY.find(p => p.kind === kind) ?? PART_LIBRARY[0];
    setPart(cloneJSON(def));
    setPicks([]);
  };
  const setDim = (k: string, v: number) => setPart(p => ({ ...p, dims: { ...p.dims, [k]: v } }));
  const setPosX = (v: number) => setPart(p => ({ ...p, pose: { ...p.pose, pos: [v, p.pose.pos[1], p.pose.pos[2]] } }));
  const setPosZ = (v: number) => setPart(p => ({ ...p, pose: { ...p.pose, pos: [p.pose.pos[0], p.pose.pos[1], v] } }));

  const footprint = () => {
    const d = part.dims; const c = part.pose.pos; const y = partTopY(part);
    let wx: number, wz: number;
    if (part.kind === "CYLINDER") { wx = wz = d.r; }
    else if (part.kind === "STEP") { wx = d.topW / 2; wz = d.topD / 2; }
    else { wx = d.w / 2; wz = d.d / 2; }
    const inset = 0.04;
    return { x0: c[0] - wx + inset, x1: c[0] + wx - inset, z0: c[2] - wz + inset, z1: c[2] + wz - inset, y };
  };
  const generateContour = () => {
    const { x0, x1, z0, z1, y } = footprint(); const n: [number,number,number] = [0,1,0];
    setPicks([
      { point: [x0,y,z0], normal: n }, { point: [x1,y,z0], normal: n },
      { point: [x1,y,z1], normal: n }, { point: [x0,y,z1], normal: n },
      { point: [x0,y,z0], normal: n },
    ]);
  };
  const generateRaster = () => {
    const { x0, x1, z0, z1, y } = footprint(); const n: [number,number,number] = [0,1,0];
    const pts: Pick[] = []; const passes = 5;
    for (let i = 0; i < passes; i++) {
      const z = z0 + (z1 - z0) * (i / (passes - 1));
      if (i % 2 === 0) { pts.push({ point: [x0,y,z], normal: n }); pts.push({ point: [x1,y,z], normal: n }); }
      else { pts.push({ point: [x1,y,z], normal: n }); pts.push({ point: [x0,y,z], normal: n }); }
    }
    setPicks(pts);
  };
  const generateSeam = () => {
    const f = footprint(); const z = (f.z0 + f.z1) / 2; const n: [number,number,number] = [0,1,0];
    setPicks([{ point: [f.x0, f.y, z], normal: n }, { point: [f.x1, f.y, z], normal: n }]);
  };

  const traj = useMemo(() => {
    if (picks.length === 0) return null;
    return generateCAMTrajectory(picks, {
      standoff: standoff / 1000, approachHeight: approach / 1000,
      vel, acc, tool, weave,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picks, standoff, approach, vel, acc, toolId, weaveType, weaveAmp, weaveWl, weaveDwell, part]);

  const liveJoints = useMemo(() => {
    if (hover) return approxIK(hover.point, hover.normal);
    if (picks.length > 0) {
      const last = picks[picks.length - 1];
      return approxIK(last.point, last.normal);
    }
    return [0, -90, 0, 0, 90, 0];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hover, picks, toolId]);

  return (
    <div className="screen cam">
      <div className="cam-grid">
        <Panel title="CAM · CLICK SURFACE TO DEFINE PATH" pad={false} style={{ gridColumn: "1 / span 2", gridRow: "1 / span 2" }}
          right={
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span className="tag dim">PART</span>
              {(["BOX","CYLINDER","PLATE","STEP"] as const).map(k =>
                <button key={k} className={"chip" + (part.kind === k ? " on" : "")} onClick={() => setKind(k)}>{k}</button>
              )}
            </div>
          }>
          <div className="cam-3d">
            <CAMViewer3D
              key={activeRobot.id + ":" + toolId}
              jointAngles={liveJoints}
              picks={picks}
              generatedTrajectory={traj}
              part={part} tool={tool} robot={activeRobot}
              onSurfaceClick={(hit) => setPicks(p => [...p, hit])}
              onSurfaceHover={setHover}
            />
            <div className="cam-hud">
              <div className="cam-hud-row">
                <span className="mono" style={{ color: "var(--ok)" }}>● {picks.length} PICK{picks.length !== 1 ? "S" : ""}</span>
                {hover && (
                  <>
                    <span className="tag dim">HOVER</span>
                    <span className="mono" style={{ fontSize: 10, color: "var(--warn)" }}>
                      X {hover.point[0].toFixed(3)}  Y {hover.point[1].toFixed(3)}  Z {hover.point[2].toFixed(3)}
                    </span>
                  </>
                )}
              </div>
              <div className="cam-hud-row">
                <span className="tag dim">CLICK SURFACE</span><span className="mono" style={{ fontSize: 10 }}>add pt</span>
                <span className="tag dim">DRAG</span><span className="mono" style={{ fontSize: 10 }}>orbit</span>
                <span className="tag dim">SCROLL</span><span className="mono" style={{ fontSize: 10 }}>zoom</span>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="MACHINING PARAMETERS">
          <div className="tag dim">TOOL</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4, marginBottom: 6 }}>
            {TOOL_LIBRARY.map(t => (
              <button key={t.id} className={"chip" + (toolId === t.id ? " on" : "")} onClick={() => setToolId(t.id)}>{t.name}</button>
            ))}
          </div>
          <div className="form-row" style={{ flexDirection: "row", gap: 10, marginBottom: 8 }}>
            <span className="tag dim">TYPE</span>
            <span className="mono" style={{ fontSize: 10, color: "var(--info)" }}>{tool ? tool.type : "—"}</span>
            <span className="tag dim">TCP·LEN</span>
            <span className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>
              {tool ? (Math.hypot(tool.tcpOffset[0], tool.tcpOffset[1], tool.tcpOffset[2]) * 1000).toFixed(0) : 0} mm
            </span>
          </div>

          <hr className="hr" />
          <div className="tag dim">PART DIMENSIONS · {part.kind}</div>
          {Object.keys(part.dims).map(k => (
            <div key={k} className="cam-slider">
              <div className="cam-slider-h"><span className="tag dim">{k.toUpperCase()}</span>
                <span className="mono" style={{ color: "var(--ok)" }}>{(part.dims[k] * 1000).toFixed(0)} mm</span></div>
              <input type="range" className="slider" min="0.02" max="0.6" step="0.005"
                value={part.dims[k]} onChange={e => setDim(k, +e.target.value)} />
            </div>
          ))}
          <div className="cam-slider">
            <div className="cam-slider-h"><span className="tag dim">POS·X</span>
              <span className="mono" style={{ color: "var(--ok)" }}>{part.pose.pos[0].toFixed(2)} m</span></div>
            <input type="range" className="slider" min="0.2" max="0.8" step="0.01"
              value={part.pose.pos[0]} onChange={e => setPosX(+e.target.value)} />
          </div>
          <div className="cam-slider">
            <div className="cam-slider-h"><span className="tag dim">POS·Z</span>
              <span className="mono" style={{ color: "var(--ok)" }}>{part.pose.pos[2].toFixed(2)} m</span></div>
            <input type="range" className="slider" min="-0.4" max="0.4" step="0.01"
              value={part.pose.pos[2]} onChange={e => setPosZ(+e.target.value)} />
          </div>

          <hr className="hr" />
          <div className="tag dim">PICK MODE</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
            {(["POINT","POLY","CONTOUR"] as const).map(k => (
              <button key={k} className={"chip" + (mode === k ? " on" : "")} onClick={() => setMode(k)}>{k}</button>
            ))}
          </div>

          {([["standoff","TOOL STANDOFF","mm",0,50,standoff,setStandoff],
             ["approach","APPROACH / RETREAT","mm",10,200,approach,setApproach],
             ["vel","TCP SPEED","%",5,100,vel,setVel],
             ["acc","ACCELERATION","%",5,100,acc,setAcc]] as const).map(([k, lbl, u, mn, mx, v, fn]) => (
            <div key={k} className="cam-slider">
              <div className="cam-slider-h"><span className="tag dim">{lbl}</span>
                <span className="mono" style={{ color: "var(--ok)" }}>{v} {u}</span></div>
              <input type="range" className="slider" min={mn} max={mx} value={v} onChange={e => (fn as (n: number) => void)(+e.target.value)} />
            </div>
          ))}

          <div className="tag dim" style={{ marginTop: 8 }}>TOOL ORIENTATION</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
            {(["NORMAL","FIXED_Z","TANGENT"] as const).map(k => (
              <button key={k} className={"chip" + (orient === k ? " on" : "")} onClick={() => setOrient(k)}>{k.replace("_"," ")}</button>
            ))}
          </div>

          <hr className="hr" />
          <div className="tag dim">WELD WEAVE</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4, marginBottom: 4 }}>
            {(["NONE","ZIGZAG","SINE","TRIANGLE","TRAPEZOID"] as const).map(w => (
              <button key={w} className={"chip" + (weaveType === w ? " on" : "")} onClick={() => setWeaveType(w)}>{w}</button>
            ))}
          </div>
          {weaveType !== "NONE" && (
            <>
              <div className="cam-slider"><div className="cam-slider-h"><span className="tag dim">AMPLITUDE</span><span className="mono" style={{ color: "var(--ok)" }}>{weaveAmp} mm</span></div>
                <input type="range" className="slider" min="1" max="20" value={weaveAmp} onChange={e => setWeaveAmp(+e.target.value)} /></div>
              <div className="cam-slider"><div className="cam-slider-h"><span className="tag dim">WAVELENGTH</span><span className="mono" style={{ color: "var(--ok)" }}>{weaveWl} mm</span></div>
                <input type="range" className="slider" min="4" max="40" value={weaveWl} onChange={e => setWeaveWl(+e.target.value)} /></div>
              <div className="cam-slider"><div className="cam-slider-h"><span className="tag dim">EDGE DWELL</span><span className="mono" style={{ color: "var(--ok)" }}>{weaveDwell.toFixed(2)} s</span></div>
                <input type="range" className="slider" min="0" max="0.5" step="0.01" value={weaveDwell} onChange={e => setWeaveDwell(+e.target.value)} /></div>
            </>
          )}

          <hr className="hr" />
          <div className="tag dim">QUICK GENERATE</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
            <button className="btn" onClick={generateContour}>▢ CONTOUR</button>
            <button className="btn" onClick={generateRaster}>≡ RASTER</button>
            <button className="btn" onClick={generateSeam}>― SEAM</button>
          </div>
        </Panel>

        <Panel title={`PICKED POINTS · ${picks.length}`} pad={false}
          right={
            <div style={{ display: "flex", gap: 4 }}>
              <button className="chip" onClick={() => setPicks(p => p.slice(0, -1))} disabled={!picks.length}>UNDO</button>
              <button className="chip" onClick={() => setPicks(p => [...p].reverse())} disabled={picks.length < 2}>REV</button>
              <button className="chip" onClick={() => setPicks([])} disabled={!picks.length}>CLEAR</button>
            </div>
          }>
          <div className="picklist">
            {picks.length === 0 && (
              <div style={{ padding: 16, textAlign: "center", color: "var(--dim)" }}>
                <div className="mono" style={{ fontSize: 11 }}>CLICK THE WORKPIECE</div>
                <div className="tag dim" style={{ marginTop: 4 }}>or generate a pattern</div>
              </div>
            )}
            {picks.map((p, i) => (
              <div key={i} className="pickrow">
                <span className="mono pickrow-n">{String(i + 1).padStart(2, "0")}</span>
                <div className="pickrow-body">
                  <div className="mono" style={{ fontSize: 10 }}>
                    <span style={{ color: "var(--err)" }}>X {p.point[0].toFixed(3)}</span>{"  "}
                    <span style={{ color: "var(--ok)" }}>Y {p.point[1].toFixed(3)}</span>{"  "}
                    <span style={{ color: "var(--info)" }}>Z {p.point[2].toFixed(3)}</span>
                  </div>
                  <div className="mono" style={{ fontSize: 9, color: "var(--fg-mute)" }}>
                    N ({p.normal.map(v => v.toFixed(2)).join(", ")})
                  </div>
                </div>
                <button className="chip danger-chip" onClick={() => setPicks(ps => ps.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="AUTO-GENERATED TRAJECTORY"
          right={traj && <button className="btn primary" onClick={() => openInPath(traj)}>OPEN IN PATH EDITOR ›</button>}>
          {!traj ? (
            <div style={{ padding: 12, color: "var(--dim)" }} className="mono">
              Click points on the surface to auto-generate a robot trajectory.
            </div>
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
                <Stat label="WAYPOINTS" value={traj.waypoints.length} color="var(--ok)" />
                <Stat label="CYCLE TIME" value={`${traj.totalTime.toFixed(2)}s`} />
                <Stat label="PATH LEN" value={`${traj.pathLength.toFixed(3)}m`} />
                <Stat label="MAX TCP·v" value={`${traj.maxTCPSpeed.toFixed(2)}m/s`} />
              </div>
              <hr className="hr" />
              <div className="tag dim">GENERATED SEQUENCE</div>
              <div className="auto-seq">
                {traj.waypoints.map((w, i) => (
                  <div key={i} className="auto-wp">
                    <span className="mono" style={{ fontSize: 9, color: "var(--ok)" }}>{String(i+1).padStart(2,"0")}</span>
                    <span className={"wp-type " + (w.type === "MoveL" ? "lin" : "joint")}>{w.type}</span>
                    <span className="mono" style={{ fontSize: 10, color: "var(--fg)" }}>{w.name}</span>
                    <span className="mono" style={{ fontSize: 9, color: "var(--dim)" }}>v{w.vel} a{w.acc}{w.blend ? ` r${w.blend}` : ""}</span>
                    {w.io && <span className="mono" style={{ fontSize: 9, color: "var(--magenta)" }}>↪ {w.io.label}</span>}
                    <span className="mono" style={{ fontSize: 9, color: "var(--ok)", marginLeft: "auto" }}>{w.t.toFixed(2)}s</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Panel>
      </div>
      {void robot}
    </div>
  );
}
