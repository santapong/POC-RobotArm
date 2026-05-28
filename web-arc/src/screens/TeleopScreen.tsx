// Teleop / pendant: Cartesian + joint jog, 3D arm, gripper + safety strip.

import { useState } from "react";
import type { Robot } from "@/types";
import { Panel, SplitScreen, Stat, type SplitNode } from "@/components/common";
import { Arm3D } from "@/components/three/Arm3D";
import { jointStateFor } from "@/lib/fleet";
import { useDocStore } from "@/store/useDocStore";
import { resolveRobot } from "@/lib/robots";

interface Props { robot: Robot | undefined; }

export function TeleopScreen({ robot }: Props) {
  const [coord, setCoord] = useState<"BASE" | "TOOL" | "WORLD" | "USER">("BASE");
  const [step, setStep] = useState(1);
  const [speed, setSpeed] = useState(20);
  const [angles, setAngles] = useState<number[]>([0, -60, 90, 0, 40, 0]);
  const seed = parseInt(robot?.id.replace("ARM-", "") || "1", 10);
  const joints = jointStateFor(seed);
  const robotId = useDocStore(s => s.doc.robotId);
  const activeRobot = resolveRobot(robotId);

  const jog = (i: number, dir: 1 | -1) => setAngles(a => a.map((v, k) => k === i ? +(v + dir * step).toFixed(2) : v));

  const armPanel = (
    <Panel title={`TELEOP · ${robot?.id ?? "—"}`} pad={false}>
      <div className="teleop-3d">
        <Arm3D key={activeRobot.id} jointAngles={angles} width="100%" height="100%"
          reach={activeRobot.reach} robot={activeRobot} />
      </div>
    </Panel>
  );

  const cartPanel = (
    <Panel title="CARTESIAN JOG · TCP">
      <div style={{ display: "flex", gap: 4, marginBottom: 8, flexWrap: "wrap" }}>
        {(["BASE","TOOL","WORLD","USER"] as const).map(c =>
          <button key={c} className={"chip" + (coord === c ? " on" : "")} onClick={() => setCoord(c)}>{c}</button>
        )}
      </div>
      <div className="jogpad">
        {(["X","Y","Z","RX","RY","RZ"] as const).map((axis) => (
          <div key={axis} className="jogrow">
            <span className="mono" style={{ width: 28, color: "var(--fg-mute)", fontSize: 11 }}>{axis}</span>
            <button className="jogbtn small">−</button>
            <button className="jogbtn small">+</button>
            <span className="mono dim" style={{ fontSize: 10, marginLeft: 6 }}>
              {axis === "X" ? robot?.tcp.x.toFixed(3) : axis === "Y" ? robot?.tcp.y.toFixed(3) : axis === "Z" ? robot?.tcp.z.toFixed(3) : "0.0"}
            </span>
          </div>
        ))}
      </div>
      <hr className="hr" />
      <div className="form-row" style={{ flexDirection: "row", gap: 8 }}>
        <span className="tag dim">STEP</span>
        {[0.1, 1, 5, 10, 50].map(s => (
          <button key={s} className={"chip" + (step === s ? " on" : "")} onClick={() => setStep(s)}>{s}</button>
        ))}
      </div>
      <div className="form-row" style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
        <span className="tag dim">SPEED</span>
        <input type="range" min={1} max={100} value={speed} onChange={e => setSpeed(+e.target.value)} className="slider" />
        <span className="mono" style={{ fontSize: 10 }}>{speed}%</span>
      </div>
    </Panel>
  );

  const jointPanel = (
    <Panel title="JOINT JOG · J1-J6">
      {joints.map((j, i) => (
        <div key={i} className="jjog">
          <span className="mono" style={{ width: 80, fontSize: 11, color: "var(--ok)" }}>{j.name}</span>
          <button className="jogbtn small" onClick={() => jog(i, -1)}>−</button>
          <button className="jogbtn small" onClick={() => jog(i, +1)}>+</button>
          <span className="mono" style={{ fontSize: 10, marginLeft: 6 }}>{angles[i].toFixed(1)}°</span>
          <span className="mono dim" style={{ fontSize: 9, marginLeft: "auto" }}>{j.current}A</span>
        </div>
      ))}
    </Panel>
  );

  const toolPanel = (
    <Panel title="TOOL · GRIPPER">
      <Stat label="TOOL" value={robot?.tool ?? "—"} color="var(--info)" />
      <hr className="hr" />
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {["OPEN", "CLOSE", "10mm", "50mm", "100mm"].map(b => <button key={b} className="chip">{b}</button>)}
      </div>
    </Panel>
  );

  const safetyPanel = (
    <Panel title="SAFETY · INTERLOCKS">
      {(["WORKSPACE","FORCE LIMIT","SINGULARITY","HUMAN-PROX","DEADMAN","E-STOP"] as const).map(k => (
        <div key={k} className="check-row">
          <span className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>✓</span>
          <span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span>
          <span className="mono" style={{ fontSize: 10, color: "var(--ok)", marginLeft: "auto" }}>OK</span>
        </div>
      ))}
      <hr className="hr" />
      <button className="btn danger" style={{ width: "100%" }}>⬣ E-STOP</button>
    </Panel>
  );

  const layout: SplitNode = {
    type: "split", direction: "v", key: "root",
    children: [
      { type: "split", direction: "h", key: "top", size: 60, children: [
        { type: "leaf", key: "arm", size: 65, content: armPanel },
        { type: "leaf", key: "cart", size: 35, content: cartPanel },
      ]},
      { type: "split", direction: "h", key: "bot", size: 40, children: [
        { type: "leaf", key: "joint", size: 40, content: jointPanel },
        { type: "leaf", key: "tool", size: 30, content: toolPanel },
        { type: "leaf", key: "safety", size: 30, content: safetyPanel },
      ]},
    ],
  };

  return <SplitScreen id="teleop" className="screen teleop-arm" node={layout} />;
}
