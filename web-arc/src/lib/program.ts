// Operation tree → one combined trajectory (the "post"). Each operation runs
// generateCAMTrajectory (after applying weave for weld ops); compileJob
// concatenates them with re-timed `t` and drops mid-program HOMEs only after
// waypoints have been emitted (so the program always starts with a HOME).

import type {
  Job, OpKind, Operation, Part, Pick, Strategy,
  Trajectory, Vec3, Waypoint,
} from "@/types";
import { findPart, findTcp, findTool, WEAVE_DEFAULT } from "./catalogs";
import { generateCAMTrajectory } from "./cam";
import { partFootprint } from "./three/part-mesh";

export const OP_KIND_COLOR: Record<OpKind, string> = {
  PICKPLACE: "var(--info)", WELD: "var(--warn)", MILL: "var(--magenta)", DISPENSE: "var(--ok)",
};
export const OP_DEFAULT_TOOL: Record<OpKind, string> = { PICKPLACE: "grip-2f", WELD: "mig", MILL: "spindle", DISPENSE: "disp" };
export const OP_DEFAULT_PART: Record<OpKind, string> = { PICKPLACE: "part-box", WELD: "part-plate", MILL: "part-box", DISPENSE: "part-plate" };

// XZ corner / raster / seam patterns on a part's top face.
export function genPicks(strategy: Strategy, part: Part | null): Pick[] {
  if (!part) return [];
  const { x0, x1, z0, z1, y } = partFootprint(part);
  const n: Vec3 = [0, 1, 0];
  if (strategy === "CONTOUR") return [
    { point: [x0, y, z0], normal: n }, { point: [x1, y, z0], normal: n },
    { point: [x1, y, z1], normal: n }, { point: [x0, y, z1], normal: n },
    { point: [x0, y, z0], normal: n },
  ];
  if (strategy === "RASTER") {
    const pts: Pick[] = []; const passes = 5;
    for (let i = 0; i < passes; i++) {
      const z = z0 + (z1 - z0) * (i / (passes - 1));
      if (i % 2 === 0) { pts.push({ point: [x0, y, z], normal: n }); pts.push({ point: [x1, y, z], normal: n }); }
      else { pts.push({ point: [x1, y, z], normal: n }); pts.push({ point: [x0, y, z], normal: n }); }
    }
    return pts;
  }
  if (strategy === "SEAM") {
    const z = (z0 + z1) / 2;
    return [{ point: [x0, y, z], normal: n }, { point: [x1, y, z], normal: n }];
  }
  return [{ point: [(x0 + x1) / 2, y, (z0 + z1) / 2], normal: n }];
}

export function makeOp(id: number, kind: OpKind): Operation {
  const partId = OP_DEFAULT_PART[kind];
  const toolId = OP_DEFAULT_TOOL[kind];
  return {
    id, name: `${kind} ${id}`, enabled: true, kind,
    partId, toolId, tcpId: "tcp-tip",
    strategy: kind === "WELD" ? "SEAM" : "POINTS",
    params: {
      standoff: 5, approach: 60, vel: 30, acc: 40,
      weave: kind === "WELD"
        ? { type: "SINE", amplitude: 0.004, wavelength: 0.012, edgeDwell: 0.05 }
        : { ...WEAVE_DEFAULT },
      picks: genPicks(kind === "WELD" ? "SEAM" : "POINTS", findPart(partId)),
    },
  };
}

export function opTrajectory(op: Operation): Trajectory | null {
  return generateCAMTrajectory(op.params.picks || [], {
    standoff: (op.params.standoff || 5) / 1000,
    approachHeight: (op.params.approach || 60) / 1000,
    vel: op.params.vel || 30,
    acc: op.params.acc || 40,
    tool: findTool(op.toolId),
    weave: op.kind === "WELD" ? op.params.weave : null,
  });
}

export function compileJob(job: Job): Trajectory {
  const all: Waypoint[] = [];
  let tOffset = 0, pathLength = 0, sing = 0, coll = 0, reach = 0, idc = 0;
  (job.ops || []).filter(o => o.enabled).forEach(op => {
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
    sing += t.singularityWarnings || 0;
    coll += t.collisionWarnings || 0;
    reach += t.reachWarnings || 0;
  });
  return {
    id: "JOB-" + (job.id || "0"), name: job.name || "PROGRAM", author: job.author || "OP",
    tool: "MULTI", payload: 0,
    waypoints: all, totalTime: all.length ? all[all.length - 1].t : 0,
    pathLength, maxTCPSpeed: 0.84, maxJointVel: 142, maxJointAcc: 540,
    singularityWarnings: sing, collisionWarnings: coll, reachWarnings: reach,
  };
}

// Render a compiled job as a URScript-flavored program text. Cosmetic — for
// the PROGRAM screen's post-output panel; not run on a real robot.
export function postProgram(compiled: Trajectory, job: Job): string {
  const tcp = findTcp(job.activeTcpId) ?? { offset: [0, 0, 0] as Vec3 };
  const lines: string[] = [];
  lines.push(`# ${job.name}  ·  ${job.author}`);
  lines.push(`# ${job.ops.filter(o => o.enabled).length} ops · ${compiled.waypoints.length} waypoints · ${compiled.totalTime.toFixed(2)}s · ${job.postFormat}`);
  lines.push(`set_tcp(p[${tcp.offset.map(v => v.toFixed(3)).join(", ")}])`);
  lines.push("");
  let cur: string | null = null;
  compiled.waypoints.forEach(wp => {
    if (wp.op !== cur) { cur = wp.op ?? null; lines.push(`# — ${cur} —`); }
    const m: "movel" | "movej" = wp.type === "MoveL" ? "movel" : "movej";
    lines.push(`${m}([${wp.joints.map(j => (j * Math.PI / 180).toFixed(3)).join(", ")}], a=${(wp.acc / 50).toFixed(2)}, v=${(wp.vel / 60).toFixed(2)}${wp.blend ? `, r=${(wp.blend / 1000).toFixed(3)}` : ""})`);
    if (wp.io) lines.push(`set_digital_out(${wp.io.ch}, ${wp.io.value ? "True" : "False"})`);
    if (wp.dwell) lines.push(`sleep(${wp.dwell})`);
  });
  lines.push("");
  lines.push("END");
  return lines.join("\n");
}

// The example job seeded into the document on first run. Marked Mutable so the
// store's deep clone is the user's editable copy; never mutate the original.
export const DEFAULT_JOB: Job = {
  id: "0142", name: "CELL-07 PROGRAM", author: "OP·KOSTA", activeTcpId: "tcp-tip", postFormat: "URScript",
  ops: [
    { id: 1, name: "PICK BLANK", enabled: true, kind: "PICKPLACE", partId: "part-box", toolId: "grip-2f", tcpId: "tcp-tip", strategy: "POINTS",
      params: { standoff: 5, approach: 60, vel: 40, acc: 50, weave: { ...WEAVE_DEFAULT }, picks: [{ point: [0.5, 0.15, 0], normal: [0, 1, 0] }] } },
    { id: 2, name: "WELD SEAM", enabled: true, kind: "WELD", partId: "part-plate", toolId: "mig", tcpId: "tcp-weld", strategy: "SEAM",
      params: { standoff: 2, approach: 50, vel: 25, acc: 40,
        weave: { type: "SINE", amplitude: 0.004, wavelength: 0.012, edgeDwell: 0.05 },
        picks: [{ point: [0.40, 0.02, 0], normal: [0, 1, 0] }, { point: [0.60, 0.02, 0], normal: [0, 1, 0] }] } },
  ],
};
