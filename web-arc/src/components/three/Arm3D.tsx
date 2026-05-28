// Imperative Three.js arm + path viewer. Uses the lib/three modules — there
// is no THREE on window. The playback marker is pinned to the arm's REAL TCP
// world position each frame (s.arm.tcp.getWorldPosition), so the tool is
// always exactly on the path it's following.

import { useEffect, useRef } from "react";
import {
  AmbientLight, BufferAttribute, BufferGeometry, CircleGeometry, Color,
  DirectionalLight, DoubleSide, Fog, GridHelper, Group, Line, LineBasicMaterial,
  LineDashedMaterial, Mesh, MeshBasicMaterial, MeshStandardMaterial,
  PerspectiveCamera, PointLight, RingGeometry, Scene, SphereGeometry,
  Vector3, WebGLRenderer,
  ArrowHelper,
} from "three";
import type { RobotModel, Tool, Trajectory, Vec3, Waypoint } from "@/types";
import { applyJointAngles, buildArmMesh, buildToolMesh, type ArmMesh } from "@/lib/three/arm-mesh";
import { armTCP, setActiveRobot } from "@/lib/three/fk";
import { OrbitControls } from "@/lib/three/orbit-controls";

export interface Arm3DProps {
  jointAngles: number[];
  faulty?: number[];
  showWorkspace?: boolean;
  showGrid?: boolean;
  reach?: number;
  width?: number | string;
  height?: number | string;
  autoRotate?: boolean;
  pathPoints?: Vec3[] | null;
  waypoints?: Waypoint[] | null;
  trajectory?: Trajectory | null;     // convenience — uses .waypoints
  selectedWaypoint?: number | null;
  tool?: Tool | null;
  // Optional RobotModel — drives the link lengths the schematic mesh and the
  // FK use, plus the workspace-sphere radius. Changing robots should be done
  // via React `key={robotId+":"+toolId}` so the component remounts (the arm
  // structure changes top-to-bottom, unlike a tool swap which is local to j6).
  robot?: RobotModel | null;
}

interface ArmState {
  scene: Scene;
  camera: PerspectiveCamera;
  renderer: WebGLRenderer;
  controls: OrbitControls;
  arm: ArmMesh;
  target: number[];
  current: number[];
  goalMarker: Mesh;
  goalRing: Mesh;
  tcpWorld: Vector3;
  playMarker: Mesh;
  playMarkerHalo: Mesh;
  rebuildPath?: (pts: Vec3[] | null, wps: Waypoint[] | null, selIdx: number | null) => void;
  raf: number | null;
  alive: boolean;
}

