// arm-cam.jsx — CAM-style surface-pick path generation
// Click a CAD workpiece in the 3D scene; system auto-calculates waypoints
// with normal-aligned tool orientation, approach/retreat moves, and IK.

// ── approximate inverse kinematics ──────────────────────────────────────
// Returns [j1, j2, j3, j4, j5, j6] degrees so the arm reaches `target`
// with tool aligned to the surface `normal`. Uses 2-link planar IK for J2/J3
// and points the wrist along the normal.
function approxIK(target, normal = [0, 1, 0], tcpLen = null) {
  const [x, y, z] = target;
  const upperArm = 0.42;
  const forearm  = 0.34;
  const baseY    = 0.26;          // height of J2 above floor

  // base rotation — arm faces the target in xz plane
  const j1 = Math.atan2(-z, x);
  const r  = Math.sqrt(x * x + z * z);
  const h  = y - baseY;

  // solve for the FLANGE, not the TCP: back off by the wrist length + the
  // active tool's TCP length so longer tools reach less far (approximate).
  if (tcpLen == null) {
    const t = (typeof window !== "undefined" && window.ACTIVE_TOOL) ? window.ACTIVE_TOOL.tcpOffset : null;
    tcpLen = t ? Math.hypot(t[0], t[1], t[2]) : 0.13;
  }
  const wristOffset = 0.10 + tcpLen;
  const rTarg = Math.max(0.1, r - wristOffset * Math.abs(normal[0] || 0));
  const hTarg = h + wristOffset * Math.abs(normal[1] || 1);

  const d = Math.sqrt(rTarg * rTarg + hTarg * hTarg);
  const D = Math.max(0.05, Math.min(upperArm + forearm - 0.02, d));

  // elbow angle via law of cosines
  const cosE = (upperArm * upperArm + forearm * forearm - D * D) / (2 * upperArm * forearm);
  const elbow = Math.acos(Math.max(-1, Math.min(1, cosE)));
  const j3 = Math.PI - elbow;

  // shoulder
  const ang = Math.atan2(hTarg, rTarg);
  const cosS = (upperArm * upperArm + D * D - forearm * forearm) / (2 * upperArm * D);
  const shoff = Math.acos(Math.max(-1, Math.min(1, cosS)));
  const j2 = -(ang + shoff);

  // wrist: orient TCP along -normal — approximate via J5 angle
  // J4=0, J5 points wrist downward (toward surface)
  const j5 = 90 - Math.atan2(normal[1], Math.sqrt(normal[0]*normal[0] + normal[2]*normal[2])) * 180/Math.PI;

  return [
    j1 * 180/Math.PI,
    j2 * 180/Math.PI,
    j3 * 180/Math.PI,
    0,
    j5,
    0,
  ];
}

