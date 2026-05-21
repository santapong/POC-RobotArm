import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";

export default function App() {
  return (
    <div className="flex h-full w-full flex-col">
      <header className="bg-slate-900 px-4 py-2 text-lg font-semibold text-white">
        POC-RobotArm
      </header>
      <main className="flex-1">
        <Canvas camera={{ position: [3, 3, 3] }}>
          <ambientLight intensity={0.6} />
          <directionalLight position={[5, 5, 5]} />
          <mesh>
            <boxGeometry />
            <meshStandardMaterial color="#60a5fa" />
          </mesh>
          <OrbitControls />
        </Canvas>
      </main>
    </div>
  );
}
