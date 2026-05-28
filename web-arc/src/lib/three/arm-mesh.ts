// 6-DoF arm kinematic chain + swappable end-effector. The TCP group is a direct
// child of j6 — its local position is set by the tool's tcpOffset, so the
// forward-kinematics TCP (see fk.ts) automatically tracks whichever tool is
// mounted. JOINT_SIGN/applyJointAngles are shared by every viewer and the FK
// helper, so the rendered pose, the FK TCP, and the path always agree.

import {
  ArrowHelper, BoxGeometry, CylinderGeometry, Group, Mesh,
  MeshStandardMaterial, TorusGeometry, Vector3,
} from "three";
import type { Tool } from "@/types";

export type Axis = "x" | "y" | "z";

export interface ArmMesh {
  root: Group;
  base: Group;
  joints: Group[];
  axes: Axis[];
  tcp: Group;
}

export interface ToolMesh {
  group: Group;
  tcp: Group;
}

// +J2 lifts the shoulder up, +J3 bends the elbow (UR/KUKA convention).
export const JOINT_SIGN: ReadonlyArray<1 | -1> = [1, -1, -1, 1, 1, 1];

export function applyJointAngles(arm: ArmMesh, anglesRad: number[]): void {
  for (let i = 0; i < 6; i++) {
    const joint = arm.joints[i];
    const axis = arm.axes[i];
    const v = (anglesRad[i] || 0) * JOINT_SIGN[i];
    if (axis === "x") joint.rotation.x = v;
    else if (axis === "y") joint.rotation.y = v;
    else joint.rotation.z = v;
  }
}

