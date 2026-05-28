// Shared domain types for the ARC·OPS arm console.

export type Vec3 = [number, number, number];

export type Status = "ACTIVE" | "IDLE" | "TELEOP" | "FAULT" | "OFFLINE";

export interface TcpPose {
  x: number; y: number; z: number;
  rx: number; ry: number; rz: number;
}

export interface Robot {
  id: string;
  callsign: string;
  hex: string;
  status: Status;
  zone: string;
  task: string;
  battery: number;
  uptime: number;
  latencyMs: number | null;
  cpu: number;
  ram: number;
  temp: number;
  x: number;
  y: number;
  heading: number;
  fw: string;
  payload: number;
  reach: number;
  tcpSpeed: number;
  tasksDone: number;
  faults24h: number;
  cycleTime: number;
  cellRow: number;
  cellCol: number;
  tool: string;
  tcp: TcpPose;
}

export interface JointState {
  name: string;
  lo: number;
  hi: number;
  pos: number;
  tgt: number;
  vel: number;
  torque: number;
  temp: number;
  current: number;
  err: "STALL" | "OVERTEMP" | null;
}

export type Severity = "OK" | "INFO" | "WARN" | "ERR" | "DEBUG";

export interface Alert {
  ts: string;
  sev: Severity;
  src: string;
  msg: string;
}

export type MoveType = "MoveJ" | "MoveL" | "MoveC" | "MoveP";

export interface IoTrigger {
  type: string;
  ch: number;
  value: boolean;
  label: string;
}

export interface Waypoint {
  id: number;
  name: string;
  type: MoveType;
  tcp: Vec3;
  rot: Vec3;
  joints: number[];
  vel: number;
  acc: number;
  blend: number;
  dwell: number;
  io: IoTrigger | null;
  t: number;
  op?: string;
}

export interface Trajectory {
  id: string;
  name: string;
  author: string;
  created?: string;
  modified?: string;
  tool: string;
  payload: number;
  totalTime: number;
  pathLength: number;
  maxTCPSpeed: number;
  maxJointVel: number;
  maxJointAcc: number;
  singularityWarnings: number;
  collisionWarnings: number;
  reachWarnings: number;
  waypoints: Waypoint[];
}

export type ToolType =
  | "GRIPPER_2F" | "GRIPPER_3F" | "SUCTION" | "MIG" | "SPINDLE" | "DISPENSER";

export interface Tool {
  id: string;
  name: string;
  type: ToolType;
  mount: { offset: Vec3; rpy: Vec3 };
  tcpOffset: Vec3;
  size: { stroke?: number; length?: number; dia?: number; width?: number };
  lead: { in: number; out: number };
}

export interface TcpFrame {
  id: string;
  name: string;
  offset: Vec3;
  rpy: Vec3;
  payload: { mass: number; com: Vec3 };
}

export type PartKind = "BOX" | "CYLINDER" | "PLATE" | "STEP";

export interface Part {
  id: string;
  name: string;
  kind: PartKind;
  dims: Record<string, number>;
  pose: { pos: Vec3; rpy: Vec3 };
}

export type WeaveType = "NONE" | "ZIGZAG" | "SINE" | "TRIANGLE" | "TRAPEZOID";

export interface Weave {
  type: WeaveType;
  amplitude: number;
  wavelength: number;
  edgeDwell: number;
}

export interface Pick {
  point: Vec3;
  normal: Vec3;
  dwell?: number;
}

export type OpKind = "PICKPLACE" | "WELD" | "MILL" | "DISPENSE";
export type Strategy = "POINTS" | "CONTOUR" | "RASTER" | "SEAM";

export interface OperationParams {
  standoff: number;
  approach: number;
  vel: number;
  acc: number;
  weave: Weave;
  picks: Pick[];
}

export interface Operation {
  id: number;
  name: string;
  enabled: boolean;
  kind: OpKind;
  partId: string;
  toolId: string;
  tcpId: string;
  strategy: Strategy;
  params: OperationParams;
}

export interface Job {
  id: string;
  name: string;
  author: string;
  activeTcpId: string;
  postFormat: string;
  ops: Operation[];
}

export interface Doc {
  version: number;
  meta: { name: string; author: string; modified: string };
  job: Job;
  activeTcpId: string;
  // Optional: which RobotModel the project was authored for. Missing means
  // "use DEFAULT_ROBOT_ID" — a v1 doc loaded under v2 leaves this unset and
  // the UI / FK fall back to the default. See lib/robots.ts.
  robotId?: string;
}

// Catalog entry for a 6-DoF arm (UR, ABB, KUKA, Fanuc, …). The mesh and IK
// are schematic — link lengths drive size/reach scaling but don't model each
// manufacturer's brand-specific kinematics. The numeric specs (payload,
// reach, joint limits, max speeds) are sourced from public datasheets and
// drive FK reach, the workspace sphere, and the spec readouts.
export interface RobotLinks {
  baseHeight: number;   // floor → J2 (m)
  upperArm: number;     // J2 → J3 (m)
  forearm: number;      // J3 → J4 (m)
  wristOffset: number;  // J4 → J5 → J6 chain (m)
  flangeOffset: number; // J6 → flange face (m, without tool)
}

export interface RobotModel {
  id: string;
  name: string;
  manufacturer: string;
  family: string;
  dof: 6;
  payload: number;             // kg
  reach: number;               // m
  links: RobotLinks;
  jointLimits: [number, number][];   // 6 (lo, hi) pairs, degrees
  maxJointVel: number[];              // °/s per joint
  maxTcpSpeed: number;                // m/s
  accent: string;                     // brand accent (rgb hex)
}

export interface CamOptions {
  standoff?: number;
  approachHeight?: number;
  vel?: number;
  acc?: number;
  home?: Vec3;
  moveType?: MoveType;
  tool?: Tool | null;
  weave?: Weave | null;
}
