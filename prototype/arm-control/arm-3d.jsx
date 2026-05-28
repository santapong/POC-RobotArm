// arm-3d.jsx — Three.js 6-DOF robot arm viewer
// Renders a kinematic chain with orbit controls, grid floor, TCP triad,
// workspace sphere, joint highlights, and per-joint accent rings.

function buildArmMesh(tool) {
  const root = new THREE.Group();
  root.name = "ARM_ROOT";

  // material palette
  const matBase  = new THREE.MeshStandardMaterial({ color: 0x1a2028, metalness: 0.7, roughness: 0.45 });
  const matLink  = new THREE.MeshStandardMaterial({ color: 0x2a323b, metalness: 0.6, roughness: 0.5 });
  const matJoint = new THREE.MeshStandardMaterial({ color: 0x0d1117, metalness: 0.85, roughness: 0.3 });
  const matAccent = new THREE.MeshStandardMaterial({
    color: 0x4ade80, emissive: 0x4ade80, emissiveIntensity: 0.6, metalness: 0.4, roughness: 0.4,
  });
  const matTool  = new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.9, roughness: 0.25 });

  // helpers
  const cyl = (r1, r2, h, mat, segs=32) => new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, segs), mat);
  const box = (w, h, d, mat) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  const ring = (r, t, mat) => new THREE.Mesh(new THREE.TorusGeometry(r, t, 8, 32), mat);

  // ── BASE (anchored at world origin, sits on floor) ───────────────────────
  const base = new THREE.Group(); base.name = "BASE";
  const basePlate = cyl(0.20, 0.22, 0.04, matBase); basePlate.position.y = 0.02;
  const baseRing  = ring(0.18, 0.012, matAccent.clone()); baseRing.position.y = 0.045; baseRing.rotation.x = Math.PI/2;
  const baseCol   = cyl(0.13, 0.13, 0.18, matBase); baseCol.position.y = 0.13;
  base.add(basePlate, baseRing, baseCol);
  root.add(base);

  // ── J1 pivot (rotate around Y at top of base) ────────────────────────────
  const j1 = new THREE.Group(); j1.name = "J1";
  j1.position.y = 0.22;
  base.add(j1);

  const shoulderHead = cyl(0.14, 0.14, 0.13, matJoint, 24);
  shoulderHead.rotation.z = Math.PI/2;  // lay it sideways
  shoulderHead.position.y = 0.04;
  j1.add(shoulderHead);
  // shoulder accent rings on both faces
  for (const sgn of [-1, 1]) {
    const r = ring(0.13, 0.010, matAccent.clone());
    r.rotation.y = Math.PI/2; r.position.set(sgn * 0.065, 0.04, 0);
    j1.add(r);
  }

  // ── J2 pivot (shoulder — rotates around Z, perpendicular to upper arm) ──
  const j2 = new THREE.Group(); j2.name = "J2";
  j2.position.set(0, 0.04, 0);
  j1.add(j2);

  // upper arm — a tapered link extending along +X
  const upper = new THREE.Group();
  const armLen1 = 0.42;
  const upperLink = box(armLen1, 0.10, 0.10, matLink);
  upperLink.position.x = armLen1/2;
  upper.add(upperLink);
  // upper arm cable-track detail
  const cable = box(armLen1*0.96, 0.025, 0.03, matJoint);
  cable.position.set(armLen1/2, 0.062, 0);
  upper.add(cable);
  j2.add(upper);

  // ── J3 pivot (elbow at far end of upper arm) ─────────────────────────────
  const j3 = new THREE.Group(); j3.name = "J3";
  j3.position.x = armLen1;
  j2.add(j3);

  const elbowHead = cyl(0.085, 0.085, 0.13, matJoint, 24);
  elbowHead.rotation.x = Math.PI/2;
  j3.add(elbowHead);
  for (const sgn of [-1, 1]) {
    const r = ring(0.082, 0.008, matAccent.clone());
    r.position.set(0, 0, sgn * 0.065);
    j3.add(r);
  }

  // forearm
  const fore = new THREE.Group();
  const armLen2 = 0.34;
  const foreLink = box(armLen2, 0.08, 0.08, matLink);
  foreLink.position.x = armLen2/2;
  fore.add(foreLink);
  j3.add(fore);

  // ── J4 (wrist 1, rotates around X — wrist roll) ──────────────────────────
  const j4 = new THREE.Group(); j4.name = "J4";
  j4.position.x = armLen2;
  j3.add(j4);

  const wrist1 = cyl(0.055, 0.055, 0.10, matJoint, 24);
  wrist1.rotation.z = Math.PI/2;
  wrist1.position.x = 0.05;
  j4.add(wrist1);
  const wRing1 = ring(0.052, 0.007, matAccent.clone());
  wRing1.rotation.y = Math.PI/2;
  wRing1.position.x = 0.1;
  j4.add(wRing1);

  // ── J5 (wrist 2, rotates around Z) ───────────────────────────────────────
  const j5 = new THREE.Group(); j5.name = "J5";
  j5.position.x = 0.10;
  j4.add(j5);

  const wrist2 = cyl(0.050, 0.050, 0.09, matJoint, 24);
  wrist2.rotation.x = Math.PI/2;
  j5.add(wrist2);
  const wRing2 = ring(0.048, 0.007, matAccent.clone());
  wRing2.position.set(0, 0, 0.046);
  j5.add(wRing2);

  // ── J6 (wrist 3, final roll around X) ────────────────────────────────────
  const j6 = new THREE.Group(); j6.name = "J6";
  j6.position.x = 0.0;
  j6.position.z = 0.055;
  j6.rotation.x = Math.PI/2;
  j5.add(j6);

  const flange = cyl(0.045, 0.045, 0.025, matJoint, 24);
  flange.position.y = 0.0125;
  j6.add(flange);
  const flangeRing = ring(0.043, 0.006, matAccent.clone());
  flangeRing.rotation.x = Math.PI/2;
  flangeRing.position.y = 0.025;
  j6.add(flangeRing);

  // tool / gripper — swappable. tool === undefined → use the active tool from
  // the library (window.ACTIVE_TOOL), null → the default 2-finger gripper.
  if (tool === undefined) tool = (typeof window !== "undefined" ? window.ACTIVE_TOOL : null) || null;
  const built = buildToolMesh(tool);
  j6.add(built.group);
  j6.add(built.tcp);     // TCP group is a direct child of j6 (j6-local frame)
  const tcp = built.tcp;

  // collect joint refs for external angle control
  const joints = [j1, j2, j3, j4, j5, j6];
  // axes for each joint (which local axis to rotate)
  // J6 = "y" because the j6 group already has rotation.x = PI/2 to orient
  // the flange forward; rotating around Y spins the tool along its long axis
  // without clobbering that initial orientation.
  const axes = ["y", "z", "z", "x", "z", "y"];

  return { root, joints, axes, tcp, base, accentMats: [baseRing, ...joints.map(j => j.children.find(c => c.material === matAccent.clone()))] };
}

