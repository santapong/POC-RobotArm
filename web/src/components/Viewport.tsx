/**
 * 3D viewport — R3F Canvas with OrbitControls, grid, axes, and one
 * RobotURDF component per robot in the station.
 *
 * URDF URLs come from the catalog store (populated at app mount).
 */

import { Canvas } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import { RobotURDF } from "./RobotURDF";
import { useStationStore } from "@/store/station";
import { useCatalogStore } from "@/store/catalog";

export function Viewport() {
  const station = useStationStore((s) => s.station);
  const catalogEntries = useCatalogStore((s) => s.entries);

  const robots = station?.robots ?? [];

  return (
    <div className="h-full w-full">
      <Canvas
        camera={{ position: [2, 2, 2], fov: 50 }}
        gl={{ antialias: true }}
        shadows
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 10, 5]} intensity={1} castShadow />

        {/* Grid helper at y=0 */}
        <Grid
          args={[10, 10]}
          cellSize={0.1}
          cellThickness={0.5}
          cellColor="#6b7280"
          sectionSize={1}
          sectionThickness={1}
          sectionColor="#374151"
          fadeDistance={15}
          fadeStrength={1}
          followCamera={false}
          infiniteGrid
        />

        {/* Axes helper at origin */}
        <axesHelper args={[0.5]} />

        {/* One URDF mesh per robot */}
        {robots.map((robot) => {
          const catalogEntry = catalogEntries.find(
            (e) => e.name === robot.robot_catalog_name,
          );
          if (catalogEntry === undefined) return null;
          return (
            <RobotURDF
              key={robot.name}
              id={robot.name}
              catalogName={robot.robot_catalog_name}
              urdfUrl={catalogEntry.urdf_url}
            />
          );
        })}

        <OrbitControls makeDefault />
      </Canvas>
    </div>
  );
}
