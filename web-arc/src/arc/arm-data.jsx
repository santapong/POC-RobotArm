// arm-data.jsx — 6-DOF arm fleet overrides (loaded AFTER data.jsx; reuses widgets/hooks)

const ARM_CALLSIGNS = [
  "FANUC-A","KUKA-B","UR-C","ABB-D","DENSO-E","YASKAWA-F","STAUBLI-G","KAWASAKI-H",
  "ATLAS","TITAN","ORION","HELIOS","ARES","KRONOS","JANUS","HERMES",
  "APOLLO","ICARUS","PERSEUS","THESEUS","HECTOR","ACHILLES","ODYSSEUS",
  "PROMETHEUS","HYPERION","NEMESIS","TARTARUS","CHARON","TRITON","BOREAS"
];

const ARM_TASKS = [
  "PICK-PLACE · BIN-A7","WELD-SEAM · PART-V4","ASSEMBLE · MOTOR-12","INSPECT · QA-PASS-3",
  "GLUE-BEAD · GASKET","DEBURR · CASTING-9","POLISH · FLANGE","SCREW-DRIVE · 14×M5",
  "PALLETIZE · LAYER-3","DEPALLETIZE · CRATE-2","DISPENSE · ADHESIVE","KIT · MOTOR-V4",
  "LOAD-CNC · OP-20","UNLOAD-CNC · OP-30","TENDED-MILL · CYCLE","CALIBRATION · TCP",
  "IDLE-STANDBY","HOMING","DRY-RUN · PROGRAM-7","TOOLCHANGE · T3→T7"
];

const ARM_STATIONS = ["CELL-01","CELL-02","CELL-03","CELL-04","CELL-05","CELL-06","CELL-07","CELL-08","CELL-09","CELL-10"];

function rngArm(seed) {
  let s = seed;
  return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
}

// 6-DOF joints with realistic ranges (UR/KUKA-ish)
const JOINTS6 = [
  ["J1·BASE",    -180,  180],
  ["J2·SHOULDER",-180,  60],
  ["J3·ELBOW",   -150,  150],
  ["J4·WRIST_1", -180,  180],
  ["J5·WRIST_2", -125,  125],
  ["J6·WRIST_3", -360,  360],
];

function buildArmFleet(count = 30) {
  const r = rngArm(7);
  // arrange in factory grid: 5 rows × 6 cols
  return Array.from({ length: count }, (_, i) => {
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
      battery,            // here = pneumatic / aux power %
      uptime: st === "OFFLINE" ? 0 : Math.floor(r() * 1200) + 24,
      latencyMs: st === "OFFLINE" ? null : Math.floor(r() * 30 + 2),
      cpu: Math.floor(r() * 60 + 20),
      ram: Math.floor(r() * 50 + 30),
      temp: Math.floor(r() * 22 + 38),
      // grid cell positions on factory map (0..1)
      x: 0.08 + col * 0.155,
      y: 0.12 + row * 0.18,
      heading: 0,
      fw: `ARC-${4 + (i%3)}.${Math.floor(r()*20) + 20}.${Math.floor(r()*9)}`,
      payload: +(2 + r() * 18).toFixed(1),    // kg payload
      reach: +(0.8 + r() * 0.9).toFixed(2),   // m
      tcpSpeed: +(0.1 + r() * 1.4).toFixed(2),// m/s
      tasksDone: Math.floor(r() * 980),
      faults24h: Math.floor(r() * 4),
      cycleTime: +(2 + r() * 14).toFixed(1),
      cellRow: row, cellCol: col,
      tool: ["GRIPPER-2F","GRIPPER-3F","SUCTION","WELDER-MIG","DISPENSER","DEBURR-SP","DRILL-T7"][Math.floor(r() * 7)],
      // current TCP pose (mock)
      tcp: {
        x: +(0.4 + r() * 0.6).toFixed(3),
        y: +(-0.3 + r() * 0.6).toFixed(3),
        z: +(0.2 + r() * 0.8).toFixed(3),
        rx: +((r()-0.5)*180).toFixed(1),
        ry: +((r()-0.5)*180).toFixed(1),
        rz: +((r()-0.5)*180).toFixed(1),
      },
    };
  });
}

function armJointStateFor(seed) {
  const r = rngArm(seed);
  return JOINTS6.map(([name, lo, hi]) => {
    const cur = lo + r() * (hi - lo);
    const tgt = cur + (r() - 0.5) * 10;
    return {
      name, lo, hi,
      pos: +cur.toFixed(2),
      tgt: +tgt.toFixed(2),
      vel: +((r() - 0.5) * 60).toFixed(2),
      torque: +((r() - 0.5) * 32).toFixed(2),
      temp: Math.floor(38 + r() * 28),
      current: +(0.4 + r() * 4.2).toFixed(2), // amps
      err: r() < 0.06 ? "STALL" : r() < 0.10 ? "OVERTEMP" : null,
    };
  });
}

