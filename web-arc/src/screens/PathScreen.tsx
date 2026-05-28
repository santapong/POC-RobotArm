// PATH screen: trajectory playback (3D arm follows the green path), waypoint
// list, velocity profile chart, selected-waypoint editor. Reads
// useUiStore.pendingTrajectory (handed off by CAM / PROGRAM); falls back to
// the example trajectory if no handoff is pending.

import { useEffect, useMemo, useRef, useState } from "react";
import type { Robot, Trajectory, Vec3 } from "@/types";
import { buildPathSamples, buildVelocityProfile, interpolateAtTime } from "@/lib/trajectory";
import { Arm3D } from "@/components/three/Arm3D";
import { Panel, Stat } from "@/components/common";
import { useUiStore } from "@/store/useUiStore";

export interface PathScreenProps { robot: Robot | undefined; }

const EXAMPLE: Trajectory = {
  id: "TRAJ-0142", name: "PICK-PLACE · BIN-A7 → KITTING-3", author: "OP·KOSTA",
  tool: "GRIPPER-2F", payload: 1.8,
  totalTime: 4.82, pathLength: 1.842, maxTCPSpeed: 0.84,
  maxJointVel: 142.6, maxJointAcc: 580,
  singularityWarnings: 0, collisionWarnings: 0, reachWarnings: 0,
  waypoints: [
    { id: 1, name: "HOME",          type: "MoveJ", tcp: [0, 0.9, 0],          rot: [180, 0, 0], joints: [0, -90, 0, 0, 90, 0],            vel: 60, acc: 50, blend: 0,  dwell: 0,    io: null,                                                       t: 0 },
    { id: 2, name: "APPROACH·PICK", type: "MoveJ", tcp: [0.42, 0.45, -0.18],  rot: [180, 0, 0], joints: [-22.4, -68.2, 84.1, 0, 74.1, -22.4], vel: 80, acc: 60, blend: 20, dwell: 0,    io: null,                                                       t: 0.95 },
    { id: 3, name: "PICK·DESCEND",  type: "MoveL", tcp: [0.42, 0.18, -0.18],  rot: [180, 0, 0], joints: [-22.4, -42.1, 58.3, 0, 73.8, -22.4], vel: 30, acc: 40, blend: 0,  dwell: 0.20, io: { type: "DO", ch: 0, value: true,  label: "GRIPPER CLOSE" }, t: 1.85 },
    { id: 4, name: "PICK·LIFT",     type: "MoveL", tcp: [0.42, 0.45, -0.18],  rot: [180, 0, 0], joints: [-22.4, -68.2, 84.1, 0, 74.1, -22.4], vel: 40, acc: 50, blend: 10, dwell: 0,    io: null,                                                       t: 2.42 },
    { id: 5, name: "TRANSIT",       type: "MoveJ", tcp: [0.14, 0.5, 0.08],    rot: [180, 0, 0], joints: [29.8, -75.4, 78.2, 0, 84, 29.8],     vel: 100, acc: 80, blend: 30, dwell: 0,    io: null,                                                       t: 2.96 },
    { id: 6, name: "APPROACH·PLACE",type: "MoveJ", tcp: [-0.32, 0.45, 0.24],  rot: [180, 0, 0], joints: [143.2, -68.2, 84.1, 0, 74.1, 143.2], vel: 80, acc: 60, blend: 20, dwell: 0,    io: null,                                                       t: 3.62 },
    { id: 7, name: "PLACE·DESCEND", type: "MoveL", tcp: [-0.32, 0.205, 0.24], rot: [180, 0, 0], joints: [143.2, -44.5, 60.1, 0, 74.1, 143.2], vel: 30, acc: 40, blend: 0,  dwell: 0.15, io: { type: "DO", ch: 0, value: false, label: "GRIPPER OPEN" },  t: 4.18 },
    { id: 8, name: "PLACE·RETREAT", type: "MoveL", tcp: [-0.32, 0.5, 0.24],   rot: [180, 0, 0], joints: [143.2, -72.1, 86.4, 0, 74.1, 143.2], vel: 40, acc: 50, blend: 10, dwell: 0,    io: null,                                                       t: 4.62 },
    { id: 9, name: "HOME",          type: "MoveJ", tcp: [0, 0.9, 0],          rot: [180, 0, 0], joints: [0, -90, 0, 0, 90, 0],            vel: 60, acc: 50, blend: 0,  dwell: 0,    io: null,                                                       t: 4.82 },
  ],
};

