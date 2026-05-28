// Weld weave presets. `applyWeave` densifies a polyline of picks ({point,
// normal}) into an oscillating path by offsetting each sample along the in-
// surface binormal (B = T × N). The output feeds straight into
// generateCAMTrajectory, so the weave appears in the FK path + velocity chart
// automatically.

import { Vector3 } from "three";
import type { Pick, Weave, WeaveType, Vec3 } from "@/types";

// Lateral profile in [-1,1] for a continuous arc-length phase (in cycles).
// All presets start at 0 on the seam centerline.
export function weaveProfile(type: WeaveType, phase: number): number {
  const f = phase - Math.floor(phase);
  if (type === "SINE") return Math.sin(phase * 2 * Math.PI);
  let tri: number;
  if (f < 0.25) tri = 4 * f;
  else if (f < 0.75) tri = 1 - 4 * (f - 0.25);
  else tri = -1 + 4 * (f - 0.75);
  if (type === "TRAPEZOID") return Math.max(-1, Math.min(1, tri * 1.8));
  return tri;
}

export function applyWeave(picks: Pick[], weave: Weave | null | undefined): Pick[] {
  if (!weave || weave.type === "NONE" || !picks || picks.length < 2) return picks;
  const amp = weave.amplitude;
  const wl = Math.max(0.002, weave.wavelength);
  const up = new Vector3(0, 1, 0);
  const out: Pick[] = [];
  let sAccum = 0;
  for (let i = 0; i < picks.length - 1; i++) {
    const a = picks[i], b = picks[i + 1];
    const A = new Vector3(a.point[0], a.point[1], a.point[2]);
    const B = new Vector3(b.point[0], b.point[1], b.point[2]);
    const seg = new Vector3().subVectors(B, A);
    const segLen = seg.length();
    if (segLen < 1e-6) continue;
    const T = seg.clone().normalize();
    const N = new Vector3(a.normal[0], a.normal[1], a.normal[2]).normalize();
    let Bn = new Vector3().crossVectors(T, N);
    if (Bn.lengthSq() < 1e-9) Bn = new Vector3().crossVectors(T, up);
    Bn.normalize();
    const steps = Math.max(2, Math.ceil(segLen / (wl / 8)));
    for (let k = 0; k <= steps; k++) {
      if (i > 0 && k === 0) continue;
      const fseg = k / steps;
      const phase = (sAccum + fseg * segLen) / wl;
      const prof = weaveProfile(weave.type, phase);
      const P = A.clone().addScaledVector(seg, fseg).addScaledVector(Bn, amp * prof);
      const point: Vec3 = [P.x, P.y, P.z];
      const pick: Pick = { point, normal: a.normal.slice() as Vec3 };
      if (weave.edgeDwell > 0 && Math.abs(prof) > 0.985) pick.dwell = weave.edgeDwell;
      out.push(pick);
    }
    sAccum += segLen;
  }
  return out;
}
