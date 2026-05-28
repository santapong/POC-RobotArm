// SCENE — full-bleed 3D viewer of the selected arm with the joint info and
// DH parameters as draggable floating panels. The user can move and resize
// each info panel; close them via ✕ and re-open from the small chip rail in
// the top-left corner. The 3D itself stays full-viewport and resizes
// responsively (Arm3D already has a ResizeObserver on its mount div).

import { useState } from "react";
import type { Robot } from "@/types";
import { FloatingPanel, Stat } from "@/components/common";
import { Arm3D } from "@/components/three/Arm3D";
import { useUiStore } from "@/store/useUiStore";
import { useDocStore } from "@/store/useDocStore";
import { resolveRobot } from "@/lib/robots";

interface Props { robot: Robot | undefined; }

type PanelKey = "robot" | "dh";

export function SceneScreen({ robot }: Props) {
  const autoRotate = useUiStore(s => s.tweaks.autoRotate3D);
  const showWorkspace = useUiStore(s => s.tweaks.showWorkspace);
  const robotId = useDocStore(s => s.doc.robotId);
  const activeRobot = resolveRobot(robotId);

  // Which floating panels are visible. Both shown by default; ✕ hides them
  // and the corner chip rail brings them back.
  const [open, setOpen] = useState<Record<PanelKey, boolean>>({ robot: true, dh: true });
  const toggle = (k: PanelKey) => setOpen(o => ({ ...o, [k]: !o[k] }));
  const close = (k: PanelKey) => () => setOpen(o => ({ ...o, [k]: false }));

  return (
    <div className="screen scene-stage">
      <div className="scene-3d-stage">
        <Arm3D
          key={activeRobot.id}
          jointAngles={[0, -60, 90, 0, 40, 0]}
          width="100%"
          height="100%"
          reach={activeRobot.reach}
          robot={activeRobot}
          autoRotate={autoRotate}
          showWorkspace={showWorkspace}
        />
      </div>

      {/* corner chip rail — toggle visibility of each floating panel. The
          chips also show which panels are currently open so the user can
          orient. */}
      <div className="float-toggle-rail">
        <button
          className={"chip" + (open.robot ? " on" : "")}
          onClick={() => toggle("robot")}
        >
          ◉ ROBOT
        </button>
        <button
          className={"chip" + (open.dh ? " on" : "")}
          onClick={() => toggle("dh")}
        >
          Σ DH PARAMS
        </button>
      </div>

      {open.robot && (
        <FloatingPanel
          title={`ROBOT · ${robot?.id ?? "—"}`}
          storageKey="scene.robot"
          defaultPreset="top-right"
          defaultSize={{ w: 240, h: 280 }}
          onClose={close("robot")}
        >
          <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
            <Stat label="ID" value={robot?.id ?? "—"} color="var(--ok)" />
            <Stat label="CALLSIGN" value={robot?.callsign ?? "—"} />
            <Stat label="MODEL" value={`${activeRobot.manufacturer} ${activeRobot.name}`} />
            <Stat label="TOOL" value={robot?.tool ?? "—"} />
            <Stat label="REACH" value={`${activeRobot.reach.toFixed(2)} m`} />
            <Stat label="PAYLOAD" value={`${activeRobot.payload.toFixed(1)} kg`} />
            <Stat label="DoF" value={activeRobot.dof} />
          </div>
        </FloatingPanel>
      )}

      {open.dh && (
        <FloatingPanel
          title="DH PARAMETERS"
          storageKey="scene.dh"
          defaultPreset="bottom-right"
          defaultSize={{ w: 280, h: 240 }}
          onClose={close("dh")}
        >
          <div style={{ padding: 10 }}>
            <table className="dhtable">
              <thead><tr><th>i</th><th>θ</th><th>d</th><th>a</th><th>α</th></tr></thead>
              <tbody>
                {[
                  [1, "θ₁", 0.163, 0,     90],
                  [2, "θ₂", 0,     0.42,  0],
                  [3, "θ₃", 0,     0.34,  0],
                  [4, "θ₄", 0.104, 0,     90],
                  [5, "θ₅", 0.085, 0,    -90],
                  [6, "θ₆", 0.082, 0,     0],
                ].map((r, i) => (
                  <tr key={i}>{r.map((c, j) => <td key={j}>{String(c)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </FloatingPanel>
      )}
    </div>
  );
}
