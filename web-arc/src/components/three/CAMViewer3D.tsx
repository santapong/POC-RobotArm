// 3D CAM viewer: arm + parametric part + clickable raycast for surface picks,
// + magenta pick polyline + green generated trajectory line (FK-sampled).
// Sets the active tool at the top of its build effect so the FK cache picks
// up the new tool's TCP length BEFORE rebuilding the path.

import { useEffect, useRef } from "react";
import {
  AmbientLight, BufferAttribute, BufferGeometry, CircleGeometry, Color,
  DirectionalLight, DoubleSide, Fog, GridHelper, Group, Line, LineBasicMaterial,
  Mesh, MeshBasicMaterial, MeshStandardMaterial, PerspectiveCamera, PointLight,
  Quaternion, Raycaster, RingGeometry, Scene, SphereGeometry, Vector2, Vector3,
  WebGLRenderer, ArrowHelper, type Object3D,
} from "three";
import type { Part, Pick, RobotModel, Tool, Trajectory } from "@/types";
import { applyJointAngles, buildArmMesh, type ArmMesh } from "@/lib/three/arm-mesh";
import { armTCP, setActiveRobot, setActiveTool } from "@/lib/three/fk";
import { buildPartMesh } from "@/lib/three/part-mesh";
import { buildPathSamples } from "@/lib/trajectory";
import { OrbitControls } from "@/lib/three/orbit-controls";
import { SCENE_BG_HEX, useUiStore } from "@/store/useUiStore";

export interface SurfaceHit { point: [number, number, number]; normal: [number, number, number]; }

export interface CAMViewer3DProps {
  jointAngles: number[];
  picks: Pick[];
  generatedTrajectory: Trajectory | null;
  part: Part | null;
  tool: Tool | null;
  // Optional active robot. Drives the arm's link lengths and the IK used by
  // generateCAMTrajectory. Combine with React `key={robotId+":"+toolId}` to
  // force a fresh build on either change.
  robot?: RobotModel | null;
  onSurfaceClick?: (hit: SurfaceHit) => void;
  onSurfaceHover?: (hit: SurfaceHit | null) => void;
}

interface ViewerState {
  scene: Scene; camera: PerspectiveCamera; renderer: WebGLRenderer;
  controls: OrbitControls; arm: ArmMesh;
  workpiece: Group; currentPart: Part | null;
  hoverDot: Mesh; hoverRing: Mesh; hoverNormal: ArrowHelper; hoverGrp: Group;
  pickGroup: Group; pathGroup: Group;
  rebuildPicks: (picks: Pick[]) => void;
  rebuildPath: (t: Trajectory | null) => void;
  target: number[]; current: number[];
  singularityGroup: Group;
  wristSingHalo: Mesh;
  tcpWorld: Vector3;
  showSingularity: boolean;
  raf: number | null; alive: boolean;
}

