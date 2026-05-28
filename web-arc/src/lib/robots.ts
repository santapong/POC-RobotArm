// Catalog of 6-DoF robot arms the editor knows about. Numeric specs come
// from public manufacturer datasheets (payload, reach, axis limits, max
// joint/TCP speeds). Link lengths are schematic — they're tuned so the
// rendered arm is roughly the right size relative to the workspace sphere,
// not to model each manufacturer's brand-specific kinematics.

import type { RobotModel } from "@/types";

// Link lengths sum to approximately `reach`, so the schematic chain matches
// the workspace sphere drawn in the 3D viewer.
function linksFor(reach: number) {
  return {
    baseHeight:   +(reach * 0.22).toFixed(3),
    upperArm:     +(reach * 0.36).toFixed(3),
    forearm:      +(reach * 0.30).toFixed(3),
    wristOffset:  +(reach * 0.105).toFixed(3),
    flangeOffset: +(reach * 0.015).toFixed(3),
  };
}

const SIX = (lo: number, hi: number): [number, number][] => Array.from({ length: 6 }, () => [lo, hi]);

export const ROBOT_LIBRARY: RobotModel[] = [
  {
    id: "ur5e",
    name: "UR5e",
    manufacturer: "Universal Robots",
    family: "e-Series",
    dof: 6,
    payload: 5,
    reach: 0.85,
    links: { baseHeight: 0.26, upperArm: 0.425, forearm: 0.392, wristOffset: 0.155, flangeOffset: 0.025 },
    jointLimits: SIX(-360, 360),
    maxJointVel: [180, 180, 180, 180, 180, 180],
    maxTcpSpeed: 1.0,
    accent: "#4ade80",
  },
  {
    id: "ur10e",
    name: "UR10e",
    manufacturer: "Universal Robots",
    family: "e-Series",
    dof: 6,
    payload: 12.5,
    reach: 1.30,
    links: { baseHeight: 0.36, upperArm: 0.612, forearm: 0.572, wristOffset: 0.180, flangeOffset: 0.025 },
    jointLimits: SIX(-360, 360),
    maxJointVel: [120, 120, 180, 180, 180, 180],
    maxTcpSpeed: 1.0,
    accent: "#38bdf8",
  },
  {
    id: "abb-irb1300-7-140",
    name: "IRB 1300-7/1.40",
    manufacturer: "ABB",
    family: "IRB 1300",
    dof: 6,
    payload: 7,
    reach: 1.40,
    links: linksFor(1.40),
    jointLimits: [
      [-180, 180],
      [-75, 155],
      [-180, 75],
      [-230, 230],
      [-125, 125],
      [-400, 400],
    ],
    maxJointVel: [225, 225, 225, 360, 360, 540],
    maxTcpSpeed: 6.0,
    accent: "#ef4444",
  },
  {
    id: "abb-irb1300-10-115",
    name: "IRB 1300-10/1.15",
    manufacturer: "ABB",
    family: "IRB 1300",
    dof: 6,
    payload: 10,
    reach: 1.15,
    links: linksFor(1.15),
    jointLimits: [
      [-180, 180],
      [-75, 155],
      [-180, 75],
      [-230, 230],
      [-125, 125],
      [-400, 400],
    ],
    maxJointVel: [225, 225, 225, 360, 360, 540],
    maxTcpSpeed: 6.0,
    accent: "#ef4444",
  },
  {
    id: "abb-irb1300-11-090",
    name: "IRB 1300-11/0.9",
    manufacturer: "ABB",
    family: "IRB 1300",
    dof: 6,
    payload: 11,
    reach: 0.90,
    links: linksFor(0.90),
    jointLimits: [
      [-180, 180],
      [-75, 155],
      [-180, 75],
      [-230, 230],
      [-125, 125],
      [-400, 400],
    ],
    maxJointVel: [225, 225, 225, 360, 360, 540],
    maxTcpSpeed: 6.0,
    accent: "#ef4444",
  },
  {
    id: "abb-irb120",
    name: "IRB 120",
    manufacturer: "ABB",
    family: "IRB 120",
    dof: 6,
    payload: 3,
    reach: 0.58,
    links: linksFor(0.58),
    jointLimits: [
      [-165, 165],
      [-110, 110],
      [-110, 70],
      [-160, 160],
      [-120, 120],
      [-400, 400],
    ],
    maxJointVel: [250, 250, 250, 320, 320, 420],
    maxTcpSpeed: 6.2,
    accent: "#f97316"
  },
  {
    id: "kuka-kr6-r900",
    name: "KR 6 R900 sixx",
    manufacturer: "KUKA",
    family: "AGILUS",
    dof: 6,
    payload: 6,
    reach: 0.901,
    links: linksFor(0.901),
    jointLimits: [
      [-170, 170],
      [-190, 45],
      [-120, 156],
      [-185, 185],
      [-120, 120],
      [-350, 350],
    ],
    maxJointVel: [300, 300, 300, 360, 360, 600],
    maxTcpSpeed: 7.5,
    accent: "#fbbf24",
  },
  {
    id: "fanuc-lrmate-200id-7l",
    name: "LR Mate 200iD/7L",
    manufacturer: "Fanuc",
    family: "LR Mate 200iD",
    dof: 6,
    payload: 7,
    reach: 0.911,
    links: linksFor(0.911),
    jointLimits: [
      [-170, 170],
      [-100, 145],
      [-145, 213],
      [-190, 190],
      [-125, 125],
      [-360, 360],
    ],
    maxJointVel: [380, 360, 460, 540, 720, 900],
    maxTcpSpeed: 6.0,
    accent: "#e879f9",
  },
];

export const DEFAULT_ROBOT_ID = "ur5e";

export function findRobot(id: string | null | undefined): RobotModel | null {
  if (!id) return null;
  return ROBOT_LIBRARY.find(r => r.id === id) ?? null;
}

// Resolve a doc.robotId to a RobotModel, falling back to the default when
// missing (v1 docs) or unknown.
export function resolveRobot(id: string | null | undefined): RobotModel {
  const r = findRobot(id) ?? findRobot(DEFAULT_ROBOT_ID);
  // The default is always present in the catalog; the non-null assertion is
  // safe by construction.
  return r as RobotModel;
}
