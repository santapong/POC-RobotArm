// arm-tooling.jsx — Robotmaster/RoboDK-style tooling: TCP frames, a tool
// library, parametric CAD parts, weave presets, and job compilation.
// Loaded AFTER arm-3d.jsx (uses buildToolMesh/armTCP) and BEFORE arm-cam.jsx /
// arm-program.jsx (which consume these catalogs + buildPartMesh).
//
// Phase 1 here: data catalogs + buildPartMesh + selection helpers.
// (applyWeave is added in Phase 2, compileJob in Phase 3.)

// ── TCP FRAMES ────────────────────────────────────────────────────────────
// A named tool-frame: flange -> TCP offset (m) + orientation (deg) + payload.
const TCP_LIBRARY = [
  { id: "tcp-flange", name: "FLANGE",   offset: [0, 0, 0],     rpy: [0, 0, 0], payload: { mass: 0,   com: [0, 0, 0] } },
  { id: "tcp-tip",    name: "TOOL TIP", offset: [0, 0.130, 0], rpy: [0, 0, 0], payload: { mass: 1.8, com: [0, 0, 0.05] } },
  { id: "tcp-weld",   name: "WELD TIP", offset: [0.027, 0.158, 0], rpy: [-35, 0, 0], payload: { mass: 2.4, com: [0, 0, 0.06] } },
];

// ── TOOL LIBRARY ──────────────────────────────────────────────────────────
// type drives buildToolMesh() geometry; tcpOffset (j6-local) drives the TCP
// group; lead = linear lead-in/out standoff (m) along the tool axis.
const TOOL_LIBRARY = [
  { id: "grip-2f", name: "GRIPPER-2F", type: "GRIPPER_2F", mount: { offset: [0, 0, 0], rpy: [0, 0, 0] },
    tcpOffset: [0, 0.130, 0], size: { stroke: 0.056, length: 0.06 }, lead: { in: 0.02, out: 0.02 } },
  { id: "grip-3f", name: "GRIPPER-3F", type: "GRIPPER_3F", mount: { offset: [0, 0, 0], rpy: [0, 0, 0] },
    tcpOffset: [0, 0.130, 0], size: { stroke: 0.050, length: 0.06 }, lead: { in: 0.02, out: 0.02 } },
  { id: "suction", name: "SUCTION",    type: "SUCTION",    mount: { offset: [0, 0, 0], rpy: [0, 0, 0] },
    tcpOffset: [0, 0.120, 0], size: { dia: 0.05 }, lead: { in: 0.03, out: 0.03 } },
  { id: "mig",     name: "WELDER-MIG", type: "MIG",        mount: { offset: [0, 0, 0], rpy: [0, 0, 0] },
    tcpOffset: [0.027, 0.158, 0], size: { length: 0.16 }, lead: { in: 0.015, out: 0.015 } },
  { id: "spindle", name: "SPINDLE-T7", type: "SPINDLE",    mount: { offset: [0, 0, 0], rpy: [0, 0, 0] },
    tcpOffset: [0, 0.201, 0], size: { length: 0.18, dia: 0.10 }, lead: { in: 0.02, out: 0.02 } },
  { id: "disp",    name: "DISPENSER",  type: "DISPENSER",  mount: { offset: [0, 0, 0], rpy: [0, 0, 0] },
    tcpOffset: [0, 0.149, 0], size: { length: 0.14 }, lead: { in: 0.01, out: 0.01 } },
];

// ── PART LIBRARY (parametric CAD primitives) ────────────────────────────────
// dims are per-kind; pose places the part base on the floor in front of the arm.
const PART_LIBRARY = [
  { id: "part-box",  name: "BLOCK",    kind: "BOX",      dims: { w: 0.40, h: 0.15, d: 0.30 }, pose: { pos: [0.50, 0, 0], rpy: [0, 0, 0] } },
  { id: "part-cyl",  name: "CYLINDER", kind: "CYLINDER", dims: { r: 0.14, h: 0.18 },           pose: { pos: [0.50, 0, 0], rpy: [0, 0, 0] } },
  { id: "part-plate",name: "PLATE",    kind: "PLATE",    dims: { w: 0.50, t: 0.02, d: 0.35 },  pose: { pos: [0.50, 0, 0], rpy: [0, 0, 0] } },
  { id: "part-step", name: "STEP",     kind: "STEP",     dims: { w: 0.40, h: 0.06, d: 0.30, topW: 0.28, topH: 0.08, topD: 0.22 }, pose: { pos: [0.50, 0, 0], rpy: [0, 0, 0] } },
];

