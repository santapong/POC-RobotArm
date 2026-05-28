// Parametric CAD parts (BOX / CYLINDER / PLATE / STEP). Returns a THREE.Group of
// clickable body meshes + yellow edge outlines, placed by part.pose. Generalizes
// the prototype's buildWorkpiece so any parametric part can be used in CAM /
// PROGRAM viewers.

import {
  BoxGeometry, CylinderGeometry, EdgesGeometry, Group, LineBasicMaterial,
  LineSegments, Mesh, MeshStandardMaterial, type BufferGeometry,
} from "three";
import type { Part } from "@/types";

export function buildPartMesh(part: Part | null): Group {
  const grp = new Group(); grp.name = "PART";
  if (!part) return grp;
  const matBody = new MeshStandardMaterial({ color: 0x9ca8b4, metalness: 0.6, roughness: 0.4 });
  const matEdge = new LineBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.85 });
  const d = part.dims || {};

  const addBody = (geo: BufferGeometry, oy: number) => {
    const m = new Mesh(geo, matBody); m.position.y = oy; m.userData.clickable = true; grp.add(m);
    const e = new LineSegments(new EdgesGeometry(geo), matEdge); e.position.y = oy; grp.add(e);
  };

  const kind = part.kind || "BOX";
  if (kind === "CYLINDER") {
    const r = d.r ?? 0.14, h = d.h ?? 0.18;
    addBody(new CylinderGeometry(r, r, h, 36), h / 2);
  } else if (kind === "PLATE") {
    const w = d.w ?? 0.50, t = d.t ?? 0.02, dp = d.d ?? 0.35;
    addBody(new BoxGeometry(w, t, dp), t / 2);
  } else if (kind === "STEP") {
    const w = d.w ?? 0.40, h = d.h ?? 0.06, dp = d.d ?? 0.30;
    const tw = d.topW ?? 0.28, th = d.topH ?? 0.08, td = d.topD ?? 0.22;
    addBody(new BoxGeometry(w, h, dp), h / 2);
    addBody(new BoxGeometry(tw, th, td), h + th / 2);
  } else {
    const w = d.w ?? 0.40, h = d.h ?? 0.15, dp = d.d ?? 0.30;
    addBody(new BoxGeometry(w, h, dp), h / 2);
  }
  const p = part.pose?.pos ?? [0.5, 0, 0];
  const r = part.pose?.rpy ?? [0, 0, 0];
  grp.position.set(p[0], p[1], p[2]);
  grp.rotation.set(r[0] * Math.PI / 180, r[1] * Math.PI / 180, r[2] * Math.PI / 180);
  return grp;
}

// Top-face height of a part (used for CONTOUR / RASTER pattern generation).
export function partTopY(part: Part): number {
  const d = part.dims || {};
  const base = part.pose?.pos?.[1] ?? 0;
  const kind = part.kind || "BOX";
  if (kind === "CYLINDER") return base + (d.h ?? 0.18);
  if (kind === "PLATE")    return base + (d.t ?? 0.02);
  if (kind === "STEP")     return base + (d.h ?? 0.06) + (d.topH ?? 0.08);
  return base + (d.h ?? 0.15);
}

// In-surface XZ footprint of a part's top face (used by genPicks). Inset 4 cm
// from the edges so picks stay safely on the face.
export interface Footprint { x0: number; x1: number; z0: number; z1: number; y: number; }
export function partFootprint(part: Part): Footprint {
  const d = part.dims || {};
  const c = part.pose?.pos ?? [0.5, 0, 0];
  const y = partTopY(part);
  let wx: number, wz: number;
  if (part.kind === "CYLINDER") { wx = wz = d.r ?? 0.14; }
  else if (part.kind === "STEP") { wx = (d.topW ?? 0.28) / 2; wz = (d.topD ?? 0.22) / 2; }
  else { wx = (d.w ?? 0.40) / 2; wz = (d.d ?? 0.30) / 2; }
  const inset = 0.04;
  return { x0: c[0] - wx + inset, x1: c[0] + wx - inset, z0: c[2] - wz + inset, z1: c[2] + wz - inset, y };
}