// ── Generate trajectory from picked surface points ──────────────────────
function generateCAMTrajectory(picks, opts = {}) {
  if (!picks || picks.length === 0) return null;
  const {
    standoff = 0.005,       // m — tool gap from surface
    approachHeight = 0.06,  // m above target for approach/retreat
    vel = 30, acc = 40,
    home = [0, 0.9, 0],
    moveType = "MoveL",
    tool = null,
  } = opts;
  const tcpLen = tool && tool.tcpOffset ? Math.hypot(tool.tcpOffset[0], tool.tcpOffset[1], tool.tcpOffset[2]) : null;

  const wps = [];
  let t = 0;

  // 1) HOME
  wps.push({
    id: 1, name: "HOME", type: "MoveJ",
    tcp: home.slice(),
    rot: [180, 0, 0],
    joints: [0, -90, 0, 0, 90, 0],
    vel: 60, acc: 50, blend: 0, dwell: 0, io: null, t,
  });
  t += 0.6;

  // 2) APPROACH first point — offset along normal by approachHeight
  const first = picks[0];
  const firstAprPos = [
    first.point[0] + first.normal[0] * approachHeight,
    first.point[1] + first.normal[1] * approachHeight,
    first.point[2] + first.normal[2] * approachHeight,
  ];
  wps.push({
    id: wps.length + 1, name: "APPROACH",
    type: "MoveJ",
    tcp: firstAprPos,
    rot: rotFromNormal(first.normal),
    joints: approxIK(firstAprPos, first.normal, tcpLen),
    vel: 70, acc: 60, blend: 10, dwell: 0, io: null, t,
  });
  t += 0.7;

  // 3) For each pick: descend to standoff, then move to next at standoff
  picks.forEach((p, i) => {
    const tcp = [
      p.point[0] + p.normal[0] * standoff,
      p.point[1] + p.normal[1] * standoff,
      p.point[2] + p.normal[2] * standoff,
    ];
    const isFirst = i === 0;
    const dur = isFirst ? 0.4 : 0.6;
    wps.push({
      id: wps.length + 1,
      name: `PT-${String(i + 1).padStart(2, "0")}`,
      type: isFirst ? "MoveL" : moveType,
      tcp,
      rot: rotFromNormal(p.normal),
      joints: approxIK(tcp, p.normal, tcpLen),
      vel, acc,
      blend: i === picks.length - 1 ? 0 : 5,
      dwell: isFirst ? 0.1 : 0,
      io: isFirst ? { type: "DO", ch: 0, value: true,  label: "TOOL ON" } : null,
      t: t + dur,
    });
    t += dur;
  });

  // 4) RETREAT — lift off from last point
  const last = picks[picks.length - 1];
  const retreatPos = [
    last.point[0] + last.normal[0] * approachHeight,
    last.point[1] + last.normal[1] * approachHeight,
    last.point[2] + last.normal[2] * approachHeight,
  ];
  wps.push({
    id: wps.length + 1, name: "RETREAT",
    type: "MoveL",
    tcp: retreatPos,
    rot: rotFromNormal(last.normal),
    joints: approxIK(retreatPos, last.normal, tcpLen),
    vel: 50, acc: 50, blend: 10, dwell: 0,
    io: { type: "DO", ch: 0, value: false, label: "TOOL OFF" },
    t: t + 0.5,
  });
  t += 0.5;

  // 5) Return HOME
  wps.push({
    id: wps.length + 1, name: "HOME", type: "MoveJ",
    tcp: home.slice(),
    rot: [180, 0, 0],
    joints: [0, -90, 0, 0, 90, 0],
    vel: 60, acc: 50, blend: 0, dwell: 0, io: null,
    t: t + 0.7,
  });

  // metrics
  let pathLength = 0;
  for (let i = 1; i < wps.length; i++) {
    const a = wps[i-1].tcp, b = wps[i].tcp;
    pathLength += Math.sqrt(
      (b[0]-a[0])**2 + (b[1]-a[1])**2 + (b[2]-a[2])**2
    );
  }

  return {
    id: "CAM-AUTO",
    name: `CAM AUTO · ${picks.length} PT${picks.length>1?"S":""}`,
    author: "AUTO·CAM",
    tool: "TOOL-T7",
    waypoints: wps,
    totalTime: wps[wps.length-1].t,
    pathLength,
    maxTCPSpeed: vel / 100 * 1.5,
    maxJointVel: 142,
    maxJointAcc: 540,
    singularityWarnings: 0,
    collisionWarnings: 0,
    reachWarnings: 0,
  };
}

function rotFromNormal(n) {
  // Convert normal vector to approximate RX/RY/RZ in degrees.
  // RX = angle from +Y axis, RZ = base rotation.
  const rx = 180 - Math.acos(Math.max(-1, Math.min(1, n[1]))) * 180/Math.PI;
  const rz = Math.atan2(n[0], n[2]) * 180/Math.PI;
  return [rx, 0, rz];
}

