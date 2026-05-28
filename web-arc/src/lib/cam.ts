// CAM-style surface-pick path generation. Click points + normals →
// HOME → APPROACH → per-point passes (with IO triggers and optional weave) →
// RETREAT → HOME. The IK is approximate (2-link planar for J2/J3, wrist along
// the surface normal) — calibrated for the active tool's TCP length so longer
// tools reach less far.

import type { CamOptions, Pick, Trajectory, Vec3, Waypoint } from "@/types";
import { applyWeave } from "./three/weave";
import { getActiveTool } from "./three/fk";

export function approxIK(target: Vec3, normal: Vec3 = [0, 1, 0], tcpLen: number | null = null): number[] {
  const [x, y, z] = target;
  const upperArm = 0.42;
  const forearm  = 0.34;
  const baseY    = 0.26;

  const j1 = Math.atan2(-z, x);
  const r  = Math.sqrt(x * x + z * z);
  const h  = y - baseY;

  if (tcpLen == null) {
    const t = getActiveTool()?.tcpOffset;
    tcpLen = t ? Math.hypot(t[0], t[1], t[2]) : 0.13;
  }
  const wristOffset = 0.10 + tcpLen;
  const rTarg = Math.max(0.1, r - wristOffset * Math.abs(normal[0] || 0));
  const hTarg = h + wristOffset * Math.abs(normal[1] || 1);

  const d = Math.sqrt(rTarg * rTarg + hTarg * hTarg);
  const D = Math.max(0.05, Math.min(upperArm + forearm - 0.02, d));

  const cosE = (upperArm * upperArm + forearm * forearm - D * D) / (2 * upperArm * forearm);
  const elbow = Math.acos(Math.max(-1, Math.min(1, cosE)));
  const j3 = Math.PI - elbow;

  const ang = Math.atan2(hTarg, rTarg);
  const cosS = (upperArm * upperArm + D * D - forearm * forearm) / (2 * upperArm * D);
  const shoff = Math.acos(Math.max(-1, Math.min(1, cosS)));
  const j2 = -(ang + shoff);

  const j5 = 90 - Math.atan2(normal[1], Math.sqrt(normal[0] * normal[0] + normal[2] * normal[2])) * 180 / Math.PI;

  return [
    j1 * 180 / Math.PI,
    j2 * 180 / Math.PI,
    j3 * 180 / Math.PI,
    0,
    j5,
    0,
  ];
}

export function rotFromNormal(n: Vec3): Vec3 {
  const rx = 180 - Math.acos(Math.max(-1, Math.min(1, n[1]))) * 180 / Math.PI;
  const rz = Math.atan2(n[0], n[2]) * 180 / Math.PI;
  return [rx, 0, rz];
}

export function generateCAMTrajectory(picks: Pick[], opts: CamOptions = {}): Trajectory | null {
  if (!picks || picks.length === 0) return null;
  const standoff = opts.standoff ?? 0.005;
  const approachHeight = opts.approachHeight ?? 0.06;
  const vel = opts.vel ?? 30;
  const acc = opts.acc ?? 40;
  const home: Vec3 = opts.home ?? [0, 0.9, 0];
  const moveType = opts.moveType ?? "MoveL";
  const tool = opts.tool ?? null;
  const weave = opts.weave ?? null;
  const tcpLen = tool?.tcpOffset ? Math.hypot(tool.tcpOffset[0], tool.tcpOffset[1], tool.tcpOffset[2]) : null;
  const wpicks = (weave && weave.type !== "NONE") ? applyWeave(picks, weave) : picks;

  const wps: Waypoint[] = [];
  let t = 0;

  wps.push({
    id: 1, name: "HOME", type: "MoveJ",
    tcp: home.slice() as Vec3,
    rot: [180, 0, 0],
    joints: [0, -90, 0, 0, 90, 0],
    vel: 60, acc: 50, blend: 0, dwell: 0, io: null, t,
  });
  t += 0.6;

  const first = wpicks[0];
  const firstAprPos: Vec3 = [
    first.point[0] + first.normal[0] * approachHeight,
    first.point[1] + first.normal[1] * approachHeight,
    first.point[2] + first.normal[2] * approachHeight,
  ];
  wps.push({
    id: wps.length + 1, name: "APPROACH", type: "MoveJ",
    tcp: firstAprPos, rot: rotFromNormal(first.normal),
    joints: approxIK(firstAprPos, first.normal, tcpLen),
    vel: 70, acc: 60, blend: 10, dwell: 0, io: null, t,
  });
  t += 0.7;

  const dense = wpicks.length > 12;
  wpicks.forEach((p, i) => {
    const tcp: Vec3 = [
      p.point[0] + p.normal[0] * standoff,
      p.point[1] + p.normal[1] * standoff,
      p.point[2] + p.normal[2] * standoff,
    ];
    const isFirst = i === 0;
    const dur = isFirst ? 0.4 : (dense ? 0.12 : 0.6);
    wps.push({
      id: wps.length + 1,
      name: `PT-${String(i + 1).padStart(2, "0")}`,
      type: isFirst ? "MoveL" : moveType,
      tcp,
      rot: rotFromNormal(p.normal),
      joints: approxIK(tcp, p.normal, tcpLen),
      vel, acc,
      blend: i === wpicks.length - 1 ? 0 : 5,
      dwell: isFirst ? 0.1 : (p.dwell ?? 0),
      io: isFirst ? { type: "DO", ch: 0, value: true, label: "TOOL ON" } : null,
      t: t + dur,
    });
    t += dur;
  });

  const last = wpicks[wpicks.length - 1];
  const retreatPos: Vec3 = [
    last.point[0] + last.normal[0] * approachHeight,
    last.point[1] + last.normal[1] * approachHeight,
    last.point[2] + last.normal[2] * approachHeight,
  ];
  wps.push({
    id: wps.length + 1, name: "RETREAT", type: "MoveL",
    tcp: retreatPos, rot: rotFromNormal(last.normal),
    joints: approxIK(retreatPos, last.normal, tcpLen),
    vel: 50, acc: 50, blend: 10, dwell: 0,
    io: { type: "DO", ch: 0, value: false, label: "TOOL OFF" },
    t: t + 0.5,
  });
  t += 0.5;

  wps.push({
    id: wps.length + 1, name: "HOME", type: "MoveJ",
    tcp: home.slice() as Vec3,
    rot: [180, 0, 0],
    joints: [0, -90, 0, 0, 90, 0],
    vel: 60, acc: 50, blend: 0, dwell: 0, io: null,
    t: t + 0.7,
  });

  let pathLength = 0;
  for (let i = 1; i < wps.length; i++) {
    const a = wps[i - 1].tcp, b = wps[i].tcp;
    pathLength += Math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2);
  }

  return {
    id: "CAM-AUTO",
    name: `CAM AUTO · ${picks.length} PT${picks.length > 1 ? "S" : ""}`,
    author: "AUTO·CAM",
    tool: "TOOL-T7",
    payload: 0,
    waypoints: wps,
    totalTime: wps[wps.length - 1].t,
    pathLength,
    maxTCPSpeed: vel / 100 * 1.5,
    maxJointVel: 142,
    maxJointAcc: 540,
    singularityWarnings: 0,
    collisionWarnings: 0,
    reachWarnings: 0,
  };
}