// shared STATUSES from data.jsx — re-import via window
const STATUSES = ["ACTIVE","ACTIVE","ACTIVE","ACTIVE","IDLE","IDLE","FAULT","TELEOP","OFFLINE"];

// ── ARM ALERTS ──
const ARM_ALERTS = [
  { ts: "06:14:22.108", sev: "WARN",  src: "ARM-014",  msg: "J3 elbow torque > 28 N·m for 1.2s · approaching limit" },
  { ts: "06:13:51.902", sev: "INFO",  src: "FLEET",    msg: "Program PALLETIZE-L3 queued · 240 cycles" },
  { ts: "06:12:09.441", sev: "ERR",   src: "ARM-022",  msg: "Collision detected · J4 contact force 18N · auto-stop" },
  { ts: "06:09:47.221", sev: "WARN",  src: "ARM-007",  msg: "TCP deviation 0.42mm > 0.30mm tolerance" },
  { ts: "06:07:18.005", sev: "INFO",  src: "OPS",      msg: "Operator KOSTA acknowledged collision alert #882" },
  { ts: "06:04:02.117", sev: "OK",    src: "ARM-003",  msg: "Tool change T3→T7 completed · 4.2s" },
  { ts: "06:01:33.880", sev: "ERR",   src: "ARM-018",  msg: "Singularity warning · wrist alignment near J5=0" },
  { ts: "05:58:11.044", sev: "INFO",  src: "CELL-09",  msg: "Conveyor advance · part PCB-V4-2189 at station" },
  { ts: "05:55:48.700", sev: "WARN",  src: "ARM-011",  msg: "Vision: low contrast on QR-tag · re-illuminate" },
  { ts: "05:52:09.331", sev: "INFO",  src: "ARM-024",  msg: "Cycle 412 of 480 · in-tolerance · ±0.08mm" },
];

// override globals so screens pick up arm versions
Object.assign(window, {
  buildFleet: buildArmFleet,
  JOINTS: JOINTS6,
  jointStateFor: armJointStateFor,
  ALERTS_INIT: ARM_ALERTS,
  ARM_TASKS, ARM_STATIONS, JOINTS6,
});

// ── EXAMPLE TRAJECTORY ──────────────────────────────────────────────────
// Y = vertical (THREE convention). Distances in meters, angles in degrees.
const EXAMPLE_TRAJECTORY = {
  id: "TRAJ-0142",
  name: "PICK-PLACE · BIN-A7 → KITTING-3",
  author: "OP·KOSTA",
  created: "2026-05-24T14:22:00Z",
  modified: "2026-05-26T06:11:48Z",
  tool: "GRIPPER-2F",
  payload: 1.8,
  totalTime: 4.82,
  pathLength: 1.842,
  maxTCPSpeed: 0.84,
  maxJointVel: 142.6,
  maxJointAcc: 580.0,
  singularityWarnings: 0,
  collisionWarnings: 0,
  reachWarnings: 0,
  waypoints: [
    { id: 1, name: "HOME",            type: "MoveJ", tcp: [0.000, 0.900,  0.000], rot: [180, 0, 0], joints: [   0, -90,   0,  0, 90,    0], vel: 60,  acc: 50, blend:  0, dwell: 0,    io: null, t: 0.00 },
    { id: 2, name: "APPROACH·PICK",   type: "MoveJ", tcp: [0.420, 0.450, -0.180], rot: [180, 0, 0], joints: [-22.4, -68.2, 84.1, 0, 74.1, -22.4], vel: 80,  acc: 60, blend: 20, dwell: 0,    io: null, t: 0.95 },
    { id: 3, name: "PICK·DESCEND",    type: "MoveL", tcp: [0.420, 0.180, -0.180], rot: [180, 0, 0], joints: [-22.4, -42.1, 58.3, 0, 73.8, -22.4], vel: 30,  acc: 40, blend:  0, dwell: 0.20, io: { type:"DO", ch:0, value:true,  label:"GRIPPER CLOSE" }, t: 1.85 },
    { id: 4, name: "PICK·LIFT",       type: "MoveL", tcp: [0.420, 0.450, -0.180], rot: [180, 0, 0], joints: [-22.4, -68.2, 84.1, 0, 74.1, -22.4], vel: 40,  acc: 50, blend: 10, dwell: 0,    io: null, t: 2.42 },
    { id: 5, name: "TRANSIT",         type: "MoveJ", tcp: [0.140, 0.500,  0.080], rot: [180, 0, 0], joints: [ 29.8, -75.4, 78.2, 0, 84.0,  29.8], vel:100,  acc: 80, blend: 30, dwell: 0,    io: null, t: 2.96 },
    { id: 6, name: "APPROACH·PLACE",  type: "MoveJ", tcp: [-0.320, 0.450, 0.240], rot: [180, 0, 0], joints: [143.2, -68.2, 84.1, 0, 74.1, 143.2], vel: 80,  acc: 60, blend: 20, dwell: 0,    io: null, t: 3.62 },
    { id: 7, name: "PLACE·DESCEND",   type: "MoveL", tcp: [-0.320, 0.205, 0.240], rot: [180, 0, 0], joints: [143.2, -44.5, 60.1, 0, 74.1, 143.2], vel: 30,  acc: 40, blend:  0, dwell: 0.15, io: { type:"DO", ch:0, value:false, label:"GRIPPER OPEN"  }, t: 4.18 },
    { id: 8, name: "PLACE·RETREAT",   type: "MoveL", tcp: [-0.320, 0.500, 0.240], rot: [180, 0, 0], joints: [143.2, -72.1, 86.4, 0, 74.1, 143.2], vel: 40,  acc: 50, blend: 10, dwell: 0,    io: null, t: 4.62 },
    { id: 9, name: "HOME",            type: "MoveJ", tcp: [0.000, 0.900,  0.000], rot: [180, 0, 0], joints: [   0, -90,   0,  0, 90,    0], vel: 60,  acc: 50, blend:  0, dwell: 0,    io: null, t: 4.82 },
  ],
};