export function CAMViewer3D({
  jointAngles, picks, generatedTrajectory,
  part, tool, robot = null,
  onSurfaceClick, onSurfaceHover,
}: CAMViewer3DProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const stateRef = useRef<ViewerState | null>(null);
  const sceneBg = useUiStore(s => s.tweaks.sceneBg);
  const showSingularity = useUiStore(s => s.tweaks.showSingularity);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    // Make this viewer's tool + robot the active ones BEFORE building the
    // arm/path, so the FK cache (armTCP) is rebuilt against the new link
    // lengths and TCP length (the green path/waypoints sit on the tool).
    setActiveRobot(robot ?? null);
    setActiveTool(tool ?? null);

    const W = mount.clientWidth || 800;
    const H = mount.clientHeight || 500;

    const scene = new Scene();
    const bgHex = SCENE_BG_HEX[sceneBg] ?? SCENE_BG_HEX.dark;
    scene.background = new Color(bgHex);
    scene.fog = new Fog(bgHex, 4, 9);

    const camera = new PerspectiveCamera(40, W / H, 0.05, 50);
    camera.position.set(1.4, 1.1, 1.6);

    const renderer = new WebGLRenderer({ antialias: true });
    renderer.setSize(W, H); renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    scene.add(new AmbientLight(0x6080a0, 0.45));
    const sun = new DirectionalLight(0xfff5e0, 0.7); sun.position.set(3, 6, 2); scene.add(sun);
    const cy = new PointLight(0x38bdf8, 1.0, 6); cy.position.set(-2, 1.5, -1.5); scene.add(cy);
    const gn = new PointLight(0x4ade80, 0.5, 4); gn.position.set(1.2, 0.4, 1.8); scene.add(gn);

    const grid = new GridHelper(6, 24, 0x4ade80, 0x1c2a32);
    const mats = Array.isArray(grid.material) ? grid.material : [grid.material];
    mats.forEach(m => { m.opacity = 0.42; m.transparent = true; });
    scene.add(grid);
    const floor = new Mesh(
      new CircleGeometry(2.4, 48),
      new MeshStandardMaterial({ color: 0x070b10, metalness: 0.4, roughness: 0.7 }),
    );
    floor.rotation.x = -Math.PI / 2; floor.position.y = -0.001; scene.add(floor);

    // Singularity overlay — same scheme as Arm3D: a red shoulder disc at
    // the base z-axis, an amber elbow ring at the workspace boundary, and a
    // dynamic wrist halo on the TCP when J5 ≈ 0 (driven by the animate loop).
    const singularityGroup = new Group();
    singularityGroup.name = "SINGULARITIES";
    singularityGroup.visible = showSingularity;
    const baseHeight = robot?.links.baseHeight ?? 0.22;
    const shoulderDisc = new Mesh(
      new RingGeometry(0.04, 0.16, 36),
      new MeshBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0.35, side: DoubleSide }),
    );
    shoulderDisc.rotation.x = -Math.PI / 2;
    shoulderDisc.position.y = baseHeight + 0.001;
    singularityGroup.add(shoulderDisc);
    const reach = robot?.reach ?? 1.0;
    const elbowRing = new Mesh(
      new RingGeometry(reach - 0.01, reach + 0.01, 64, 1, 0, Math.PI),
      new MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.32, side: DoubleSide }),
    );
    elbowRing.rotation.x = -Math.PI / 2;
    elbowRing.position.y = baseHeight;
    singularityGroup.add(elbowRing);
    const wristSingHalo = new Mesh(
      new SphereGeometry(0.055, 18, 18),
      new MeshBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0.0, wireframe: true }),
    );
    wristSingHalo.visible = false;
    scene.add(singularityGroup);
    scene.add(wristSingHalo);

    const arm = buildArmMesh(tool ?? null, robot ?? null);
    scene.add(arm.root);

    let workpiece = buildPartMesh(part);
    scene.add(workpiece);

    const hoverGrp = new Group(); scene.add(hoverGrp);
    const hoverDot = new Mesh(new SphereGeometry(0.012, 16, 16), new MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.95 }));
    const hoverRing = new Mesh(new RingGeometry(0.020, 0.028, 24), new MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.6, side: DoubleSide }));
    const hoverNormal = new ArrowHelper(new Vector3(0, 1, 0), new Vector3(), 0.08, 0xfbbf24, 0.025, 0.018);
    hoverGrp.add(hoverDot, hoverRing, hoverNormal);
    hoverGrp.visible = false;

    const pickGroup = new Group(); scene.add(pickGroup);
    const pathGroup = new Group(); scene.add(pathGroup);

    const disposeChildren = (g: Group): void => {
      while (g.children.length) {
        const c = g.children[0] as Mesh | Line;
        g.remove(c);
        if ("geometry" in c && c.geometry) c.geometry.dispose();
        const m = (c as Mesh).material;
        if (m && !Array.isArray(m)) m.dispose();
      }
    };

    const rebuildPicks = (ps: Pick[]) => {
      disposeChildren(pickGroup);
      (ps || []).forEach(p => {
        const sphere = new Mesh(new SphereGeometry(0.015, 16, 16), new MeshBasicMaterial({ color: 0xe879f9 }));
        sphere.position.set(p.point[0], p.point[1], p.point[2]);
        pickGroup.add(sphere);
        const arrow = new ArrowHelper(
          new Vector3(p.normal[0], p.normal[1], p.normal[2]),
          new Vector3(p.point[0], p.point[1], p.point[2]),
          0.06, 0xe879f9, 0.022, 0.016,
        );
        pickGroup.add(arrow);
      });
      if (ps && ps.length >= 2) {
        const geom = new BufferGeometry();
        const arr = new Float32Array(ps.length * 3);
        ps.forEach((p, i) => { arr[i * 3] = p.point[0]; arr[i * 3 + 1] = p.point[1]; arr[i * 3 + 2] = p.point[2]; });
        geom.setAttribute("position", new BufferAttribute(arr, 3));
        pickGroup.add(new Line(geom, new LineBasicMaterial({ color: 0xe879f9, transparent: true, opacity: 0.7 })));
      }
    };

    const rebuildPath = (traj: Trajectory | null) => {
      disposeChildren(pathGroup);
      if (!traj) return;
      const pts = buildPathSamples(traj.waypoints, 200);
      if (pts.length >= 2) {
        const geom = new BufferGeometry();
        const arr = new Float32Array(pts.length * 3);
        pts.forEach((p, i) => { arr[i * 3] = p[0]; arr[i * 3 + 1] = p[1]; arr[i * 3 + 2] = p[2]; });
        geom.setAttribute("position", new BufferAttribute(arr, 3));
        pathGroup.add(new Line(geom, new LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.92 })));
        pathGroup.add(new Line(geom.clone(), new LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.3 })));
      }
      traj.waypoints.forEach(wp => {
        const isLin = wp.type === "MoveL";
        const sphere = new Mesh(
          new SphereGeometry(0.016, 14, 14),
          new MeshBasicMaterial({ color: isLin ? 0x38bdf8 : 0xfbbf24 }),
        );
        const p = armTCP(wp.joints);
        sphere.position.set(p[0], p[1], p[2]);
        pathGroup.add(sphere);
      });
    };

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = 0.08;
    controls.target.set(0.4, 0.3, 0);
    controls.minDistance = 0.6; controls.maxDistance = 6;
    controls.maxPolarAngle = Math.PI / 2 - 0.02;

    const initial = (jointAngles || [0, -60, 90, 0, 40, 0]).map(d => d * Math.PI / 180);
    const state: ViewerState = {
      scene, camera, renderer, controls, arm,
      workpiece, currentPart: part,
      hoverGrp, hoverDot, hoverRing, hoverNormal,
      pickGroup, pathGroup, rebuildPicks, rebuildPath,
      target: initial.slice(), current: initial.slice(),
      singularityGroup, wristSingHalo,
      tcpWorld: new Vector3(),
      showSingularity,
      raf: null, alive: true,
    };
    stateRef.current = state;

    rebuildPicks(picks);
    rebuildPath(generatedTrajectory);

    // raycaster + pointer
    const raycaster = new Raycaster();
    const ndc = new Vector2();
    let downAt: { x: number; y: number } | null = null;
    const getClickables = (): Object3D[] => state.workpiece.children.filter(c => c.userData.clickable);
    const castFromEvent = (e: PointerEvent): SurfaceHit | null => {
      const rect = renderer.domElement.getBoundingClientRect();
      ndc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      ndc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(getClickables(), false);
      if (!hits.length) return null;
      const hit = hits[0];
      const n = hit.face!.normal.clone();
      n.transformDirection(hit.object.matrixWorld);
      return {
        point: [hit.point.x, hit.point.y, hit.point.z],
        normal: [n.x, n.y, n.z],
      };
    };
    const onMove = (e: PointerEvent): void => {
      const hit = castFromEvent(e);
      if (hit) {
        hoverGrp.visible = true;
        hoverDot.position.set(hit.point[0], hit.point[1], hit.point[2]);
        hoverRing.position.set(
          hit.point[0] + hit.normal[0] * 0.001,
          hit.point[1] + hit.normal[1] * 0.001,
          hit.point[2] + hit.normal[2] * 0.001,
        );
        const up = new Vector3(hit.normal[0], hit.normal[1], hit.normal[2]);
        const q = new Quaternion().setFromUnitVectors(new Vector3(0, 0, 1), up);
        hoverRing.quaternion.copy(q);
        hoverNormal.setDirection(up);
        hoverNormal.position.set(hit.point[0], hit.point[1], hit.point[2]);
        onSurfaceHover?.(hit);
      } else {
        hoverGrp.visible = false;
        onSurfaceHover?.(null);
      }
    };
    const onDown = (e: PointerEvent): void => { downAt = { x: e.clientX, y: e.clientY }; };
    const onUp = (e: PointerEvent): void => {
      if (!downAt) return;
      const dx = e.clientX - downAt.x, dy = e.clientY - downAt.y;
      const moved = Math.hypot(dx, dy);
      downAt = null;
      if (moved > 3) return;
      if (e.button !== 0) return;
      const hit = castFromEvent(e);
      if (hit) onSurfaceClick?.(hit);
    };
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    const ro = new ResizeObserver(() => {
      const w = mount.clientWidth, h = mount.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h; camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    ro.observe(mount);

    const animate = (): void => {
      const s = stateRef.current;
      if (!s || !s.alive) return;
      s.raf = requestAnimationFrame(animate);
      for (let i = 0; i < 6; i++) s.current[i] += (s.target[i] - s.current[i]) * 0.04;
      applyJointAngles(s.arm, s.current);
      const t = performance.now() / 400;
      s.hoverRing.scale.setScalar(1 + 0.15 * Math.sin(t));

      if (s.showSingularity) {
        const j5 = s.current[4] ?? 0;
        const nearSing = Math.abs(j5) < 6 * Math.PI / 180;
        s.wristSingHalo.visible = nearSing;
        if (nearSing) {
          s.arm.tcp.getWorldPosition(s.tcpWorld);
          s.wristSingHalo.position.copy(s.tcpWorld);
          (s.wristSingHalo.material as MeshBasicMaterial).opacity = 0.45 + 0.35 * Math.sin(performance.now() / 180);
          s.wristSingHalo.scale.setScalar(1 + 0.18 * Math.sin(performance.now() / 220));
        }
      } else if (s.wristSingHalo.visible) {
        s.wristSingHalo.visible = false;
      }

      s.controls.update();
      s.renderer.render(s.scene, s.camera);
    };
    animate();

    return () => {
      const s = stateRef.current;
      if (!s) return;
      s.alive = false;
      if (s.raf != null) cancelAnimationFrame(s.raf);
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      ro.disconnect();
      s.controls.dispose();
      s.renderer.dispose();
      if (s.renderer.domElement.parentNode === mount) mount.removeChild(s.renderer.domElement);
      s.scene.traverse(o => {
        const m = o as Mesh;
        if (m.geometry) m.geometry.dispose();
        const mat = m.material;
        if (mat) {
          if (Array.isArray(mat)) mat.forEach(x => x.dispose());
          else (mat as MeshBasicMaterial).dispose();
        }
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // swap workpiece when the part changes (kind / dims / pose)
  useEffect(() => {
    const s = stateRef.current;
    if (!s || !part || part === s.currentPart) return;
    s.scene.remove(s.workpiece);
    s.workpiece.traverse(o => {
      const m = o as Mesh;
      if (m.geometry) m.geometry.dispose();
      const mat = m.material;
      if (mat) {
        if (Array.isArray(mat)) mat.forEach(x => x.dispose());
        else (mat as MeshBasicMaterial).dispose();
      }
    });
    s.workpiece = buildPartMesh(part);
    s.scene.add(s.workpiece);
    s.currentPart = part;
  }, [part]);

  useEffect(() => {
    const s = stateRef.current; if (!s || !jointAngles) return;
    s.target = jointAngles.map(d => d * Math.PI / 180);
  }, [jointAngles]);

  useEffect(() => {
    const s = stateRef.current; if (!s) return;
    s.rebuildPicks(picks);
  }, [picks]);

  useEffect(() => {
    const s = stateRef.current; if (!s) return;
    s.rebuildPath(generatedTrajectory);
  }, [generatedTrajectory]);

  useEffect(() => {
    const s = stateRef.current; if (!s) return;
    const hex = SCENE_BG_HEX[sceneBg] ?? SCENE_BG_HEX.dark;
    (s.scene.background as Color)?.setHex(hex);
    if (s.scene.fog) (s.scene.fog as Fog).color.setHex(hex);
  }, [sceneBg]);

  useEffect(() => {
    const s = stateRef.current; if (!s) return;
    s.showSingularity = showSingularity;
    s.singularityGroup.visible = showSingularity;
    if (!showSingularity) s.wristSingHalo.visible = false;
  }, [showSingularity]);

  return <div ref={mountRef} style={{ width: "100%", height: "100%", position: "relative", overflow: "hidden", cursor: "crosshair" }} />;
}
