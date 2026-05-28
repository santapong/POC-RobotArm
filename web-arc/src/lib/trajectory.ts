// Trajectory interpolation + FK-sampled path and velocity helpers. By sampling
// the path via armTCP(joints) we guarantee the drawn green path is the tool's
// REAL world path (not the stored TCP data) — the fix that makes the gripper
// follow the line.

import type { Vec3, Waypoint } from "@/types";
import { armTCP } from "./three/fk";

export interface InterpolatedState {
  joints: number[];
  tcp: Vec3;
  segment: number;
}

export function interpolateAtTime(waypoints: Waypoint[], t: number): InterpolatedState | null {
  if (!waypoints || waypoints.length === 0) return null;
  if (t <= waypoints[0].t) return { joints: waypoints[0].joints.slice(), tcp: waypoints[0].tcp.slice() as Vec3, segment: 0 };
  const last = waypoints[waypoints.length - 1];
  if (t >= last.t) return { joints: last.joints.slice(), tcp: last.tcp.slice() as Vec3, segment: waypoints.length - 1 };
  for (let i = 0; i < waypoints.length - 1; i++) {
    const a = waypoints[i], b = waypoints[i + 1];
    if (t >= a.t && t <= b.t) {
      const f = (t - a.t) / Math.max(0.001, b.t - a.t);
      const ef = f * f * (3 - 2 * f); // smoothstep
      return {
        joints: a.joints.map((v, k) => v + (b.joints[k] - v) * ef),
        tcp: [
          a.tcp[0] + (b.tcp[0] - a.tcp[0]) * ef,
          a.tcp[1] + (b.tcp[1] - a.tcp[1]) * ef,
          a.tcp[2] + (b.tcp[2] - a.tcp[2]) * ef,
        ],
        segment: i,
      };
    }
  }
  return { joints: waypoints[0].joints.slice(), tcp: waypoints[0].tcp.slice() as Vec3, segment: 0 };
}

// Sample the FK tool path along the trajectory — i.e., where the gripper
// actually goes for the active tool — so the path on screen matches the arm.
export function buildPathSamples(waypoints: Waypoint[], samples = 240): Vec3[] {
  if (!waypoints || waypoints.length < 2) return [];
  const total = waypoints[waypoints.length - 1].t;
  const pts: Vec3[] = [];
  for (let i = 0; i < samples; i++) {
    const t = (i / (samples - 1)) * total;
    const s = interpolateAtTime(waypoints, t);
    if (!s) continue;
    pts.push(armTCP(s.joints));
  }
  return pts;
}

export interface VelocityProfile {
  vel: number[];
  acc: number[];
  totalT: number;
  dt: number;
}

export function buildVelocityProfile(waypoints: Waypoint[], samples = 240): VelocityProfile {
  if (!waypoints || waypoints.length < 2) return { vel: [], acc: [], totalT: 0, dt: 0 };
  const total = waypoints[waypoints.length - 1].t;
  const dt = total / (samples - 1);
  const positions: Vec3[] = [];
  for (let i = 0; i < samples; i++) {
    const s = interpolateAtTime(waypoints, i * dt);
    if (!s) continue;
    positions.push(armTCP(s.joints));
  }
  const vel: number[] = [], acc: number[] = [];
  for (let i = 0; i < positions.length; i++) {
    const im = Math.max(0, i - 1), ip = Math.min(positions.length - 1, i + 1);
    const dx = positions[ip][0] - positions[im][0];
    const dy = positions[ip][1] - positions[im][1];
    const dz = positions[ip][2] - positions[im][2];
    vel.push(Math.sqrt(dx * dx + dy * dy + dz * dz) / ((ip - im) * dt));
  }
  for (let i = 0; i < vel.length; i++) {
    const im = Math.max(0, i - 1), ip = Math.min(vel.length - 1, i + 1);
    acc.push(Math.abs((vel[ip] - vel[im]) / ((ip - im) * dt)));
  }
  return { vel, acc, totalT: total, dt };
}
