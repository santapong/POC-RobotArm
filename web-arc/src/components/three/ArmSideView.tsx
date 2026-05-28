// Lightweight 2D side-view of the arm — used in the robot detail screen
// where a full WebGL viewer would be overkill. Projects the j2/j3/j5 angles
// to a planar shoulder/elbow/wrist chain.

export interface ArmSideViewProps {
  width?: number;
  height?: number;
  jointAngles: number[];
  faulty?: number[];
}

export function ArmSideView({ width = 320, height = 280, jointAngles, faulty = [] }: ArmSideViewProps) {
  const j2 = (jointAngles[1] ?? -60) * Math.PI / 180;
  const j3 = (jointAngles[2] ?? 90) * Math.PI / 180;
  const j5 = (jointAngles[4] ?? 40) * Math.PI / 180;

  const cx = width / 2 - 30, cy = height - 50;
  const L1 = 90, L2 = 75, L3 = 36;
  const sh: [number, number] = [cx, cy - 36];
  const el: [number, number] = [sh[0] + Math.cos(j2) * L1, sh[1] + Math.sin(j2) * L1];
  const wr: [number, number] = [el[0] + Math.cos(j2 + j3) * L2, el[1] + Math.sin(j2 + j3) * L2];
  const tcp: [number, number] = [wr[0] + Math.cos(j2 + j3 + j5) * L3, wr[1] + Math.sin(j2 + j3 + j5) * L3];

  const color = (i: number) => faulty.includes(i) ? "var(--err)" : "var(--ok)";

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: "block" }}
    >
      <defs>
        <pattern id="ag1" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(120,180,200,.07)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width={width} height={height} fill="url(#ag1)" />
      <line x1="0" y1={cy} x2={width} y2={cy} stroke="rgba(74,222,128,.4)" strokeDasharray="4 3" strokeWidth="1" />
      <text x="6" y={cy - 4} fill="rgba(74,222,128,.6)" fontSize="9" fontFamily="JetBrains Mono">FLOOR · z=0</text>
      <rect x={cx - 16} y={cy - 8} width="32" height="8" fill="#1a2028" stroke="var(--border-2)" />
      <rect x={cx - 22} y={cy - 28} width="44" height="20" fill="#1a2028" stroke="var(--border-2)" />
      <circle cx={cx} cy={cy - 36} r="9" fill="#0d1117" stroke={color(0)} strokeWidth="1.5" />
      <text x={cx + 14} y={cy - 32} fill={color(0)} fontSize="9" fontFamily="JetBrains Mono">J1</text>
      <line x1={sh[0]} y1={sh[1]} x2={el[0]} y2={el[1]} stroke={color(1)} strokeWidth="6" strokeLinecap="round" opacity="0.75" />
      <line x1={sh[0]} y1={sh[1]} x2={el[0]} y2={el[1]} stroke={color(1)} strokeWidth="2" />
      <circle cx={el[0]} cy={el[1]} r="7" fill="#0d1117" stroke={color(2)} strokeWidth="1.5" />
      <text x={sh[0] + 8} y={sh[1] - 6} fill={color(1)} fontSize="9" fontFamily="JetBrains Mono">J2</text>
      <text x={el[0] + 10} y={el[1]} fill={color(2)} fontSize="9" fontFamily="JetBrains Mono">J3</text>
      <line x1={el[0]} y1={el[1]} x2={wr[0]} y2={wr[1]} stroke={color(3)} strokeWidth="5" strokeLinecap="round" opacity="0.75" />
      <line x1={el[0]} y1={el[1]} x2={wr[0]} y2={wr[1]} stroke={color(3)} strokeWidth="2" />
      <circle cx={wr[0]} cy={wr[1]} r="5" fill="#0d1117" stroke={color(4)} strokeWidth="1.5" />
      <text x={wr[0] + 8} y={wr[1] + 3} fill={color(4)} fontSize="9" fontFamily="JetBrains Mono">J4/5</text>
      <line x1={wr[0]} y1={wr[1]} x2={tcp[0]} y2={tcp[1]} stroke={color(5)} strokeWidth="3" />
      <circle cx={tcp[0]} cy={tcp[1]} r="4" fill="var(--magenta)" stroke="#06090d" strokeWidth="1.5" />
      <text x={tcp[0] + 6} y={tcp[1] - 4} fill="var(--magenta)" fontSize="9" fontFamily="JetBrains Mono">TCP</text>
      <text x="6" y="14" fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">VIEW · SIDE · base_link</text>
      <text x={width - 6} y="14" textAnchor="end" fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">6 DoF · UR-LIKE</text>
      <text x="6" y={height - 6} fill="rgba(120,180,200,.55)" fontSize="9" fontFamily="JetBrains Mono">SCALE 1:4</text>
    </svg>
  );
}
