/**
 * R3F component that loads a URDF and animates joint values from telemetry.
 *
 * The URDF is loaded once via urdf-loader in a useEffect and attached to the
 * R3F scene. Inside useFrame, joint values are read from the telemetry store
 * ref (not via a React selector) to avoid tearing at 30+ Hz.
 */

import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import URDFLoader from "urdf-loader";
import type { URDFRobot } from "urdf-loader";
import { getStateRef } from "@/store/telemetry";

interface RobotURDFProps {
  id: string;
  catalogName: string;
  urdfUrl: string;
}

export function RobotURDF({ id: _id, catalogName, urdfUrl }: RobotURDFProps) {
  const { scene } = useThree();
  const robotRef = useRef<URDFRobot | null>(null);
  // Ordered list of non-fixed joint names after load
  const jointNamesRef = useRef<string[]>([]);

  useEffect(() => {
    const manager = new THREE.LoadingManager();
    const loader = new URDFLoader(manager);

    // workingPath for resolving relative mesh references within the URDF dir
    loader.workingPath = `/api/assets/urdf/${catalogName}/`;
    // packages map — not needed for project URDFs (primitive shapes), but
    // set as a fallback in case a bundled URDF references package:// paths
    loader.packages = { "": `/api/assets/urdf/${catalogName}/` };

    loader.load(
      urdfUrl,
      (robot) => {
        robotRef.current = robot;

        // Build ordered joint name list (skip fixed joints, which don't move)
        const names: string[] = [];
        for (const [name, joint] of Object.entries(robot.joints)) {
          if (joint.jointType !== "fixed") {
            names.push(name);
          }
        }
        jointNamesRef.current = names;

        scene.add(robot);
      },
      undefined,
      (err) => {
        // Soft failure: log but do not crash the viewport
        console.warn(`Failed to load URDF for ${catalogName}:`, err);
      },
    );

    return () => {
      if (robotRef.current !== null) {
        scene.remove(robotRef.current);
        robotRef.current = null;
        jointNamesRef.current = [];
      }
    };
    // urdfUrl and catalogName are stable after initial mount; re-run only if
    // they change (robot was replaced)
  }, [urdfUrl, catalogName, scene]);

  // Inside useFrame: read telemetry via ref to avoid React re-renders.
  useFrame(() => {
    const robot = robotRef.current;
    if (robot === null) return;

    const state = getStateRef();
    const { joints_rad } = state;
    if (joints_rad.length === 0) return;

    const names = jointNamesRef.current;
    for (let i = 0; i < names.length && i < joints_rad.length; i++) {
      const name = names[i];
      if (name !== undefined) {
        robot.setJointValue(name, joints_rad[i] ?? 0);
      }
    }
  });

  // The robot is added directly to the R3F scene; no JSX children needed.
  return null;
}