// Build the end-effector for a tool spec (see TOOL shape in arm-tooling.jsx).
// Returns { group, tcp }: `group` is the visual tool mounted on the flange,
// `tcp` is a frame group placed at the tool's TCP in j6-LOCAL coords (carrying
// the axis triad). tool == null reproduces the original 2-finger gripper, so
// every existing caller and the armTCP() FK baseline are unchanged.
function buildToolMesh(tool) {
  const matTool   = new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.9, roughness: 0.25 });
  const matMetal  = new THREE.MeshStandardMaterial({ color: 0x2a323b, metalness: 0.7, roughness: 0.4 });
  const matAccent = new THREE.MeshStandardMaterial({ color: 0x4ade80, emissive: 0x4ade80, emissiveIntensity: 0.6, metalness: 0.4, roughness: 0.4 });
  const matCopper = new THREE.MeshStandardMaterial({ color: 0xc77b3b, metalness: 0.8, roughness: 0.35 });
  const cyl = (r1, r2, h, mat, segs = 20) => new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, segs), mat);
  const box = (w, h, d, mat) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  const add = (grp, mesh, x, y, z) => { mesh.position.set(x, y, z); grp.add(mesh); return mesh; };

  const group = new THREE.Group(); group.name = "TOOL";
  const type = (tool && tool.type) || "GRIPPER_2F";
  const size = (tool && tool.size) || {};

  // mount: flange -> tool base (baseline sits the tool on the flange, +y up)
  const mOff = (tool && tool.mount && tool.mount.offset) || [0, 0, 0];
  const mRpy = (tool && tool.mount && tool.mount.rpy) || [0, 0, 0];
  group.position.set(mOff[0], 0.025 + mOff[1], mOff[2]);
  group.rotation.set(mRpy[0] * Math.PI / 180, mRpy[1] * Math.PI / 180, mRpy[2] * Math.PI / 180);

  let defTcp = [0, 0.13, 0];

  if (type === "GRIPPER_2F" || type === "GRIPPER_3F") {
    const stroke = size.stroke != null ? size.stroke : 0.056;
    const fingerLen = size.length != null ? size.length : 0.06;
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
    const dia = size.dia != null ? size.dia : 0.05;
    add(group, cyl(0.018, 0.018, 0.06, matMetal, 16), 0, 0.05, 0);
    add(group, cyl(dia / 2, dia / 2.6, 0.03, matTool, 20), 0, 0.095, 0);  // cup
    defTcp = [0, 0.12, 0];
  } else if (type === "MIG") {
    const len = size.length != null ? size.length : 0.16;
    const body = cyl(0.022, 0.022, len * 0.55, matTool, 16);
    body.position.set(0, 0.03 + len * 0.275, 0);
    body.rotation.z = -0.35;  // torch angled
    group.add(body);
    add(group, cyl(0.02, 0.008, 0.05, matCopper, 16), Math.sin(0.35) * len * 0.5, 0.03 + len * 0.62, 0); // nozzle
    add(group, cyl(0.0015, 0.0015, 0.03, matAccent, 8), Math.sin(0.35) * len * 0.5, 0.03 + len * 0.75, 0); // wire
    defTcp = [Math.sin(0.35) * len * 0.5, 0.03 + len * 0.8, 0];
  } else if (type === "SPINDLE") {
    const len = size.length != null ? size.length : 0.18;
    add(group, cyl(0.05, 0.03, len * 0.6, matMetal, 20), 0, 0.03 + len * 0.3, 0);   // body
    add(group, cyl(0.012, 0.012, len * 0.3, matTool, 16), 0, 0.03 + len * 0.6, 0);  // collet
    add(group, cyl(0.004, 0.004, len * 0.25, matAccent, 12), 0, 0.03 + len * 0.8, 0); // bit
    defTcp = [0, 0.03 + len * 0.95, 0];
  } else if (type === "DISPENSER") {
    const len = size.length != null ? size.length : 0.14;
    add(group, cyl(0.02, 0.02, len * 0.6, matTool, 16), 0, 0.03 + len * 0.3, 0);    // barrel
    add(group, cyl(0.008, 0.001, 0.04, matMetal, 12), 0, 0.03 + len * 0.7, 0);      // needle cone
    defTcp = [0, 0.03 + len * 0.85, 0];
  } else {
    add(group, cyl(0.035, 0.035, 0.05, matTool, 16), 0, 0.05, 0);
  }

  const off = (tool && tool.tcpOffset) || defTcp;
  const tcp = new THREE.Group(); tcp.name = "TCP";
  tcp.position.set(off[0], off[1], off[2]);
  const aL = 0.06;
  tcp.add(
    new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), aL, 0xef4444, 0.02, 0.012),
    new THREE.ArrowHelper(new THREE.Vector3(0, 1, 0), new THREE.Vector3(), aL, 0x4ade80, 0.02, 0.012),
    new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(), aL, 0x38bdf8, 0.02, 0.012),
  );
  return { group, tcp };
}