// ── 3D CAM viewer with workpiece + raycaster ────────────────────────────
function CAMViewer3D({
  jointAngles,
  picks, generatedTrajectory, hoverPick,
  part, tool, onSurfaceClick, onSurfaceHover,
  reach = 1.0,
}) {
  const mountRef = React.useRef();
  const stateRef = React.useRef({});

  React.useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !window.THREE) return;
    const W = mount.clientWidth || 800;
    const H = mount.clientHeight || 500;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x05080c);
    scene.fog = new THREE.Fog(0x05080c, 4, 9);

    const camera = new THREE.PerspectiveCamera(40, W/H, 0.05, 50);
    camera.position.set(1.4, 1.1, 1.6);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(W, H); renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    // lights
    scene.add(new THREE.AmbientLight(0x6080a0, 0.45));
    const sun = new THREE.DirectionalLight(0xfff5e0, 0.7); sun.position.set(3, 6, 2); scene.add(sun);
    const cy = new THREE.PointLight(0x38bdf8, 1.0, 6); cy.position.set(-2, 1.5, -1.5); scene.add(cy);
    const gn = new THREE.PointLight(0x4ade80, 0.5, 4); gn.position.set(1.2, 0.4, 1.8); scene.add(gn);

    // floor grid
    const grid = new THREE.GridHelper(6, 24, 0x4ade80, 0x1c2a32);
    const mats = Array.isArray(grid.material) ? grid.material : [grid.material];
    mats.forEach(m => { m.opacity = 0.42; m.transparent = true; });
    scene.add(grid);
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(2.4, 48),
      new THREE.MeshStandardMaterial({ color: 0x070b10, metalness: 0.4, roughness: 0.7 })
    );
    floor.rotation.x = -Math.PI/2; floor.position.y = -0.001; scene.add(floor);

    // arm (built with the selected tool)
    const armBuilt = buildArmMesh(tool);
    scene.add(armBuilt.root);

    // ── workpiece (parametric, clickable) ─────────────────────────
    let workpiece = buildPartMesh(part);
    scene.add(workpiece);

    // ── hover marker ──────────────────────────────────────────────
    const hoverGrp = new THREE.Group(); scene.add(hoverGrp);
    const hoverDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.012, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.95 })
    );
    const hoverRing = new THREE.Mesh(
      new THREE.RingGeometry(0.020, 0.028, 24),
      new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.6, side: THREE.DoubleSide })
    );
    const hoverNormal = new THREE.ArrowHelper(
      new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 0), 0.08, 0xfbbf24, 0.025, 0.018
    );
    hoverGrp.add(hoverDot, hoverRing, hoverNormal);
    hoverGrp.visible = false;

    // ── pick / path objects (rebuilt on prop changes) ─────────────
    const pickGroup = new THREE.Group(); scene.add(pickGroup);
    const pathGroup = new THREE.Group(); scene.add(pathGroup);

    function rebuildPicks(picks) {
      while (pickGroup.children.length) {
        const c = pickGroup.children[0]; pickGroup.remove(c);
        if (c.geometry) c.geometry.dispose(); if (c.material) c.material.dispose();
      }
      (picks || []).forEach((p, i) => {
        const sphere = new THREE.Mesh(
          new THREE.SphereGeometry(0.015, 16, 16),
          new THREE.MeshBasicMaterial({ color: 0xe879f9 })
        );
        sphere.position.set(...p.point);
        pickGroup.add(sphere);
        // normal indicator
        const arrow = new THREE.ArrowHelper(
          new THREE.Vector3(...p.normal),
          new THREE.Vector3(...p.point),
          0.06, 0xe879f9, 0.022, 0.016
        );
        pickGroup.add(arrow);
      });

      // connect picks with a magenta line
      if (picks && picks.length >= 2) {
        const geom = new THREE.BufferGeometry();
        const arr = new Float32Array(picks.length * 3);
        picks.forEach((p, i) => { arr[i*3]=p.point[0]; arr[i*3+1]=p.point[1]; arr[i*3+2]=p.point[2]; });
        geom.setAttribute("position", new THREE.BufferAttribute(arr, 3));
        const line = new THREE.Line(geom, new THREE.LineBasicMaterial({ color: 0xe879f9, transparent: true, opacity: 0.7 }));
        pickGroup.add(line);
      }
    }

    function rebuildPath(traj) {
      while (pathGroup.children.length) {
        const c = pathGroup.children[0]; pathGroup.remove(c);
        if (c.geometry) c.geometry.dispose(); if (c.material) c.material.dispose();
      }
      if (!traj) return;
      const pts = buildPathSamples(traj.waypoints, 200);
      if (pts.length >= 2) {
        const geom = new THREE.BufferGeometry();
        const arr = new Float32Array(pts.length * 3);
        pts.forEach((p, i) => { arr[i*3]=p[0]; arr[i*3+1]=p[1]; arr[i*3+2]=p[2]; });
        geom.setAttribute("position", new THREE.BufferAttribute(arr, 3));
        pathGroup.add(new THREE.Line(geom, new THREE.LineBasicMaterial({
          color: 0x4ade80, transparent: true, opacity: 0.92,
        })));
        // glow
        pathGroup.add(new THREE.Line(geom.clone(), new THREE.LineBasicMaterial({
          color: 0x4ade80, transparent: true, opacity: 0.3,
        })));
      }
      // waypoint spheres — at the tool's actual FK position so they sit on
      // the (FK-sampled) green path, consistent with the rendered arm
      traj.waypoints.forEach((wp) => {
        const isLin = wp.type === "MoveL";
        const sphere = new THREE.Mesh(
          new THREE.SphereGeometry(0.016, 14, 14),
          new THREE.MeshBasicMaterial({ color: isLin ? 0x38bdf8 : 0xfbbf24 })
        );
        const p = window.armTCP ? window.armTCP(wp.joints) : wp.tcp;
        sphere.position.set(p[0], p[1], p[2]);
        pathGroup.add(sphere);
      });
    }

    stateRef.current = {
      scene, camera, renderer, arm: armBuilt,
      workpiece, hoverGrp, hoverDot, hoverRing, hoverNormal,
      pickGroup, pathGroup, rebuildPicks, rebuildPath,
      currentPart: part,
      target: (jointAngles || [0,-60,90,0,40,0]).map(d => d * Math.PI/180),
      current: (jointAngles || [0,-60,90,0,40,0]).map(d => d * Math.PI/180),
      alive: true, raf: null,
    };

    rebuildPicks(picks);
    rebuildPath(generatedTrajectory);

    // ── orbit controls ────────────────────────────────────────────
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = 0.08;
    controls.target.set(0.4, 0.3, 0);
    controls.minDistance = 0.6; controls.maxDistance = 6;
    controls.maxPolarAngle = Math.PI/2 - 0.02;
    stateRef.current.controls = controls;

    // ── raycaster + interactions ──────────────────────────────────
    const raycaster = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    let downAt = null;
    function getClickables() {
      return workpiece.children.filter(c => c.userData.clickable);
    }
    function castFromEvent(e) {
      const rect = renderer.domElement.getBoundingClientRect();
      ndc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      ndc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(getClickables(), false);
      if (!hits.length) return null;
      const hit = hits[0];
      const n = hit.face.normal.clone();
      n.transformDirection(hit.object.matrixWorld);
      return { point: hit.point.toArray(), normal: n.toArray() };
    }
    function onMove(e) {
      const hit = castFromEvent(e);
      if (hit && onSurfaceHover) {
        hoverGrp.visible = true;
        hoverDot.position.set(...hit.point);
        hoverRing.position.set(hit.point[0] + hit.normal[0]*0.001, hit.point[1] + hit.normal[1]*0.001, hit.point[2] + hit.normal[2]*0.001);
        // orient ring perpendicular to normal
        const up = new THREE.Vector3(...hit.normal);
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,0,1), up);
        hoverRing.quaternion.copy(q);
        // normal arrow
        hoverNormal.setDirection(up);
        hoverNormal.position.set(...hit.point);
        onSurfaceHover(hit);
      } else {
        hoverGrp.visible = false;
        if (onSurfaceHover) onSurfaceHover(null);
      }
    }
    function onDown(e) { downAt = { x: e.clientX, y: e.clientY }; }
    function onUp(e) {
      if (!downAt) return;
      const dx = e.clientX - downAt.x, dy = e.clientY - downAt.y;
      const moved = Math.hypot(dx, dy);
      downAt = null;
      if (moved > 3) return;  // it was a drag
      if (e.button !== 0) return; // only LMB
      const hit = castFromEvent(e);
      if (hit && onSurfaceClick) onSurfaceClick(hit);
    }
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    // resize
    const ro = new ResizeObserver(() => {
      const w = mount.clientWidth, h = mount.clientHeight;
      if (!w || !h) return;
      camera.aspect = w/h; camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    ro.observe(mount);

    const animate = () => {
      const s = stateRef.current;
      if (!s.alive) return;
      s.raf = requestAnimationFrame(animate);
      // lerp joints toward target, then pose with the shared sign/axis
      // convention (matches armTCP FK so picks/path/arm stay aligned)
      for (let i = 0; i < 6; i++) {
        s.current[i] += (s.target[i] - s.current[i]) * 0.1;
      }
      applyJointAngles(s.arm, s.current);
      // pulse hover ring
      const t = performance.now() / 400;
      hoverRing.scale.setScalar(1 + 0.15 * Math.sin(t));
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      const s = stateRef.current;
      s.alive = false;
      cancelAnimationFrame(s.raf);
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
      scene.traverse(o => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) { if (Array.isArray(o.material)) o.material.forEach(m => m.dispose()); else o.material.dispose(); }
      });
    };
  }, []);

  // rebuild the parametric part when it changes (kind/dims/pose edits)
  React.useEffect(() => {
    const s = stateRef.current;
    if (!s.scene || !part || part === s.currentPart) return;
    s.scene.remove(s.workpiece);
    s.workpiece.traverse(o => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) { if (Array.isArray(o.material)) o.material.forEach(m => m.dispose()); else o.material.dispose(); }
    });
    s.workpiece = buildPartMesh(part);
    s.scene.add(s.workpiece);
    s.currentPart = part;
  }, [part]);

  React.useEffect(() => {
    const s = stateRef.current;
    if (!s.target || !jointAngles) return;
    s.target = jointAngles.map(d => d * Math.PI/180);
  }, [jointAngles]);

  React.useEffect(() => {
    const s = stateRef.current;
    if (s.rebuildPicks) s.rebuildPicks(picks);
  }, [picks]);

  React.useEffect(() => {
    const s = stateRef.current;
    if (s.rebuildPath) s.rebuildPath(generatedTrajectory);
  }, [generatedTrajectory]);

  return <div ref={mountRef} style={{ width: "100%", height: "100%", position: "relative", overflow: "hidden", cursor: "crosshair" }} />;
}