// default WEAVE used by weld operations (engine arrives in Phase 2)
const WEAVE_DEFAULT = { type: "NONE", amplitude: 0.004, wavelength: 0.012, edgeDwell: 0.05 };

// ── lookups ─────────────────────────────────────────────────────────────────
function findTool(id) { return TOOL_LIBRARY.find(t => t.id === id) || null; }
function findTcp(id)  { return TCP_LIBRARY.find(t => t.id === id) || null; }
function findPart(id) { return PART_LIBRARY.find(p => p.id === id) || null; }

// ── parametric part mesh (generalizes the old CAMViewer3D buildWorkpiece) ────
// Returns a THREE.Group of clickable body meshes (userData.clickable) plus a
// yellow EdgesGeometry outline, placed by part.pose. Body origin is the part
// base, so it rests on the floor at pose.pos.y.
function buildPartMesh(part) {
  const grp = new THREE.Group(); grp.name = "PART";
  if (!part) return grp;
  const matBody = new THREE.MeshStandardMaterial({ color: 0x9ca8b4, metalness: 0.6, roughness: 0.4 });
  const matEdge = new THREE.LineBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.85 });
  const d = part.dims || {};
  const addBody = (geo, oy) => {
    const m = new THREE.Mesh(geo, matBody); m.position.y = oy; m.userData.clickable = true; grp.add(m);
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo), matEdge); e.position.y = oy; grp.add(e);
  };
  const kind = part.kind || "BOX";
  if (kind === "CYLINDER") {
    const r = d.r || 0.14, h = d.h || 0.18;
    addBody(new THREE.CylinderGeometry(r, r, h, 36), h / 2);
  } else if (kind === "PLATE") {
    const w = d.w || 0.50, t = d.t || 0.02, dp = d.d || 0.35;
    addBody(new THREE.BoxGeometry(w, t, dp), t / 2);
  } else if (kind === "STEP") {
    const w = d.w || 0.40, h = d.h || 0.06, dp = d.d || 0.30;
    const tw = d.topW || 0.28, th = d.topH || 0.08, td = d.topD || 0.22;
    addBody(new THREE.BoxGeometry(w, h, dp), h / 2);
    addBody(new THREE.BoxGeometry(tw, th, td), h + th / 2);
  } else {
    const w = d.w || 0.40, h = d.h || 0.15, dp = d.d || 0.30;
    addBody(new THREE.BoxGeometry(w, h, dp), h / 2);
  }
  const p = (part.pose && part.pose.pos) || [0.5, 0, 0];
  const r = (part.pose && part.pose.rpy) || [0, 0, 0];
  grp.position.set(p[0], p[1], p[2]);
  grp.rotation.set(r[0] * Math.PI / 180, r[1] * Math.PI / 180, r[2] * Math.PI / 180);
  return grp;
}

// top face height of a part (for quick CONTOUR/RASTER pattern generation)
function partTopY(part) {
  const d = part.dims || {}, base = (part.pose && part.pose.pos && part.pose.pos[1]) || 0;
  const kind = part.kind || "BOX";
  if (kind === "CYLINDER") return base + (d.h || 0.18);
  if (kind === "PLATE")    return base + (d.t || 0.02);
  if (kind === "STEP")     return base + (d.h || 0.06) + (d.topH || 0.08);
  return base + (d.h || 0.15);
}

Object.assign(window, {
  TCP_LIBRARY, TOOL_LIBRARY, PART_LIBRARY, WEAVE_DEFAULT,
  findTool, findTcp, findPart, buildPartMesh, partTopY,
});