// Sign flip so positive joint angles match robotics convention (UR/KUKA):
// +J2 lifts the shoulder up, +J3 bends the elbow. Shared by every viewer so
// the rendered pose, the forward-kinematics TCP, and the path all agree.
const JOINT_SIGN = [1, -1, -1, 1, 1, 1];

// Apply 6 joint angles (radians) to an arm built by buildArmMesh(), using the
// same axis + sign convention as the animation loop. J6 keeps its baked
// rotation.x = π/2 (flange forward) because its driven axis is "y".
function applyJointAngles(arm, anglesRad) {
  for (let i = 0; i < 6; i++) {
    const joint = arm.joints[i];
    const axis = arm.axes[i];
    const v = (anglesRad[i] || 0) * JOINT_SIGN[i];
    if (axis === "x") joint.rotation.x = v;
    else if (axis === "y") joint.rotation.y = v;
    else joint.rotation.z = v;
  }
}

// Forward kinematics: world-space TCP position for a set of joint angles
// (degrees). Uses a cached off-screen arm so the path, waypoint markers, and
// playback marker are all derived from the SAME geometry the user sees — which
// guarantees the tool actually sits on the path it's following.
let _fkArm = null;
function armTCP(jointAnglesDeg) {
  if (typeof THREE === "undefined") return (jointAnglesDeg || [0, 0, 0]).slice(0, 3);
  if (!_fkArm) _fkArm = buildArmMesh((typeof window !== "undefined" ? window.ACTIVE_TOOL : null) || null);
  const rad = (jointAnglesDeg || [0, -60, 90, 0, 40, 0]).map(d => d * Math.PI / 180);
  applyJointAngles(_fkArm, rad);
  _fkArm.root.updateMatrixWorld(true);
  const v = new THREE.Vector3();
  _fkArm.tcp.getWorldPosition(v);
  return [v.x, v.y, v.z];
}