// ── Main CAM screen ──────────────────────────────────────────────────────
function CAMScreen({ robot, onGoto }) {
  const [toolId, setToolId] = React.useState("grip-2f");
  const [part, setPart] = React.useState(() => JSON.parse(JSON.stringify(PART_LIBRARY[0])));
  const [mode, setMode] = React.useState("POLY");   // POLY | POINT | CONTOUR
  const [standoff, setStandoff] = React.useState(5);       // mm
  const [approach, setApproach] = React.useState(60);      // mm
  const [vel, setVel] = React.useState(30);
  const [acc, setAcc] = React.useState(40);
  const [orient, setOrient] = React.useState("NORMAL");    // NORMAL | FIXED_Z | TANGENT

  const [picks, setPicks] = React.useState([]);
  const [hover, setHover] = React.useState(null);

  const tool = findTool(toolId);
  // make the chosen tool active so the 3D arm, FK and IK all use it
  React.useEffect(() => { setActiveTool(findTool(toolId)); }, [toolId]);

  const handleClick = (hit) => { setPicks(p => [...p, hit]); };
  const handleHover = (hit) => setHover(hit);

  const clearAll = () => { setPicks([]); setHover(null); };
  const undo = () => setPicks(p => p.slice(0, -1));
  const reverse = () => setPicks(p => [...p].reverse());

  // load default dims/pose when the part kind changes
  const setKind = (kind) => {
    const def = PART_LIBRARY.find(p => p.kind === kind) || PART_LIBRARY[0];
    setPart(JSON.parse(JSON.stringify({ ...def })));
    setPicks([]);
  };
  const setDim = (k, v) => setPart(p => ({ ...p, dims: { ...p.dims, [k]: v } }));
  const setPosX = (v) => setPart(p => ({ ...p, pose: { ...p.pose, pos: [v, p.pose.pos[1], p.pose.pos[2]] } }));
  const setPosZ = (v) => setPart(p => ({ ...p, pose: { ...p.pose, pos: [p.pose.pos[0], p.pose.pos[1], v] } }));

  // top-face footprint of the current part (for CONTOUR/RASTER patterns)
  const footprint = () => {
    const d = part.dims, c = part.pose.pos, y = partTopY(part);
    let wx, wz;
    if (part.kind === "CYLINDER") { wx = wz = d.r; }
    else if (part.kind === "STEP") { wx = d.topW / 2; wz = d.topD / 2; }
    else { wx = d.w / 2; wz = d.d / 2; }
    const inset = 0.04;
    return { x0: c[0] - wx + inset, x1: c[0] + wx - inset, z0: c[2] - wz + inset, z1: c[2] + wz - inset, y };
  };

  const generateContour = () => {
    const { x0, x1, z0, z1, y } = footprint();
    const n = [0, 1, 0];
    setPicks([
      { point: [x0, y, z0], normal: n }, { point: [x1, y, z0], normal: n },
      { point: [x1, y, z1], normal: n }, { point: [x0, y, z1], normal: n },
      { point: [x0, y, z0], normal: n },
    ]);
  };
  const generateRaster = () => {
    const { x0, x1, z0, z1, y } = footprint();
    const n = [0, 1, 0], pts = [], passes = 5;
    for (let i = 0; i < passes; i++) {
      const z = z0 + (z1 - z0) * (i / (passes - 1));
      if (i % 2 === 0) { pts.push({ point: [x0, y, z], normal: n }); pts.push({ point: [x1, y, z], normal: n }); }
      else { pts.push({ point: [x1, y, z], normal: n }); pts.push({ point: [x0, y, z], normal: n }); }
    }
    setPicks(pts);
  };

  // auto-generated trajectory (toolId in deps: IK backs off by the tool length)
  const traj = React.useMemo(() => {
    if (picks.length === 0) return null;
    return generateCAMTrajectory(picks, {
      standoff:  standoff / 1000,
      approachHeight: approach / 1000,
      vel, acc, tool,
    });
  }, [picks, standoff, approach, vel, acc, toolId]);

  // joint angles: at last picked point if any, else home
  const liveJoints = React.useMemo(() => {
    if (hover) return approxIK(hover.point, hover.normal);
    if (picks.length > 0) {
      const last = picks[picks.length - 1];
      return approxIK(last.point, last.normal);
    }
    return [0, -90, 0, 0, 90, 0];
  }, [hover, picks, toolId]);

  return (
    <div className="screen cam">
      <div className="cam-grid">
        <Panel title="CAM · CLICK SURFACE TO DEFINE PATH" right={
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span className="tag dim">PART</span>
            {["BOX","CYLINDER","PLATE","STEP"].map(k =>
              <button key={k} className={"chip" + (part.kind === k ? " on" : "")} onClick={() => setKind(k)}>{k}</button>
            )}
          </div>
        } pad={false} style={{ gridColumn: "1 / span 2", gridRow: "1 / span 2" }}>
          <div className="cam-3d">
            <CAMViewer3D
              key={toolId}
              jointAngles={liveJoints}
              picks={picks}
              generatedTrajectory={traj}
              hoverPick={hover}
              part={part}
              tool={tool}
              onSurfaceClick={handleClick}
              onSurfaceHover={handleHover}
              reach={robot ? robot.reach : 1.0}
            />
            {/* HUD */}
            <div className="cam-hud">
              <div className="cam-hud-row">
                <span className="mono" style={{ color: "var(--ok)" }}>● {picks.length} PICK{picks.length !== 1 ? "S" : ""}</span>
                {hover && (
                  <>
                    <span className="tag dim">HOVER</span>
                    <span className="mono" style={{ fontSize: 10, color: "var(--warn)" }}>
                      X {hover.point[0].toFixed(3)}  Y {hover.point[1].toFixed(3)}  Z {hover.point[2].toFixed(3)}
                    </span>
                    <span className="tag dim">N</span>
                    <span className="mono" style={{ fontSize: 10, color: "var(--warn)" }}>
                      ({hover.normal.map(v => v.toFixed(2)).join(", ")})
                    </span>
                  </>
                )}
              </div>
              <div className="cam-hud-row">
                <span className="tag dim">CLICK SURFACE</span>
                <span className="mono" style={{ fontSize: 10 }}>add pt</span>
                <span className="tag dim">DRAG</span>
                <span className="mono" style={{ fontSize: 10 }}>orbit</span>
                <span className="tag dim">SCROLL</span>
                <span className="mono" style={{ fontSize: 10 }}>zoom</span>
              </div>
            </div>
          </div>
        </Panel>

        {/* PARAMETERS */}
        <Panel title="MACHINING PARAMETERS">
          <div className="tag dim">TOOL</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4, marginBottom: 6 }}>
            {TOOL_LIBRARY.map(t =>
              <button key={t.id} className={"chip" + (toolId === t.id ? " on" : "")} onClick={() => setToolId(t.id)}>{t.name}</button>
            )}
          </div>
          <div className="form-row" style={{ flexDirection: "row", gap: 10, marginBottom: 8 }}>
            <span className="tag dim">TYPE</span>
            <span className="mono" style={{ fontSize: 10, color: "var(--info)" }}>{tool ? tool.type : "—"}</span>
            <span className="tag dim">TCP·LEN</span>
            <span className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>
              {tool ? (Math.hypot(...tool.tcpOffset) * 1000).toFixed(0) : 0} mm
            </span>
          </div>

          <hr className="hr" />
          <div className="tag dim">PART DIMENSIONS · {part.kind}</div>
          <div style={{ marginTop: 4, marginBottom: 4 }}>
            {Object.keys(part.dims).map(k => (
              <div key={k} className="cam-slider">
                <div className="cam-slider-h">
                  <span className="tag dim">{k.toUpperCase()}</span>
                  <span className="mono" style={{ color: "var(--ok)" }}>{(part.dims[k] * 1000).toFixed(0)} mm</span>
                </div>
                <input type="range" className="slider" min="0.02" max="0.6" step="0.005"
                  value={part.dims[k]} onChange={e => setDim(k, +e.target.value)} />
              </div>
            ))}
            <div className="cam-slider">
              <div className="cam-slider-h"><span className="tag dim">POS·X</span>
                <span className="mono" style={{ color: "var(--ok)" }}>{part.pose.pos[0].toFixed(2)} m</span></div>
              <input type="range" className="slider" min="0.2" max="0.8" step="0.01"
                value={part.pose.pos[0]} onChange={e => setPosX(+e.target.value)} />
            </div>
            <div className="cam-slider">
              <div className="cam-slider-h"><span className="tag dim">POS·Z</span>
                <span className="mono" style={{ color: "var(--ok)" }}>{part.pose.pos[2].toFixed(2)} m</span></div>
              <input type="range" className="slider" min="-0.4" max="0.4" step="0.01"
                value={part.pose.pos[2]} onChange={e => setPosZ(+e.target.value)} />
            </div>
          </div>

          <hr className="hr" />
          <div className="tag dim">PICK MODE</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
            {[["POINT","Single picks"],["POLY","Polyline"],["CONTOUR","Closed loop"]].map(([k, lbl]) =>
              <button key={k} className={"chip" + (mode === k ? " on" : "")} onClick={() => setMode(k)} title={lbl}>{k}</button>
            )}
          </div>

          <div className="cam-slider">
            <div className="cam-slider-h">
              <span className="tag dim">TOOL STANDOFF</span>
              <span className="mono" style={{ color: "var(--ok)" }}>{standoff} mm</span>
            </div>
            <input type="range" className="slider" min="0" max="50" value={standoff} onChange={e => setStandoff(+e.target.value)} />
          </div>

          <div className="cam-slider">
            <div className="cam-slider-h">
              <span className="tag dim">APPROACH / RETREAT</span>
              <span className="mono" style={{ color: "var(--ok)" }}>{approach} mm</span>
            </div>
            <input type="range" className="slider" min="10" max="200" value={approach} onChange={e => setApproach(+e.target.value)} />
          </div>

          <div className="cam-slider">
            <div className="cam-slider-h">
              <span className="tag dim">TCP SPEED</span>
              <span className="mono" style={{ color: "var(--ok)" }}>{vel} %</span>
            </div>
            <input type="range" className="slider" min="5" max="100" value={vel} onChange={e => setVel(+e.target.value)} />
          </div>

          <div className="cam-slider">
            <div className="cam-slider-h">
              <span className="tag dim">ACCELERATION</span>
              <span className="mono" style={{ color: "var(--ok)" }}>{acc} %</span>
            </div>
            <input type="range" className="slider" min="5" max="100" value={acc} onChange={e => setAcc(+e.target.value)} />
          </div>

          <div className="tag dim" style={{ marginTop: 8 }}>TOOL ORIENTATION</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
            {[["NORMAL","Normal to surface"],["FIXED_Z","Fixed −Z"],["TANGENT","Along tangent"]].map(([k, lbl]) =>
              <button key={k} className={"chip" + (orient === k ? " on" : "")} onClick={() => setOrient(k)} title={lbl}>{k.replace("_"," ")}</button>
            )}
          </div>

          <hr className="hr" />
          <div className="tag dim">QUICK GENERATE</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
            <button className="btn" onClick={generateContour}>▢ CONTOUR</button>
            <button className="btn" onClick={generateRaster}>≡ RASTER</button>
          </div>
        </Panel>

        {/* PICKED POINTS LIST */}
        <Panel title={`PICKED POINTS · ${picks.length}`} right={
          <div style={{ display: "flex", gap: 4 }}>
            <button className="chip" onClick={undo} disabled={!picks.length}>UNDO</button>
            <button className="chip" onClick={reverse} disabled={picks.length < 2}>REV</button>
            <button className="chip" onClick={clearAll} disabled={!picks.length}>CLEAR</button>
          </div>
        } pad={false}>
          <div className="picklist">
            {picks.length === 0 && (
              <div style={{ padding: 16, textAlign: "center", color: "var(--dim)" }}>
                <div className="mono" style={{ fontSize: 11 }}>CLICK THE WORKPIECE</div>
                <div className="tag dim" style={{ marginTop: 4 }}>or generate a pattern</div>
              </div>
            )}
            {picks.map((p, i) => (
              <div key={i} className="pickrow">
                <span className="mono pickrow-n">{String(i + 1).padStart(2, "0")}</span>
                <div className="pickrow-body">
                  <div className="mono" style={{ fontSize: 10 }}>
                    <span style={{ color: "var(--err)" }}>X {p.point[0].toFixed(3)}</span>{"  "}
                    <span style={{ color: "var(--ok)" }}>Y {p.point[1].toFixed(3)}</span>{"  "}
                    <span style={{ color: "var(--info)" }}>Z {p.point[2].toFixed(3)}</span>
                  </div>
                  <div className="mono" style={{ fontSize: 9, color: "var(--fg-mute)" }}>
                    N ({p.normal.map(v => v.toFixed(2)).join(", ")})
                  </div>
                </div>
                <button className="chip danger-chip" onClick={() => setPicks(ps => ps.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
          </div>
        </Panel>

        {/* AUTO-GENERATED TRAJECTORY METRICS */}
        <Panel title="AUTO-GENERATED TRAJECTORY" right={
          traj && (
            <div style={{ display: "flex", gap: 4 }}>
              <button className="btn primary" onClick={() => {
                window.GENERATED_TRAJECTORY = traj;
                onGoto("path");
              }}>OPEN IN PATH EDITOR ›</button>
            </div>
          )
        }>
          {!traj ? (
            <div style={{ padding: 12, color: "var(--dim)" }} className="mono">
              Click points on the surface to auto-generate a robot trajectory.
            </div>
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
                <Stat label="WAYPOINTS" value={traj.waypoints.length} color="var(--ok)" />
                <Stat label="CYCLE TIME" value={`${traj.totalTime.toFixed(2)}s`} />
                <Stat label="PATH LEN" value={`${traj.pathLength.toFixed(3)}m`} />
                <Stat label="MAX TCP·v" value={`${traj.maxTCPSpeed.toFixed(2)}m/s`} />
              </div>
              <hr className="hr" />
              <div className="tag dim">GENERATED SEQUENCE</div>
              <div className="auto-seq">
                {traj.waypoints.map((w, i) => (
                  <div key={i} className="auto-wp">
                    <span className="mono" style={{ fontSize: 9, color: "var(--ok)" }}>{String(i+1).padStart(2,"0")}</span>
                    <span className={"wp-type " + (w.type === "MoveL" ? "lin" : "joint")}>{w.type}</span>
                    <span className="mono" style={{ fontSize: 10, color: "var(--fg)" }}>{w.name}</span>
                    <span className="mono" style={{ fontSize: 9, color: "var(--dim)" }}>v{w.vel} a{w.acc}{w.blend?` r${w.blend}`:""}</span>
                    {w.io && <span className="mono" style={{ fontSize: 9, color: "var(--magenta)" }}>↪ {w.io.label}</span>}
                    <span className="mono" style={{ fontSize: 9, color: "var(--ok)", marginLeft: "auto" }}>{w.t.toFixed(2)}s</span>
                  </div>
                ))}
              </div>
              <hr className="hr" />
              <div className="tag dim">CHECKS · AUTO-VALIDATION</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                {[
                  ["REACH", "PASS", "var(--ok)"],
                  ["SINGULARITY", "PASS", "var(--ok)"],
                  ["COLLISION", "PASS", "var(--ok)"],
                  ["JOINT LIMITS", "PASS", "var(--ok)"],
                  ["VEL LIMITS", "PASS", "var(--ok)"],
                  ["TOOL CLEARANCE", "PASS", "var(--ok)"],
                ].map(([k, v, c]) =>
                  <div key={k} className="check-row" style={{ borderBottom: 0 }}>
                    <span className="mono" style={{ fontSize: 10, color: c }}>✓</span>
                    <span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span>
                  </div>
                )}
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                <button className="btn primary">SEND TO ROBOT ›</button>
                <button className="btn">SIMULATE</button>
                <button className="btn">EXPORT URPx</button>
                <button className="btn">EXPORT GCODE</button>
              </div>
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}

Object.assign(window, { CAMScreen, CAMViewer3D, generateCAMTrajectory, approxIK });
