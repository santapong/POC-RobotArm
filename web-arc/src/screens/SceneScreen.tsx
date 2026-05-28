// SCENE — 3D viewer of the selected arm, larger viewport.

import type { Robot } from "@/types";
import { Panel, Stat } from "@/components/common";
import { Arm3D } from "@/components/three/Arm3D";
import { useUiStore } from "@/store/useUiStore";
import { useDocStore } from "@/store/useDocStore";
import { resolveRobot } from "@/lib/robots";

interface Props { robot: Robot | undefined; }

export function SceneScreen({ robot }: Props) {
  const autoRotate = useUiStore(s => s.tweaks.autoRotate3D);
  const showWorkspace = useUiStore(s => s.tweaks.showWorkspace);
  const robotId = useDocStore(s => s.doc.robotId);
  const activeRobot = resolveRobot(robotId);
  return (
    <div className="screen scene-arm">
      <Panel title={`SCENE · ${robot?.id ?? "—"} · ${activeRobot.name}`} pad={false} style={{ gridColumn: "1 / span 2", gridRow: "1 / span 2" }}>
        <div className="scene-3d">
          <Arm3D key={activeRobot.id} jointAngles={[0,-60,90,0,40,0]} width="100%" height="100%"
            reach={activeRobot.reach} robot={activeRobot}
            autoRotate={autoRotate} showWorkspace={showWorkspace} />
        </div>
      </Panel>
      <Panel title="ROBOT" style={{ gridColumn: "3", gridRow: "1" }}>
        <Stat label="ID" value={robot?.id ?? "—"} color="var(--ok)" />
        <Stat label="CALLSIGN" value={robot?.callsign ?? "—"} />
        <Stat label="TOOL" value={robot?.tool ?? "—"} />
        <Stat label="REACH" value={`${(robot?.reach ?? 0).toFixed(2)} m`} />
        <Stat label="PAYLOAD" value={`${(robot?.payload ?? 0).toFixed(1)} kg`} />
      </Panel>
      <Panel title="DH PARAMETERS" style={{ gridColumn: "4", gridRow: "1" }}>
        <table className="dhtable">
          <thead><tr><th>i</th><th>θ</th><th>d</th><th>a</th><th>α</th></tr></thead>
          <tbody>
            {[[1,"θ₁",0.163,0,90],[2,"θ₂",0,0.42,0],[3,"θ₃",0,0.34,0],[4,"θ₄",0.104,0,90],[5,"θ₅",0.085,0,-90],[6,"θ₆",0.082,0,0]].map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j}>{String(c)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
