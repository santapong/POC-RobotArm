// Tool / part / TCP-frame catalogs — code-level reference data that the
// project's operation tree (Job) refers to by id. Mirrors Robotmaster's split
// between a tool database and the part program.

import type { Part, TcpFrame, Tool, Weave } from "@/types";

export const TCP_LIBRARY: TcpFrame[] = [
  { id: "tcp-flange", name: "FLANGE",   offset: [0, 0, 0],         rpy: [0, 0, 0],   payload: { mass: 0,   com: [0, 0, 0] } },
  { id: "tcp-tip",    name: "TOOL TIP", offset: [0, 0.130, 0],     rpy: [0, 0, 0],   payload: { mass: 1.8, com: [0, 0, 0.05] } },
  { id: "tcp-weld",   name: "WELD TIP", offset: [0.027, 0.158, 0], rpy: [-35, 0, 0], payload: { mass: 2.4, com: [0, 0, 0.06] } },
];

export const TOOL_LIBRARY: Tool[] = [
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

export const PART_LIBRARY: Part[] = [
  { id: "part-box",   name: "BLOCK",    kind: "BOX",      dims: { w: 0.40, h: 0.15, d: 0.30 },                                                       pose: { pos: [0.50, 0, 0], rpy: [0, 0, 0] } },
  { id: "part-cyl",   name: "CYLINDER", kind: "CYLINDER", dims: { r: 0.14, h: 0.18 },                                                                pose: { pos: [0.50, 0, 0], rpy: [0, 0, 0] } },
  { id: "part-plate", name: "PLATE",    kind: "PLATE",    dims: { w: 0.50, t: 0.02, d: 0.35 },                                                       pose: { pos: [0.50, 0, 0], rpy: [0, 0, 0] } },
  { id: "part-step",  name: "STEP",     kind: "STEP",     dims: { w: 0.40, h: 0.06, d: 0.30, topW: 0.28, topH: 0.08, topD: 0.22 }, pose: { pos: [0.50, 0, 0], rpy: [0, 0, 0] } },
];

export const WEAVE_DEFAULT: Weave = { type: "NONE", amplitude: 0.004, wavelength: 0.012, edgeDwell: 0.05 };

export function findTool(id: string | undefined | null): Tool | null {
  if (!id) return null;
  return TOOL_LIBRARY.find(t => t.id === id) || null;
}
export function findTcp(id: string | undefined | null): TcpFrame | null {
  if (!id) return null;
  return TCP_LIBRARY.find(t => t.id === id) || null;
}
export function findPart(id: string | undefined | null): Part | null {
  if (!id) return null;
  return PART_LIBRARY.find(p => p.id === id) || null;
}