export function Arm3D({
  jointAngles, faulty = [],
  showWorkspace = true, showGrid = true,
  reach = 1.0,
  width = "100%", height = 400,
  autoRotate = false,
  pathPoints = null, waypoints = null, trajectory = null,
  selectedWaypoint = null,
  tool = null,
  robot = null,
}: Arm3DProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const stateRef = useRef<ArmState | null>(null);

  // resolve waypoints from either prop or trajectory
  const wps = waypoints ?? trajectory?.waypoints ?? null;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    // Set the active robot BEFORE building the arm/path so the FK cache
    // (armTCP) rebuilds with the right link lengths and the green path /
    // waypoint spheres sit on the new tool tip.
    setActiveRobot(robot ?? null);

    const W = mount.clientWidth || 600;
    const H = mount.clientHeight || 400;

    const scene = new Scene();
    scene.background = new Color(0x05080c);
    scene.fog = new Fog(0x05080c, 4, 9);

    const camera = new PerspectiveCamera(40, W / H, 0.05, 50);
    camera.position.set(1.6, 1.3, 1.9);

    const renderer = new WebGLRenderer({ antialias: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = false;
    mount.appendChild(renderer.domElement);

    scene.add(new AmbientLight(0x6080a0, 0.45));
    const sun = new DirectionalLight(0xfff5e0, 0.7); sun.position.set(3, 6, 2); scene.add(sun);
    const fillCy = new PointLight(0x38bdf8, 1.2, 6); fillCy.position.set(-2, 1.5, -1.5); scene.add(fillCy);
    const fillGn = new PointLight(0x4ade80, 0.6, 4); fillGn.position.set(1.2, 0.4, 1.8); scene.add(fillGn);

    if (showGrid) {
      const grid = new GridHelper(6, 24, 0x4ade80, 0x1c2a32);
      grid.position.y = 0;
      const mats = Array.isArray(grid.material) ? grid.material : [grid.material];
      mats.forEach(m => { m.opacity = 0.42; m.transparent = true; });
      scene.add(grid);
    }
    const floor = new Mesh(
      new CircleGeometry(2.4, 48),
      new MeshStandardMaterial({ color: 0x070b10, metalness: 0.4, roughness: 0.7 }),
    );
    floor.rotation.x = -Math.PI / 2; floor.position.y = -0.001; scene.add(floor);

    const triad = new Group();
    triad.add(
      new ArrowHelper(new Vector3(1, 0, 0), new Vector3(), 0.25, 0xef4444, 0.06, 0.04),
      new ArrowHelper(new Vector3(0, 1, 0), new Vector3(), 0.25, 0x4ade80, 0.06, 0.04),
      new ArrowHelper(new Vector3(0, 0, 1), new Vector3(), 0.25, 0x38bdf8, 0.06, 0.04),
    );
    triad.position.set(-1.3, 0.01, 1.3);
    scene.add(triad);

    // Workspace radius prefers the active robot's reach so the sphere sized
    // for an ABB IRB 1300-7/1.40 actually looks 1.4 m wide.
    const wsRadius = robot?.reach ?? reach;
    if (showWorkspace) {
      const ws = new Mesh(
        new SphereGeometry(wsRadius, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2 + 0.2),
        new MeshBasicMaterial({ color: 0x38bdf8, wireframe: true, opacity: 0.07, transparent: true }),
      );
      ws.position.y = robot?.links.baseHeight ?? 0.22;
      scene.add(ws);
    }

    const arm = buildArmMesh(tool ?? null, robot ?? null);
    scene.add(arm.root);

    const goalMarker = new Mesh(
      new SphereGeometry(0.025, 12, 12),
      new MeshBasicMaterial({ color: 0xe879f9, transparent: true, opacity: 0.85 }),
    );
    goalMarker.position.set(0.45, 0.55, 0.2);
    scene.add(goalMarker);
    const goalRing = new Mesh(
      new RingGeometry(0.035, 0.05, 24),
      new MeshBasicMaterial({ color: 0xe879f9, transparent: true, opacity: 0.55, side: DoubleSide }),
    );
    goalRing.position.copy(goalMarker.position);
    goalRing.rotation.x = -Math.PI / 2;
    scene.add(goalRing);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(0.1, 0.55, 0);
    controls.minDistance = 0.6;
    controls.maxDistance = 6;
    controls.maxPolarAngle = Math.PI / 2 - 0.02;
    controls.autoRotate = autoRotate;
    controls.autoRotateSpeed = 0.4;

    const initial = (jointAngles || [0, -60, 90, 0, 40, 0]).map(d => d * Math.PI / 180);
    const state: ArmState = {
      scene, camera, renderer, controls, arm,
      target: initial.slice(), current: initial.slice(),
      goalMarker, goalRing,
      tcpWorld: new Vector3(),
      playMarker: null as unknown as Mesh,        // set below
      playMarkerHalo: null as unknown as Mesh,
      raf: null, alive: true,
    };
    stateRef.current = state;

    // path + waypoints + playback marker
    const pathGroup = new Group(); pathGroup.name = "PATH"; scene.add(pathGroup);
    const wpGroup   = new Group(); wpGroup.name   = "WAYPOINTS"; scene.add(wpGroup);

    const playMarker = new Mesh(
      new SphereGeometry(0.026, 16, 16),
      new MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.95 }),
    );
    const playMarkerHalo = new Mesh(
      new SphereGeometry(0.045, 16, 16),
      new MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.18 }),
    );
    playMarker.visible = false;
    playMarkerHalo.visible = false;
    scene.add(playMarker, playMarkerHalo);
    state.playMarker = playMarker;
    state.playMarkerHalo = playMarkerHalo;

    const disposeChildren = (g: Group): void => {
      while (g.children.length) {
        const c = g.children[0] as Mesh | Line;
        g.remove(c);
        if ("geometry" in c && c.geometry) c.geometry.dispose();
        const m = (c as Mesh).material;
        if (m && !Array.isArray(m)) m.dispose();
      }
    };

    const rebuildPath = (pts: Vec3[] | null, ws: Waypoint[] | null, selIdx: number | null) => {
      disposeChildren(pathGroup);
      disposeChildren(wpGroup);

      if (pts && pts.length >= 2) {
        const geom = new BufferGeometry();
        const arr = new Float32Array(pts.length * 3);
        for (let i = 0; i < pts.length; i++) {
          arr[i * 3] = pts[i][0]; arr[i * 3 + 1] = pts[i][1]; arr[i * 3 + 2] = pts[i][2];
        }
        geom.setAttribute("position", new BufferAttribute(arr, 3));
        pathGroup.add(new Line(geom, new LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.9 })));
        pathGroup.add(new Line(geom.clone(), new LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.25 })));

        // floor shadow projection
        const shadowArr = new Float32Array(pts.length * 3);
        for (let i = 0; i < pts.length; i++) {
          shadowArr[i * 3] = pts[i][0]; shadowArr[i * 3 + 1] = 0.001; shadowArr[i * 3 + 2] = pts[i][2];
        }
        const shadowGeom = new BufferGeometry();
        shadowGeom.setAttribute("position", new BufferAttribute(shadowArr, 3));
        pathGroup.add(new Line(shadowGeom, new LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.18 })));
      }

      if (ws && ws.length) {
        ws.forEach((wp, i) => {
          const isLin = wp.type === "MoveL";
          const isSel = selIdx !== null && selIdx === i;
          const baseColor = isLin ? 0x38bdf8 : 0xfbbf24;
          const c = isSel ? 0xe879f9 : baseColor;
          const r = isSel ? 0.030 : 0.022;
          // FK to keep waypoints on the same line as the tool
          const p = armTCP(wp.joints);
          const sphere = new Mesh(
            new SphereGeometry(r, 18, 18),
            new MeshBasicMaterial({ color: c, transparent: true, opacity: 0.95 }),
          );
          sphere.position.set(p[0], p[1], p[2]);
          wpGroup.add(sphere);
          const ring = new Mesh(
            new RingGeometry(0.030, 0.045, 24),
            new MeshBasicMaterial({ color: c, transparent: true, opacity: 0.45, side: DoubleSide }),
          );
          ring.position.set(p[0], 0.002, p[2]);
          ring.rotation.x = -Math.PI / 2;
          wpGroup.add(ring);
          const dropGeom = new BufferGeometry().setFromPoints([
            new Vector3(p[0], p[1], p[2]),
            new Vector3(p[0], 0, p[2]),
          ]);
          const dropMat = new LineDashedMaterial({ color: c, dashSize: 0.02, gapSize: 0.02, transparent: true, opacity: 0.35 });
          const drop = new Line(dropGeom, dropMat); drop.computeLineDistances();
          wpGroup.add(drop);
          if (isSel) {
            const halo = new Mesh(
              new RingGeometry(0.055, 0.07, 32),
              new MeshBasicMaterial({ color: c, transparent: true, opacity: 0.55, side: DoubleSide }),
            );
            halo.position.set(p[0], p[1], p[2]);
            halo.lookAt(camera.position);
            wpGroup.add(halo);
          }
        });
      }
      const hasPath = !!pts && pts.length > 0;
      playMarker.visible = hasPath;
      playMarkerHalo.visible = hasPath;
    };
    state.rebuildPath = rebuildPath;
    rebuildPath(pathPoints, wps, selectedWaypoint);

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

      for (let i = 0; i < 6; i++) s.current[i] += (s.target[i] - s.current[i]) * 0.08;
      applyJointAngles(s.arm, s.current);

      const t = performance.now() / 600;
      s.goalRing.scale.setScalar(1 + 0.15 * Math.sin(t));
      (s.goalMarker.material as MeshBasicMaterial).opacity = 0.7 + 0.25 * Math.sin(t);

      if (s.playMarker.visible) {
        s.arm.tcp.getWorldPosition(s.tcpWorld);
        s.playMarker.position.copy(s.tcpWorld);
        s.playMarkerHalo.position.copy(s.tcpWorld);
        s.playMarkerHalo.scale.setScalar(1 + 0.2 * Math.sin(performance.now() / 220));
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
    // We deliberately use [] here — joint/path/tool prop changes are handled
    // by the dedicated effects below so we don't tear down the GL context.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // update target angles when prop changes
  useEffect(() => {
    const s = stateRef.current; if (!s || !jointAngles) return;
    s.target = jointAngles.map(d => d * Math.PI / 180);
  }, [jointAngles]);

  // rebuild path / waypoints when props change
  useEffect(() => {
    const s = stateRef.current; if (!s || !s.rebuildPath) return;
    s.rebuildPath(pathPoints, wps, selectedWaypoint);
  }, [pathPoints, wps, selectedWaypoint]);

  useEffect(() => {
    const s = stateRef.current; if (!s) return;
    s.controls.autoRotate = !!autoRotate;
  }, [autoRotate]);

  // Swap the end-effector when the `tool` prop changes. We rebuild only the
  // TOOL + TCP groups under j6 (not the whole arm) and re-point state.arm.tcp
  // so the playback marker / path FK keep tracking the real tool tip.
  useEffect(() => {
    const s = stateRef.current; if (!s) return;
    const j6 = s.arm.joints[5];
    for (const name of ["TOOL", "TCP"]) {
      const old = j6.getObjectByName(name);
      if (!old) continue;
      old.traverse(o => {
        const m = o as Mesh;
        if (m.geometry) m.geometry.dispose();
        const mat = m.material;
        if (mat) {
          if (Array.isArray(mat)) mat.forEach(x => x.dispose());
          else (mat as MeshBasicMaterial).dispose();
        }
      });
      j6.remove(old);
    }
    const built = buildToolMesh(tool ?? null);
    j6.add(built.group);
    j6.add(built.tcp);
    s.arm.tcp = built.tcp;
  }, [tool]);

  void faulty; // reserved for highlighting faulted joints

  return (
    <div
      ref={mountRef}
      style={{
        width: typeof width === "number" ? width : width,
        height: typeof height === "number" ? height : height,
        position: "relative", overflow: "hidden",
      }}
    />
  );
}