// Set the active end-effector. Stored on window so every buildArmMesh() with no
// explicit tool (and the FK arm) picks it up; resets the cached FK arm so armTCP
// recomputes against the new tool's TCP. Viewers remount (React key) to rebuild.
function setActiveTool(tool) {
  if (typeof window !== "undefined") window.ACTIVE_TOOL = tool || null;
  _fkArm = null;
}

function Arm3D({ jointAngles, faulty = [], showWorkspace = true, showGrid = true, reach = 1.0, width = 600, height = 400, autoRotate = false, pathPoints = null, waypoints = null, markerRef = null, selectedWaypoint = null, tool }) {
  const mountRef = React.useRef(null);
  const stateRef = React.useRef({});

  React.useEffect(() => {
    if (!mountRef.current || !window.THREE) return;
    const mount = mountRef.current;
    const W = mount.clientWidth || width;
    const H = mount.clientHeight || height;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x05080c);
    scene.fog = new THREE.Fog(0x05080c, 4, 9);

    const camera = new THREE.PerspectiveCamera(40, W / H, 0.05, 50);
    camera.position.set(1.6, 1.3, 1.9);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = false;
    mount.appendChild(renderer.domElement);

    // lights
    scene.add(new THREE.AmbientLight(0x6080a0, 0.45));
    const sun = new THREE.DirectionalLight(0xfff5e0, 0.7);
    sun.position.set(3, 6, 2);
    scene.add(sun);
    const fillCy = new THREE.PointLight(0x38bdf8, 1.2, 6);
    fillCy.position.set(-2, 1.5, -1.5);
    scene.add(fillCy);
    const fillGn = new THREE.PointLight(0x4ade80, 0.6, 4);
    fillGn.position.set(1.2, 0.4, 1.8);
    scene.add(fillGn);

    // grid floor + base disc
    if (showGrid) {
      const grid = new THREE.GridHelper(6, 24, 0x4ade80, 0x1c2a32);
      grid.position.y = 0;
      const mats = Array.isArray(grid.material) ? grid.material : [grid.material];
      mats.forEach(m => { m.opacity = 0.42; m.transparent = true; });
      scene.add(grid);
    }
    // floor accent (subtle reflective disc)
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(2.4, 48),
      new THREE.MeshStandardMaterial({ color: 0x070b10, metalness: 0.4, roughness: 0.7 })
    );
    floor.rotation.x = -Math.PI/2;
    floor.position.y = -0.001;
    scene.add(floor);

    // world axes triad (bottom-left)
    const triad = new THREE.Group();
    triad.add(
      new THREE.ArrowHelper(new THREE.Vector3(1,0,0), new THREE.Vector3(), 0.25, 0xef4444, 0.06, 0.04),
      new THREE.ArrowHelper(new THREE.Vector3(0,1,0), new THREE.Vector3(), 0.25, 0x4ade80, 0.06, 0.04),
      new THREE.ArrowHelper(new THREE.Vector3(0,0,1), new THREE.Vector3(), 0.25, 0x38bdf8, 0.06, 0.04),
    );
    triad.position.set(-1.3, 0.01, 1.3);
    scene.add(triad);

    // workspace sphere
    let ws = null;
    if (showWorkspace) {
      ws = new THREE.Mesh(
        new THREE.SphereGeometry(reach, 24, 16, 0, Math.PI*2, 0, Math.PI/2 + 0.2),
        new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true, opacity: 0.07, transparent: true })
      );
      ws.position.y = 0.22;
      scene.add(ws);
    }

    // the arm (tool prop overrides the global active tool when provided)
    const armBuilt = buildArmMesh(tool);
    scene.add(armBuilt.root);

    // pose markers (target ghost) — a translucent flag at the goal pose
    const goalMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.025, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0xe879f9, transparent: true, opacity: 0.85 })
    );
    goalMarker.position.set(0.45, 0.55, 0.2);
    scene.add(goalMarker);
    const goalRing = new THREE.Mesh(
      new THREE.RingGeometry(0.035, 0.05, 24),
      new THREE.MeshBasicMaterial({ color: 0xe879f9, transparent: true, opacity: 0.55, side: THREE.DoubleSide })
    );
    goalRing.position.copy(goalMarker.position);
    goalRing.rotation.x = -Math.PI/2;
    scene.add(goalRing);

    // orbit controls
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(0.1, 0.55, 0);
    controls.minDistance = 0.6;
    controls.maxDistance = 6;
    controls.maxPolarAngle = Math.PI/2 - 0.02;
    controls.autoRotate = !!autoRotate;
    controls.autoRotateSpeed = 0.4;

    stateRef.current = {
      scene, camera, renderer, controls, arm: armBuilt,
      target: (jointAngles || [0,-60,90,0,40,0]).map(d => d * Math.PI/180),
      current: (jointAngles || [0,-60,90,0,40,0]).map(d => d * Math.PI/180),
      faulty: new Set(faulty),
      goalMarker, goalRing,
      tcpWorld: new THREE.Vector3(),
      raf: null, alive: true,
    };

    // ── PATH rendering objects (rebuilt when props change) ──
    const pathGroup = new THREE.Group(); pathGroup.name = "PATH"; scene.add(pathGroup);
    const wpGroup   = new THREE.Group(); wpGroup.name   = "WAYPOINTS"; scene.add(wpGroup);

    // moving playback marker (driven by ref each frame)
    const playMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.026, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.95 })
    );
    const playMarkerHalo = new THREE.Mesh(
      new THREE.SphereGeometry(0.045, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.18 })
    );
    playMarker.visible = false;
    playMarkerHalo.visible = false;
    scene.add(playMarker, playMarkerHalo);

    function rebuildPath(pts, wps, selIdx) {
      // clear
      while (pathGroup.children.length) {
        const c = pathGroup.children[0];
        pathGroup.remove(c);
        if (c.geometry) c.geometry.dispose();
        if (c.material) c.material.dispose();
      }
      while (wpGroup.children.length) {
        const c = wpGroup.children[0];
        wpGroup.remove(c);
        if (c.geometry) c.geometry.dispose();
        if (c.material) c.material.dispose();
      }

      if (pts && pts.length >= 2) {
        // glowing core path
        const geom = new THREE.BufferGeometry();
        const arr = new Float32Array(pts.length * 3);
        for (let i = 0; i < pts.length; i++) {
          arr[i*3] = pts[i][0]; arr[i*3+1] = pts[i][1]; arr[i*3+2] = pts[i][2];
        }
        geom.setAttribute("position", new THREE.BufferAttribute(arr, 3));
        const matCore = new THREE.LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.9 });
        pathGroup.add(new THREE.Line(geom, matCore));
        const matGlow = new THREE.LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.25, linewidth: 3 });
        pathGroup.add(new THREE.Line(geom.clone(), matGlow));

        // floor shadow projection (z onto y=0)
        const shadowArr = new Float32Array(pts.length * 3);
        for (let i = 0; i < pts.length; i++) {
          shadowArr[i*3] = pts[i][0]; shadowArr[i*3+1] = 0.001; shadowArr[i*3+2] = pts[i][2];
        }
        const shadowGeom = new THREE.BufferGeometry();
        shadowGeom.setAttribute("position", new THREE.BufferAttribute(shadowArr, 3));
        pathGroup.add(new THREE.Line(shadowGeom, new THREE.LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.18 })));
      }

      if (wps && wps.length) {
        wps.forEach((wp, i) => {
          const isLin = wp.type === "MoveL";
          const isSel = (selIdx !== null && selIdx === i);
          const baseColor = isLin ? 0x38bdf8 : 0xfbbf24;
          const c = isSel ? 0xe879f9 : baseColor;
          const r = isSel ? 0.030 : 0.022;
          // place the marker where the tool actually is for this pose (FK),
          // not at the stored TCP, so spheres line up with the arm + path
          const p = armTCP(wp.joints);
          const sphere = new THREE.Mesh(
            new THREE.SphereGeometry(r, 18, 18),
            new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: 0.95 })
          );
          sphere.position.set(p[0], p[1], p[2]);
          wpGroup.add(sphere);
          // glow ring on floor
          const ring = new THREE.Mesh(
            new THREE.RingGeometry(0.030, 0.045, 24),
            new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: 0.45, side: THREE.DoubleSide })
          );
          ring.position.set(p[0], 0.002, p[2]);
          ring.rotation.x = -Math.PI / 2;
          wpGroup.add(ring);
          // dashed drop line to floor
          const dropGeom = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(p[0], p[1], p[2]),
            new THREE.Vector3(p[0], 0, p[2]),
          ]);
          const dropMat = new THREE.LineDashedMaterial({ color: c, dashSize: 0.02, gapSize: 0.02, transparent: true, opacity: 0.35 });
          const drop = new THREE.Line(dropGeom, dropMat); drop.computeLineDistances();
          wpGroup.add(drop);
          // selection rings
          if (isSel) {
            const halo = new THREE.Mesh(
              new THREE.RingGeometry(0.055, 0.07, 32),
              new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: 0.55, side: THREE.DoubleSide })
            );
            halo.position.set(p[0], p[1], p[2]);
            halo.lookAt(camera.position);
            wpGroup.add(halo);
          }
        });
      }

      playMarker.visible = !!pts && pts.length > 0;
      playMarkerHalo.visible = playMarker.visible;
    }
    stateRef.current.rebuildPath = rebuildPath;
    stateRef.current.playMarker = playMarker;
    stateRef.current.playMarkerHalo = playMarkerHalo;
    rebuildPath(pathPoints, waypoints, selectedWaypoint);

    // resize observer
    const ro = new ResizeObserver(() => {
      const w = mount.clientWidth, h = mount.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    ro.observe(mount);

    const animate = () => {
      const s = stateRef.current;
      if (!s.alive) return;
      s.raf = requestAnimationFrame(animate);

      // lerp current joint angles toward target, then pose the arm with the
      // shared sign/axis convention (so rendered pose matches armTCP() FK)
      for (let i = 0; i < 6; i++) {
        s.current[i] += (s.target[i] - s.current[i]) * 0.08;
      }
      applyJointAngles(s.arm, s.current);

      // pulse goal marker
      const t = performance.now() / 600;
      s.goalRing.scale.setScalar(1 + 0.15 * Math.sin(t));
      s.goalMarker.material.opacity = 0.7 + 0.25 * Math.sin(t);

      // playback marker — pin it to the arm's ACTUAL tool tip so the marker
      // (and therefore the tool) is always exactly on the path it follows
      if (s.playMarker.visible) {
        s.arm.tcp.getWorldPosition(s.tcpWorld);
        s.playMarker.position.copy(s.tcpWorld);
        s.playMarkerHalo.position.copy(s.tcpWorld);
        const ph = 1 + 0.2 * Math.sin(performance.now() / 220);
        s.playMarkerHalo.scale.setScalar(ph);
      }

      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      const s = stateRef.current;
      s.alive = false;
      cancelAnimationFrame(s.raf);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
      scene.traverse(o => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) {
          if (Array.isArray(o.material)) o.material.forEach(m => m.dispose());
          else o.material.dispose();
        }
      });
    };
  }, []);

  // update target angles when prop changes
  React.useEffect(() => {
    const s = stateRef.current;
    if (!s.target || !jointAngles) return;
    s.target = jointAngles.map(d => d * Math.PI/180);
    s.faulty = new Set(faulty);
  }, [jointAngles, faulty]);

  // rebuild path / waypoints when props change
  React.useEffect(() => {
    const s = stateRef.current;
    if (s.rebuildPath) s.rebuildPath(pathPoints, waypoints, selectedWaypoint);
  }, [pathPoints, waypoints, selectedWaypoint]);

  React.useEffect(() => {
    const s = stateRef.current;
    if (s.controls) s.controls.autoRotate = !!autoRotate;
  }, [autoRotate]);

  return <div ref={mountRef} style={{ width: width === "100%" ? "100%" : width, height, position: "relative", overflow: "hidden" }} />;
}