// ── TRAJECTORY HELPERS ──────────────────────────────────────────────────
function interpolateAtTime(waypoints, t) {
  if (!waypoints || waypoints.length === 0) return null;
  if (t <= waypoints[0].t) return { joints: waypoints[0].joints.slice(), tcp: waypoints[0].tcp.slice(), segment: 0 };
  const last = waypoints[waypoints.length - 1];
  if (t >= last.t) return { joints: last.joints.slice(), tcp: last.tcp.slice(), segment: waypoints.length - 1 };
  for (let i = 0; i < waypoints.length - 1; i++) {
    const a = waypoints[i], b = waypoints[i + 1];
    if (t >= a.t && t <= b.t) {
      const f = (t - a.t) / Math.max(0.001, (b.t - a.t));
      const ef = f * f * (3 - 2 * f); // smoothstep
      return {
        joints: a.joints.map((v, k) => v + (b.joints[k] - v) * ef),
        tcp:    a.tcp.map(   (v, k) => v + (b.tcp[k]    - v) * ef),
        segment: i,
      };
    }
  }
  return { joints: waypoints[0].joints.slice(), tcp: waypoints[0].tcp.slice(), segment: 0 };
}

function buildPathSamples(waypoints, samples = 240) {
  if (!waypoints || waypoints.length < 2) return [];
  const total = waypoints[waypoints.length - 1].t;
  const pts = [];
  for (let i = 0; i < samples; i++) {
    const t = (i / (samples - 1)) * total;
    const s = interpolateAtTime(waypoints, t);
    // sample the ACTUAL tool path (forward kinematics of the interpolated
    // joints) so the drawn path matches where the gripper really goes
    pts.push(window.armTCP ? window.armTCP(s.joints) : s.tcp);
  }
  return pts;
}

function buildVelocityProfile(waypoints, samples = 240) {
  if (!waypoints || waypoints.length < 2) return { vel: [], acc: [], totalT: 0 };
  const total = waypoints[waypoints.length - 1].t;
  // sample TCP positions at dt
  const dt = total / (samples - 1);
  const positions = [];
  for (let i = 0; i < samples; i++) {
    const s = interpolateAtTime(waypoints, i * dt);
    positions.push(window.armTCP ? window.armTCP(s.joints) : s.tcp);
  }
  // velocity = finite diff
  const vel = [], acc = [];
  for (let i = 0; i < positions.length; i++) {
    const im = Math.max(0, i - 1), ip = Math.min(positions.length - 1, i + 1);
    const dx = positions[ip][0] - positions[im][0];
    const dy = positions[ip][1] - positions[im][1];
    const dz = positions[ip][2] - positions[im][2];
    const v = Math.sqrt(dx*dx + dy*dy + dz*dz) / ((ip - im) * dt);
    vel.push(v);
  }
  // acceleration = finite diff of velocity
  for (let i = 0; i < vel.length; i++) {
    const im = Math.max(0, i - 1), ip = Math.min(vel.length - 1, i + 1);
    const a = (vel[ip] - vel[im]) / ((ip - im) * dt);
    acc.push(Math.abs(a));
  }
  return { vel, acc, totalT: total, dt };
}

