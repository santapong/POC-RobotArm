// Mock fleet + per-arm joint state + alert seed data. Drives the FLEET / ROBOT /
// LOGS / ANALYTICS screens before any backend is wired up.

import type { Alert, JointState, Robot, Status } from "@/types";

export const ARM_CALLSIGNS = [
  "FANUC-A", "KUKA-B", "UR-C", "ABB-D", "DENSO-E", "YASKAWA-F", "STAUBLI-G", "KAWASAKI-H",
  "ATLAS", "TITAN", "ORION", "HELIOS", "ARES", "KRONOS", "JANUS", "HERMES",
  "APOLLO", "ICARUS", "PERSEUS", "THESEUS", "HECTOR", "ACHILLES", "ODYSSEUS",
  "PROMETHEUS", "HYPERION", "NEMESIS", "TARTARUS", "CHARON", "TRITON", "BOREAS",
];

export const ARM_TASKS = [
  "PICK-PLACE · BIN-A7", "WELD-SEAM · PART-V4", "ASSEMBLE · MOTOR-12", "INSPECT · QA-PASS-3",
  "GLUE-BEAD · GASKET", "DEBURR · CASTING-9", "POLISH · FLANGE", "SCREW-DRIVE · 14×M5",
  "PALLETIZE · LAYER-3", "DEPALLETIZE · CRATE-2", "DISPENSE · ADHESIVE", "KIT · MOTOR-V4",
  "LOAD-CNC · OP-20", "UNLOAD-CNC · OP-30", "TENDED-MILL · CYCLE", "CALIBRATION · TCP",
  "IDLE-STANDBY", "HOMING", "DRY-RUN · PROGRAM-7", "TOOLCHANGE · T3→T7",
];

const STATUSES: Status[] = ["ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "IDLE", "IDLE", "FAULT", "TELEOP", "OFFLINE"];

export const JOINTS6: ReadonlyArray<readonly [string, number, number]> = [
  ["J1·BASE", -180, 180],
  ["J2·SHOULDER", -180, 60],
  ["J3·ELBOW", -150, 150],
  ["J4·WRIST_1", -180, 180],
  ["J5·WRIST_2", -125, 125],
  ["J6·WRIST_3", -360, 360],
];

const TOOLS = ["GRIPPER-2F", "GRIPPER-3F", "SUCTION", "WELDER-MIG", "DISPENSER", "DEBURR-SP", "DRILL-T7"];

// Deterministic seeded RNG so the fleet renders identically across runs.
function seededRng(seed: number): () => number {
  let s = seed;
  return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
}

export function buildFleet(count = 30): Robot[] {
  const r = seededRng(7);
  return Array.from({ length: count }, (_, i): Robot => {
    const num = String(i + 1).padStart(3, "0");
    const col = i % 6;
    const row = Math.floor(i / 6);
    const cs = ARM_CALLSIGNS[i % ARM_CALLSIGNS.length];
    const st = STATUSES[Math.floor(r() * STATUSES.length)];
    const battery = st === "OFFLINE" ? 0 : Math.floor(r() * 70 + 25);
    return {
      id: `ARM-${num}`,
      callsign: cs,
      hex: `0x${(0x2C00 + i * 11).toString(16).toUpperCase()}`,
      status: st,
      zone: `CELL-${String(i + 1).padStart(2, "0")}`,
      task: st === "OFFLINE" ? "—" : ARM_TASKS[Math.floor(r() * ARM_TASKS.length)],
      battery,
      uptime: st === "OFFLINE" ? 0 : Math.floor(r() * 1200) + 24,
      latencyMs: st === "OFFLINE" ? null : Math.floor(r() * 30 + 2),
      cpu: Math.floor(r() * 60 + 20),
      ram: Math.floor(r() * 50 + 30),
      temp: Math.floor(r() * 22 + 38),
      x: 0.08 + col * 0.155,
      y: 0.12 + row * 0.18,
      heading: 0,
      fw: `ARC-${4 + (i % 3)}.${Math.floor(r() * 20) + 20}.${Math.floor(r() * 9)}`,
      payload: +(2 + r() * 18).toFixed(1),
      reach: +(0.8 + r() * 0.9).toFixed(2),
      tcpSpeed: +(0.1 + r() * 1.4).toFixed(2),
      tasksDone: Math.floor(r() * 980),
      faults24h: Math.floor(r() * 4),
      cycleTime: +(2 + r() * 14).toFixed(1),
      cellRow: row,
      cellCol: col,
      tool: TOOLS[Math.floor(r() * TOOLS.length)],
      tcp: {
        x: +(0.4 + r() * 0.6).toFixed(3),
        y: +(-0.3 + r() * 0.6).toFixed(3),
        z: +(0.2 + r() * 0.8).toFixed(3),
        rx: +((r() - 0.5) * 180).toFixed(1),
        ry: +((r() - 0.5) * 180).toFixed(1),
        rz: +((r() - 0.5) * 180).toFixed(1),
      },
    };
  });
}

export function jointStateFor(seed: number): JointState[] {
  const r = seededRng(seed);
  return JOINTS6.map(([name, lo, hi]): JointState => {
    const cur = lo + r() * (hi - lo);
    const tgt = cur + (r() - 0.5) * 10;
    return {
      name, lo, hi,
      pos: +cur.toFixed(2),
      tgt: +tgt.toFixed(2),
      vel: +((r() - 0.5) * 60).toFixed(2),
      torque: +((r() - 0.5) * 32).toFixed(2),
      temp: Math.floor(38 + r() * 28),
      current: +(0.4 + r() * 4.2).toFixed(2),
      err: r() < 0.06 ? "STALL" : r() < 0.10 ? "OVERTEMP" : null,
    };
  });
}

export const ALERTS_INIT: Alert[] = [
  { ts: "06:14:22.108", sev: "WARN", src: "ARM-014", msg: "J3 elbow torque > 28 N·m for 1.2s · approaching limit" },
  { ts: "06:13:51.902", sev: "INFO", src: "FLEET",   msg: "Program PALLETIZE-L3 queued · 240 cycles" },
  { ts: "06:12:09.441", sev: "ERR",  src: "ARM-022", msg: "Collision detected · J4 contact force 18N · auto-stop" },
  { ts: "06:09:47.221", sev: "WARN", src: "ARM-007", msg: "TCP deviation 0.42mm > 0.30mm tolerance" },
  { ts: "06:07:18.005", sev: "INFO", src: "OPS",     msg: "Operator KOSTA acknowledged collision alert #882" },
  { ts: "06:04:02.117", sev: "OK",   src: "ARM-003", msg: "Tool change T3→T7 completed · 4.2s" },
  { ts: "06:01:33.880", sev: "ERR",  src: "ARM-018", msg: "Singularity warning · wrist alignment near J5=0" },
  { ts: "05:58:11.044", sev: "INFO", src: "CELL-09", msg: "Conveyor advance · part PCB-V4-2189 at station" },
  { ts: "05:55:48.700", sev: "WARN", src: "ARM-011", msg: "Vision: low contrast on QR-tag · re-illuminate" },
  { ts: "05:52:09.331", sev: "INFO", src: "ARM-024", msg: "Cycle 412 of 480 · in-tolerance · ±0.08mm" },
];