export function buildArmMesh(tool: Tool | null): ArmMesh {
  const root = new Group(); root.name = "ARM_ROOT";

  const matBase  = new MeshStandardMaterial({ color: 0x1a2028, metalness: 0.7, roughness: 0.45 });
  const matLink  = new MeshStandardMaterial({ color: 0x2a323b, metalness: 0.6, roughness: 0.5 });
  const matJoint = new MeshStandardMaterial({ color: 0x0d1117, metalness: 0.85, roughness: 0.3 });
  const matAccent = new MeshStandardMaterial({
    color: 0x4ade80, emissive: 0x4ade80, emissiveIntensity: 0.6, metalness: 0.4, roughness: 0.4,
  });

  const cyl = (r1: number, r2: number, h: number, mat: MeshStandardMaterial, segs = 32) =>
    new Mesh(new CylinderGeometry(r1, r2, h, segs), mat);
  const box = (w: number, h: number, d: number, mat: MeshStandardMaterial) =>
    new Mesh(new BoxGeometry(w, h, d), mat);
  const ring = (r: number, t: number, mat: MeshStandardMaterial) =>
    new Mesh(new TorusGeometry(r, t, 8, 32), mat);

  // BASE
  const base = new Group(); base.name = "BASE";
  const basePlate = cyl(0.20, 0.22, 0.04, matBase); basePlate.position.y = 0.02;
  const baseRing  = ring(0.18, 0.012, matAccent.clone()); baseRing.position.y = 0.045; baseRing.rotation.x = Math.PI / 2;
  const baseCol   = cyl(0.13, 0.13, 0.18, matBase); baseCol.position.y = 0.13;
  base.add(basePlate, baseRing, baseCol);
  root.add(base);

  // J1 — rotate around Y at top of base
  const j1 = new Group(); j1.name = "J1"; j1.position.y = 0.22; base.add(j1);
  const shoulderHead = cyl(0.14, 0.14, 0.13, matJoint, 24);
  shoulderHead.rotation.z = Math.PI / 2; shoulderHead.position.y = 0.04;
  j1.add(shoulderHead);
  for (const sgn of [-1, 1]) {
    const r = ring(0.13, 0.010, matAccent.clone());
    r.rotation.y = Math.PI / 2; r.position.set(sgn * 0.065, 0.04, 0);
    j1.add(r);
  }

  // J2 — shoulder, rotates around Z
  const j2 = new Group(); j2.name = "J2"; j2.position.set(0, 0.04, 0); j1.add(j2);
  const upper = new Group();
  const armLen1 = 0.42;
  const upperLink = box(armLen1, 0.10, 0.10, matLink); upperLink.position.x = armLen1 / 2; upper.add(upperLink);
  const cable = box(armLen1 * 0.96, 0.025, 0.03, matJoint); cable.position.set(armLen1 / 2, 0.062, 0); upper.add(cable);
  j2.add(upper);

  // J3 — elbow at end of upper arm
  const j3 = new Group(); j3.name = "J3"; j3.position.x = armLen1; j2.add(j3);
  const elbowHead = cyl(0.085, 0.085, 0.13, matJoint, 24); elbowHead.rotation.x = Math.PI / 2;
  j3.add(elbowHead);
  for (const sgn of [-1, 1]) {
    const r = ring(0.082, 0.008, matAccent.clone());
    r.position.set(0, 0, sgn * 0.065);
    j3.add(r);
  }
  const fore = new Group();
  const armLen2 = 0.34;
  const foreLink = box(armLen2, 0.08, 0.08, matLink); foreLink.position.x = armLen2 / 2; fore.add(foreLink);
  j3.add(fore);

  // J4 — wrist 1, rotates around X
  const j4 = new Group(); j4.name = "J4"; j4.position.x = armLen2; j3.add(j4);
  const wrist1 = cyl(0.055, 0.055, 0.10, matJoint, 24); wrist1.rotation.z = Math.PI / 2; wrist1.position.x = 0.05;
  j4.add(wrist1);
  const wRing1 = ring(0.052, 0.007, matAccent.clone()); wRing1.rotation.y = Math.PI / 2; wRing1.position.x = 0.1;
  j4.add(wRing1);

  // J5 — wrist 2, rotates around Z
  const j5 = new Group(); j5.name = "J5"; j5.position.x = 0.10; j4.add(j5);
  const wrist2 = cyl(0.050, 0.050, 0.09, matJoint, 24); wrist2.rotation.x = Math.PI / 2;
  j5.add(wrist2);
  const wRing2 = ring(0.048, 0.007, matAccent.clone()); wRing2.position.set(0, 0, 0.046);
  j5.add(wRing2);

  // J6 — wrist 3, baked rotation.x = π/2 so flange points forward; driven axis = y
  const j6 = new Group(); j6.name = "J6";
  j6.position.x = 0; j6.position.z = 0.055; j6.rotation.x = Math.PI / 2;
  j5.add(j6);
  const flange = cyl(0.045, 0.045, 0.025, matJoint, 24); flange.position.y = 0.0125;
  j6.add(flange);
  const flangeRing = ring(0.043, 0.006, matAccent.clone()); flangeRing.rotation.x = Math.PI / 2; flangeRing.position.y = 0.025;
  j6.add(flangeRing);

  // Swappable tool — tcp group is its child so the FK TCP follows tool length
  const built = buildToolMesh(tool);
  j6.add(built.group);
  j6.add(built.tcp);

  const joints = [j1, j2, j3, j4, j5, j6];
  const axes: Axis[] = ["y", "z", "z", "x", "z", "y"];
  return { root, base, joints, axes, tcp: built.tcp };
}