// 2D side-view SVG of the arm (used in robot detail when 3D isn't needed)
function ArmSideView({ width = 320, height = 280, jointAngles, faulty = [] }) {
  // Project to 2D side view: take j2, j3 angles for shoulder/elbow.
  // Simplified planar representation.
  const j2 = (jointAngles[1] || -60) * Math.PI/180;
  const j3 = (jointAngles[2] || 90)  * Math.PI/180;
  const j5 = (jointAngles[4] || 40)  * Math.PI/180;

  const cx = width / 2 - 30, cy = height - 50;
  const L1 = 90, L2 = 75, L3 = 36;
  const sh = [cx, cy - 36];
  const el = [sh[0] + Math.cos(j2) * L1, sh[1] + Math.sin(j2) * L1];
  const wr = [el[0] + Math.cos(j2 + j3) * L2, el[1] + Math.sin(j2 + j3) * L2];
  const tcp = [wr[0] + Math.cos(j2 + j3 + j5) * L3, wr[1] + Math.sin(j2 + j3 + j5) * L3];

  const isFault = (i) => faulty.includes(i);
  const color = (i) => isFault(i) ? "var(--err)" : "var(--ok)";

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <defs>
        <pattern id="ag1" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(120,180,200,.07)" strokeWidth="1"/>
        </pattern>
      </defs>
      <rect width={width} height={height} fill="url(#ag1)" />
      {/* floor */}
      <line x1="0" y1={cy} x2={width} y2={cy} stroke="rgba(74,222,128,.4)" strokeDasharray="4 3" strokeWidth="1" />
      <text x="6" y={cy - 4} fill="rgba(74,222,128,.6)" fontSize="9" fontFamily="JetBrains Mono">FLOOR · z=0</text>
      {/* base */}
      <rect x={cx - 16} y={cy - 8} width="32" height="8" fill="#1a2028" stroke="var(--border-2)" />
      <rect x={cx - 22} y={cy - 28} width="44" height="20" fill="#1a2028" stroke="var(--border-2)" />
      <circle cx={cx} cy={cy - 36} r="9" fill="#0d1117" stroke={color(0)} strokeWidth="1.5" />
      <text x={cx + 14} y={cy - 32} fill={color(0)} fontSize="9" fontFamily="JetBrains Mono">J1</text>
      {/* upper arm */}
      <line x1={sh[0]} y1={sh[1]} x2={el[0]} y2={el[1]} stroke={color(1)} strokeWidth="6" strokeLinecap="round" opacity="0.75" />
      <line x1={sh[0]} y1={sh[1]} x2={el[0]} y2={el[1]} stroke={color(1)} strokeWidth="2" />
      <circle cx={el[0]} cy={el[1]} r="7" fill="#0d1117" stroke={color(2)} strokeWidth="1.5" />
      <text x={sh[0] + 8} y={sh[1] - 6} fill={color(1)} fontSize="9" fontFamily="JetBrains Mono">J2</text>
      <text x={el[0] + 10} y={el[1]} fill={color(2)} fontSize="9" fontFamily="JetBrains Mono">J3</text>
      {/* forearm */}
      <line x1={el[0]} y1={el[1]} x2={wr[0]} y2={wr[1]} stroke={color(3)} strokeWidth="5" strokeLinecap="round" opacity="0.75" />
      <line x1={el[0]} y1={el[1]} x2={wr[0]} y2={wr[1]} stroke={color(3)} strokeWidth="2" />
      <circle cx={wr[0]} cy={wr[1]} r="5" fill="#0d1117" stroke={color(4)} strokeWidth="1.5" />
      <text x={wr[0] + 8} y={wr[1] + 3} fill={color(4)} fontSize="9" fontFamily="JetBrains Mono">J4/5</text>
      {/* tool */}
      <line x1={wr[0]} y1={wr[1]} x2={tcp[0]} y2={tcp[1]} stroke={color(5)} strokeWidth="3" />
      <circle cx={tcp[0]} cy={tcp[1]} r="4" fill="var(--magenta)" stroke="#06090d" strokeWidth="1.5" />
      <text x={tcp[0] + 6} y={tcp[1] - 4} fill="var(--magenta)" fontSize="9" fontFamily="JetBrains Mono">TCP</text>

      {/* labels */}
      <text x="6" y="14" fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">VIEW · SIDE · base_link</text>
      <text x={width - 6} y="14" textAnchor="end" fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">6 DoF · UR-LIKE</text>
      <text x="6" y={height - 6} fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">SCALE 1:4</text>
    </svg>
  );
}

Object.assign(window, { buildArmMesh, buildToolMesh, setActiveTool, Arm3D, ArmSideView, armTCP, applyJointAngles, JOINT_SIGN });