export function PathScreen({ robot }: PathScreenProps) {
  const pending = useUiStore(s => s.pendingTrajectory);
  const traj = pending ?? EXAMPLE;

  const [playT, setPlayT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [selWp, setSelWp] = useState(0);

  const pathPoints = useMemo<Vec3[]>(() => buildPathSamples(traj.waypoints, 200), [traj]);
  const profile = useMemo(() => buildVelocityProfile(traj.waypoints, 200), [traj]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setPlayT(t => {
        const nt = t + dt * speed;
        if (nt >= traj.totalTime) { setPlaying(false); return traj.totalTime; }
        return nt;
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, traj]);

  const live = useMemo(() => interpolateAtTime(traj.waypoints, playT), [traj, playT]);
  const markerRef = useRef<Vec3>([0, 0, 0]);
  useEffect(() => { if (live) markerRef.current = live.tcp; }, [live]);
  useEffect(() => { if (playing && live) setSelWp(live.segment); }, [live, playing]);

  const sel = traj.waypoints[selWp];
  const jumpTo = (i: number) => { setSelWp(i); setPlayT(traj.waypoints[i].t); setPlaying(false); };

  return (
    <div className="screen path">
      <div className="path-grid">
        <Panel
          title={`▸ TRAJECTORY · ${traj.name}`}
          right={
            <span className="mono dim" style={{ fontSize: 10 }}>{traj.id} · {traj.author}</span>
          }
          pad={false}
          style={{ gridColumn: "1 / span 2", gridRow: "1" }}
        >
          <div className="path-3d">
            <Arm3D
              jointAngles={live ? live.joints : traj.waypoints[0].joints}
              pathPoints={pathPoints}
              waypoints={traj.waypoints}
              selectedWaypoint={selWp}
              reach={robot?.reach ?? 1.0}
              width="100%"
              height="100%"
            />
            <div className="cam-hud-tl">
              <div className="mono" style={{ color: "var(--ok)" }}>● PATH · 200 SAMPLES</div>
              <div className="mono dim" style={{ fontSize: 9 }}>{traj.waypoints.length} WAYPOINTS</div>
            </div>
            <div className="cam-hud-tr mono dim">drag · orbit  ·  scroll · zoom  ·  right · pan</div>
            <div className="play-bar">
              <button className="play-btn" onClick={() => setPlaying(p => !p)}>{playing ? "❚❚" : "▶"}</button>
              <button className="play-btn small" onClick={() => { setPlayT(0); setPlaying(false); }}>⏮</button>
              <button className="play-btn small" onClick={() => { setPlayT(traj.totalTime); setPlaying(false); }}>⏭</button>
              <div className="play-time mono">{playT.toFixed(2)} / {traj.totalTime.toFixed(2)}s</div>
              <input className="play-scrub" type="range" min={0} max={traj.totalTime} step={0.01}
                value={playT} onChange={e => { setPlayT(+e.target.value); setPlaying(false); }} />
              <div style={{ display: "flex", gap: 2 }}>
                {[0.25, 0.5, 1, 2].map(s => (
                  <button key={s} className={"chip" + (speed === s ? " on" : "")} onClick={() => setSpeed(s)}>{s}×</button>
                ))}
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="WAYPOINTS" pad={false} style={{ gridColumn: "3", gridRow: "1 / span 2" }}>
          <div className="wplist">
            {traj.waypoints.map((wp, i) => {
              const isSel = i === selWp;
              const isCur = live && live.segment === i;
              return (
                <button
                  key={wp.id}
                  className={"wprow" + (isSel ? " sel" : "") + (isCur ? " cur" : "")}
                  onClick={() => jumpTo(i)}
                >
                  <div className="wprow-num">
                    <span className="mono">{String(i + 1).padStart(2, "0")}</span>
                    <span className={"wp-type " + (wp.type === "MoveL" ? "lin" : "joint")}>{wp.type}</span>
                  </div>
                  <div>
                    <div className="mono wprow-name">{wp.name}</div>
                    <div className="wprow-meta mono">
                      <span>X {wp.tcp[0].toFixed(3)}</span>
                      <span>Y {wp.tcp[1].toFixed(3)}</span>
                      <span>Z {wp.tcp[2].toFixed(3)}</span>
                    </div>
                    {wp.io && (
                      <div className="wprow-io mono" style={{ color: "var(--magenta)" }}>{wp.io.label}</div>
                    )}
                  </div>
                  <div className="wprow-t mono">{wp.t.toFixed(2)}s</div>
                </button>
              );
            })}
          </div>
        </Panel>

        <Panel title="MOTION PROFILE · TCP"
          right={
            <div style={{ display: "flex", gap: 10, fontSize: 10 }}>
              <span className="mono" style={{ color: "var(--ok)" }}>—— VEL</span>
              <span className="mono" style={{ color: "var(--warn)" }}>- - ACC</span>
            </div>
          }
          style={{ gridColumn: "1 / span 2", gridRow: "2" }}
        >
          <VelocityChart profile={profile} waypoints={traj.waypoints} playT={playT} totalT={traj.totalTime}
            onScrub={(t) => { setPlayT(t); setPlaying(false); }} />
        </Panel>

        <Panel title={`▸ WP-${String(selWp + 1).padStart(2, "0")} · ${sel.name}`}
          style={{ gridColumn: "1 / span 2", gridRow: "3" }}>
          <div className="wp-edit-grid">
            <div className="wp-edit-col">
              <div className="form-row"><span className="tag dim">NAME</span>
                <input className="inp" defaultValue={sel.name} /></div>
              <div className="form-row"><span className="tag dim">TIME</span>
                <input className="inp" defaultValue={`${sel.t.toFixed(2)}s`} /></div>
              <div className="form-row"><span className="tag dim">DWELL</span>
                <input className="inp" defaultValue={`${sel.dwell}s`} /></div>
            </div>
            <div className="wp-edit-col">
              <div className="tag dim">TCP POSE · base_link</div>
              <div className="wp-tcp">
                {(["X", "Y", "Z"] as const).map((axis, i) => (
                  <div key={axis} className="wp-tcp-row">
                    <span className="tag" style={{ width: 16 }}>{axis}</span>
                    <input className="inp mono" defaultValue={sel.tcp[i].toFixed(3)} />
                    <span className="tag dim">m</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="wp-edit-col">
              <div className="tag dim">JOINTS · J1-J6</div>
              <div className="wp-joints">
                {sel.joints.map((j, i) => (
                  <div key={i} className="wp-joint-row">
                    <span className="mono" style={{ fontSize: 9, color: "var(--ok)", width: 22 }}>J{i + 1}</span>
                    <input className="inp mono" defaultValue={j.toFixed(2)} style={{ width: 70 }} />
                    <span className="tag dim">°</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="wp-edit-col">
              <Stat label="VEL" value={`${sel.vel}%`} />
              <Stat label="ACC" value={`${sel.acc}%`} />
              <Stat label="BLEND r" value={`${sel.blend}mm`} />
            </div>
          </div>
        </Panel>

        <Panel title="METRICS · ANALYSIS" style={{ gridColumn: "3", gridRow: "3" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <Stat label="CYCLE TIME" value={`${traj.totalTime.toFixed(2)}s`} color="var(--ok)" />
            <Stat label="PATH LEN" value={`${traj.pathLength.toFixed(2)}m`} />
            <Stat label="MAX TCP·v" value={`${traj.maxTCPSpeed.toFixed(2)} m/s`} />
            <Stat label="MAX J·vel" value={`${traj.maxJointVel.toFixed(0)} °/s`} />
            <Stat label="MAX J·acc" value={`${traj.maxJointAcc.toFixed(0)} °/s²`} />
            <Stat label="WAYPOINTS" value={traj.waypoints.length} />
          </div>
        </Panel>
      </div>
    </div>
  );
}

// Compact velocity profile chart (TCP speed + acceleration, with waypoint
// markers and a scrubbable playback head).
interface VelocityChartProps {
  profile: { vel: number[]; acc: number[]; totalT: number; dt: number };
  waypoints: Trajectory["waypoints"];
  playT: number;
  totalT: number;
  onScrub: (t: number) => void;
}

function VelocityChart({ profile, waypoints, playT, totalT, onScrub }: VelocityChartProps) {
  const w = 800, H = 160, pad = 24;
  if (!profile.vel.length) return <div style={{ height: H }} />;
  const maxVel = Math.max(0.001, ...profile.vel);
  const maxAcc = Math.max(0.001, ...profile.acc);
  const velPath = profile.vel.map((v, i) => {
    const x = pad + (i / (profile.vel.length - 1)) * (w - pad * 2);
    const y = H - 18 - (v / maxVel) * (H - 36);
    return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  const accPath = profile.acc.map((v, i) => {
    const x = pad + (i / (profile.acc.length - 1)) * (w - pad * 2);
    const y = H - 18 - (v / maxAcc) * (H - 36);
    return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  const playX = pad + (playT / totalT) * (w - pad * 2);
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${w} ${H}`} preserveAspectRatio="none" style={{ cursor: "crosshair" }}
      onClick={(e) => {
        const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
        const xPx = e.clientX - rect.left;
        const px = (xPx / rect.width) * w;
        const t = Math.max(0, Math.min(totalT, ((px - pad) / (w - pad * 2)) * totalT));
        onScrub(t);
      }}
    >
      {[0.25, 0.5, 0.75].map(p => (
        <line key={p} x1={pad} y1={(H - 18) - p * (H - 36)} x2={w - pad} y2={(H - 18) - p * (H - 36)} stroke="rgba(120,180,200,.08)" strokeDasharray="2 3" />
      ))}
      <line x1={pad} y1={H - 18} x2={w - pad} y2={H - 18} stroke="rgba(120,180,200,.25)" />
      {waypoints.map((wp, i) => {
        const x = pad + (wp.t / totalT) * (w - pad * 2);
        return <line key={i} x1={x} y1={6} x2={x} y2={H - 18} stroke="rgba(232,121,249,.25)" strokeDasharray="2 2" />;
      })}
      <path d={velPath} fill="none" stroke="#4ade80" strokeWidth="1.5" />
      <path d={accPath} fill="none" stroke="#fbbf24" strokeWidth="1.2" strokeDasharray="3 2" opacity="0.85" />
      <line x1={playX} y1={6} x2={playX} y2={H - 6} stroke="#fbbf24" strokeWidth="1.5" />
      <polygon points={`${playX - 4},6 ${playX + 4},6 ${playX},12`} fill="#fbbf24" />
    </svg>
  );
}