// ── EXAMPLE IMPORTED FILES ──────────────────────────────────────────────
const EXAMPLE_IMPORTS = [
  { path: "models/arm_ur5e.urdf",        type: "URDF", size: 28412, modified: "2026-05-22T09:11:00Z", author: "ENG·LIN" },
  { path: "models/gripper_2f.urdf",      type: "URDF", size:  9418, modified: "2026-05-22T09:14:00Z", author: "ENG·LIN" },
  { path: "models/cell_fixture.urdf",    type: "URDF", size: 14002, modified: "2026-05-23T11:42:00Z", author: "ENG·DAR" },
  { path: "cad/part_v4.step",            type: "STEP", size: 1894244, modified: "2026-05-20T16:08:00Z", author: "MECH·JI" },
  { path: "cad/fixture_jaws.stl",        type: "STL",  size: 412800, modified: "2026-05-21T10:30:00Z", author: "MECH·JI" },
  { path: "cad/bin_a7.stl",              type: "STL",  size:  84200, modified: "2026-05-19T08:14:00Z", author: "MECH·JI" },
  { path: "programs/pick_place.urpx",    type: "PROG", size:  4218, modified: "2026-05-26T05:48:00Z", author: "OP·KOSTA" },
  { path: "programs/weld_seam_v4.urpx",  type: "PROG", size:  8412, modified: "2026-05-25T14:22:00Z", author: "OP·KOSTA" },
  { path: "programs/inspect_qa.urpx",    type: "PROG", size:  6210, modified: "2026-05-24T13:09:00Z", author: "OP·DAR" },
  { path: "programs/calibrate_tcp.py",   type: "PY",   size:  3110, modified: "2026-05-20T12:00:00Z", author: "ENG·LIN" },
  { path: "trajectories/PICK-PLACE.json",type: "TRAJ", size: 12480, modified: "2026-05-26T06:11:48Z", author: "OP·KOSTA" },
  { path: "trajectories/WELD-SEAM-V4.json", type: "TRAJ", size: 24102, modified: "2026-05-25T14:24:00Z", author: "OP·KOSTA" },
  { path: "trajectories/STACKING_4x6.json", type: "TRAJ", size: 18244, modified: "2026-05-22T18:42:00Z", author: "OP·LIN" },
  { path: "waypoints/bin_locations.csv", type: "CSV",  size:   842, modified: "2026-05-18T11:00:00Z", author: "ENG·DAR" },
];

const EXAMPLE_PROGRAM = `# PICK-PLACE · BIN-A7 → KITTING-3
# Auto-generated from TRAJ-0142 · author OP·KOSTA
# Last modified 2026-05-26 06:11:48 UTC

DEF pick_place_a7():
    set_payload(1.8, [0, 0, 0.05])
    set_tcp(p[0, 0, 0.158, 0, 0, 0])

    # 1. Home
    movej([0, -1.57, 0, 0, 1.57, 0], a=1.0, v=1.05)

    # 2. Approach pick
    movej([-0.39, -1.19, 1.47, 0, 1.29, -0.39], a=1.2, v=1.4, r=0.02)

    # 3. Descend to pick
    movel(p[0.420, -0.180, 0.180, 3.14, 0, 0], a=0.6, v=0.3)

    # 4. Close gripper
    set_digital_out(0, True)
    sleep(0.2)

    # 5. Lift
    movel(p[0.420, -0.180, 0.450, 3.14, 0, 0], a=0.8, v=0.4, r=0.01)

    # 6. Transit
    movej([0.52, -1.32, 1.36, 0, 1.47, 0.52], a=1.5, v=2.0, r=0.03)

    # 7. Approach place
    movej([2.50, -1.19, 1.47, 0, 1.29, 2.50], a=1.2, v=1.4, r=0.02)

    # 8. Descend to place
    movel(p[-0.320, 0.240, 0.205, 3.14, 0, 0], a=0.6, v=0.3)

    # 9. Open gripper
    set_digital_out(0, False)
    sleep(0.15)

    # 10. Retreat
    movel(p[-0.320, 0.240, 0.500, 3.14, 0, 0], a=0.8, v=0.4, r=0.01)

    # 11. Return home
    movej([0, -1.57, 0, 0, 1.57, 0], a=1.0, v=1.05)
END
`;

Object.assign(window, {
  EXAMPLE_TRAJECTORY, EXAMPLE_IMPORTS, EXAMPLE_PROGRAM,
  interpolateAtTime, buildPathSamples, buildVelocityProfile,
});