// End-effector mesh for a tool spec. `tool == null` reproduces the original
// 2-finger gripper baseline so existing callers / FK numbers are unchanged.
export function buildToolMesh(tool: Tool | null): ToolMesh {
  const matTool   = new MeshStandardMaterial({ color: 0x111111, metalness: 0.9, roughness: 0.25 });
  const matMetal  = new MeshStandardMaterial({ color: 0x2a323b, metalness: 0.7, roughness: 0.4 });
  const matAccent = new MeshStandardMaterial({ color: 0x4ade80, emissive: 0x4ade80, emissiveIntensity: 0.6, metalness: 0.4, roughness: 0.4 });
  const matCopper = new MeshStandardMaterial({ color: 0xc77b3b, metalness: 0.8, roughness: 0.35 });
  const cyl = (r1: number, r2: number, h: number, mat: MeshStandardMaterial, segs = 20) =>
    new Mesh(new CylinderGeometry(r1, r2, h, segs), mat);
  const box = (w: number, h: number, d: number, mat: MeshStandardMaterial) =>
    new Mesh(new BoxGeometry(w, h, d), mat);
  const add = (grp: Group, mesh: Mesh, x: number, y: number, z: number) => {
    mesh.position.set(x, y, z); grp.add(mesh); return mesh;
  };

  const group = new Group(); group.name = "TOOL";
  const type = tool?.type || "GRIPPER_2F";
  const size = tool?.size || {};

  const mOff = tool?.mount?.offset || [0, 0, 0];
  const mRpy = tool?.mount?.rpy || [0, 0, 0];
  group.position.set(mOff[0], 0.025 + mOff[1], mOff[2]);
  group.rotation.set(mRpy[0] * Math.PI / 180, mRpy[1] * Math.PI / 180, mRpy[2] * Math.PI / 180);

  let defTcp: [number, number, number] = [0, 0.13, 0];

  if (type === "GRIPPER_2F" || type === "GRIPPER_3F") {
    const stroke = size.stroke ?? 0.056;
    const fingerLen = size.length ?? 0.06;
    add(group, cyl(0.035, 0.035, 0.04, matTool, 16), 0, 0.045, 0);
    const n = type === "GRIPPER_3F" ? 3 : 2;
    for (let k = 0; k < n; k++) {
      const ang = type === "GRIPPER_3F" ? (k / 3) * Math.PI * 2 : (k === 0 ? Math.PI : 0);
      const fx = Math.cos(ang) * (stroke / 2), fz = Math.sin(ang) * (stroke / 2);
      add(group, box(0.012, fingerLen, 0.025, matTool), fx, 0.06 + fingerLen / 2, fz);
      add(group, box(0.008, 0.015, 0.022, matAccent), fx * 0.85, 0.11, fz * 0.85);
    }
    defTcp = [0, 0.13, 0];
  } else if (type === "SUCTION") {
    const dia = size.dia ?? 0.05;
    add(group, cyl(0.018, 0.018, 0.06, matMetal, 16), 0, 0.05, 0);
    add(group, cyl(dia / 2, dia / 2.6, 0.03, matTool, 20), 0, 0.095, 0);
    defTcp = [0, 0.12, 0];
  } else if (type === "MIG") {
    const len = size.length ?? 0.16;
    const body = cyl(0.022, 0.022, len * 0.55, matTool, 16);
    body.position.set(0, 0.03 + len * 0.275, 0);
    body.rotation.z = -0.35;
    group.add(body);
    add(group, cyl(0.02, 0.008, 0.05, matCopper, 16), Math.sin(0.35) * len * 0.5, 0.03 + len * 0.62, 0);
    add(group, cyl(0.0015, 0.0015, 0.03, matAccent, 8), Math.sin(0.35) * len * 0.5, 0.03 + len * 0.75, 0);
    defTcp = [Math.sin(0.35) * len * 0.5, 0.03 + len * 0.8, 0];
  } else if (type === "SPINDLE") {
    const len = size.length ?? 0.18;
    add(group, cyl(0.05, 0.03, len * 0.6, matMetal, 20), 0, 0.03 + len * 0.3, 0);
    add(group, cyl(0.012, 0.012, len * 0.3, matTool, 16), 0, 0.03 + len * 0.6, 0);
    add(group, cyl(0.004, 0.004, len * 0.25, matAccent, 12), 0, 0.03 + len * 0.8, 0);
    defTcp = [0, 0.03 + len * 0.95, 0];
  } else if (type === "DISPENSER") {
    const len = size.length ?? 0.14;
    add(group, cyl(0.02, 0.02, len * 0.6, matTool, 16), 0, 0.03 + len * 0.3, 0);
    add(group, cyl(0.008, 0.001, 0.04, matMetal, 12), 0, 0.03 + len * 0.7, 0);
    defTcp = [0, 0.03 + len * 0.85, 0];
  } else {
    add(group, cyl(0.035, 0.035, 0.05, matTool, 16), 0, 0.05, 0);
  }

  const off = tool?.tcpOffset || defTcp;
  const tcp = new Group(); tcp.name = "TCP";
  tcp.position.set(off[0], off[1], off[2]);
  const aL = 0.06;
  tcp.add(
    new ArrowHelper(new Vector3(1, 0, 0), new Vector3(), aL, 0xef4444, 0.02, 0.012),
    new ArrowHelper(new Vector3(0, 1, 0), new Vector3(), aL, 0x4ade80, 0.02, 0.012),
    new ArrowHelper(new Vector3(0, 0, 1), new Vector3(), aL, 0x38bdf8, 0.02, 0.012),
  );
  return { group, tcp };
}
