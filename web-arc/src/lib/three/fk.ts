// Forward kinematics + active-tool state. armTCP() builds (and caches) an
// off-screen arm with the active tool, applies the joint angles, and reads the
// world-space TCP. Every consumer — drawn path, waypoint spheres, playback
// marker, the rendered arm — derives positions through this single FK, so the
// gripper is always exactly on the path it's following. Replaces the old
// window.ACTIVE_TOOL + _fkArm globals with proper module state.

import { Vector3 } from "three";
import type { Tool, Vec3 } from "@/types";
import { applyJointAngles, buildArmMesh, type ArmMesh } from "./arm-mesh";

let _activeTool: Tool | null = null;
let _fkArm: ArmMesh | null = null;
const _v = new Vector3();
const subs = new Set<() => void>();

export function getActiveTool(): Tool | null { return _activeTool; }

export function setActiveTool(tool: Tool | null): void {
  if (tool === _activeTool) return;
  _activeTool = tool;
  _fkArm = null;                            // invalidate the FK cache
  subs.forEach(fn => fn());
}

export function subscribeActiveTool(fn: () => void): () => void {
  subs.add(fn);
  return () => { subs.delete(fn); };
}

export function armTCP(jointAnglesDeg: number[]): Vec3 {
  if (!_fkArm) _fkArm = buildArmMesh(_activeTool);
  const rad = (jointAnglesDeg || [0, -60, 90, 0, 40, 0]).map(d => d * Math.PI / 180);
  applyJointAngles(_fkArm, rad);
  _fkArm.root.updateMatrixWorld(true);
  _fkArm.tcp.getWorldPosition(_v);
  return [_v.x, _v.y, _v.z];
}
