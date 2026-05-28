// Forward kinematics + active-tool / active-robot state. armTCP() builds
// (and caches) an off-screen arm with the active tool AND the active robot,
// applies the joint angles, and reads the world-space TCP. Every consumer —
// drawn path, waypoint spheres, playback marker, the rendered arm — derives
// positions through this single FK, so the gripper is always exactly on the
// path it's following.

import { Vector3 } from "three";
import type { RobotModel, Tool, Vec3 } from "@/types";
import { applyJointAngles, buildArmMesh, type ArmMesh } from "./arm-mesh";

let _activeTool: Tool | null = null;
let _activeRobot: RobotModel | null = null;
let _fkArm: ArmMesh | null = null;
const _v = new Vector3();
const toolSubs = new Set<() => void>();
const robotSubs = new Set<() => void>();

export function getActiveTool(): Tool | null { return _activeTool; }
export function getActiveRobot(): RobotModel | null { return _activeRobot; }

export function setActiveTool(tool: Tool | null): void {
  if (tool === _activeTool) return;
  _activeTool = tool;
  _fkArm = null;                            // invalidate the FK cache
  toolSubs.forEach(fn => fn());
}

export function setActiveRobot(robot: RobotModel | null): void {
  if (robot === _activeRobot) return;
  _activeRobot = robot;
  _fkArm = null;                            // invalidate the FK cache
  robotSubs.forEach(fn => fn());
}

export function subscribeActiveTool(fn: () => void): () => void {
  toolSubs.add(fn);
  return () => { toolSubs.delete(fn); };
}

export function subscribeActiveRobot(fn: () => void): () => void {
  robotSubs.add(fn);
  return () => { robotSubs.delete(fn); };
}

export function armTCP(jointAnglesDeg: number[]): Vec3 {
  if (!_fkArm) _fkArm = buildArmMesh(_activeTool, _activeRobot);
  const rad = (jointAnglesDeg || [0, -60, 90, 0, 40, 0]).map(d => d * Math.PI / 180);
  applyJointAngles(_fkArm, rad);
  _fkArm.root.updateMatrixWorld(true);
  _fkArm.tcp.getWorldPosition(_v);
  return [_v.x, _v.y, _v.z];
}
