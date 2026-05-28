// CONFIG — robot identity, PID per joint, safety limits, sensors, OTA.

import type { Robot } from "@/types";
import { Panel, SplitScreen, Stat, type SplitNode } from "@/components/common";
import { JOINTS6 } from "@/lib/fleet";
import { useDocStore } from "@/store/useDocStore";
import { resolveRobot } from "@/lib/robots";

interface Props { robot: Robot | undefined; }

export function SettingsScreen({ robot }: Props) {
  const robotId = useDocStore(s => s.doc.robotId);
  const model = resolveRobot(robotId);

  const identityPanel = (
    <Panel title="IDENTITY">
      <div className="form-row"><span className="tag dim">CALLSIGN</span><input className="inp" defaultValue={robot?.callsign ?? ""} /></div>
      <div className="form-row"><span className="tag dim">HOSTNAME</span><input className="inp" defaultValue={(robot?.id ?? "").toLowerCase()} /></div>
      <div className="form-row"><span className="tag dim">CELL</span><input className="inp" defaultValue={robot?.zone ?? ""} /></div>
      <Stat label="FIRMWARE" value={robot?.fw ?? "—"} />
    </Panel>
  );

  const robotModelPanel = (
    <Panel title={`ROBOT · ${model.manufacturer} ${model.name}`}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <Stat label="PAYLOAD" value={`${model.payload} kg`} color="var(--ok)" />
        <Stat label="REACH" value={`${(model.reach * 1000).toFixed(0)} mm`} />
        <Stat label="DoF" value={model.dof} />
        <Stat label="MAX TCP" value={`${model.maxTcpSpeed.toFixed(2)} m/s`} />
      </div>
      <hr className="hr" />
      <div className="tag dim">JOINT LIMITS · °</div>
      {model.jointLimits.map(([lo, hi], i) => (
        <div key={i} className="form-row" style={{ flexDirection: "row", gap: 8 }}>
          <span className="mono" style={{ width: 30, fontSize: 10, color: "var(--ok)" }}>J{i + 1}</span>
          <span className="mono dim" style={{ fontSize: 10 }}>{lo} … {hi}</span>
          <span className="mono dim" style={{ fontSize: 10, marginLeft: "auto" }}>{model.maxJointVel[i]}°/s</span>
        </div>
      ))}
      <hr className="hr" />
      <div className="tag dim">LINK LENGTHS · m (schematic)</div>
      <div className="mono dim" style={{ fontSize: 10 }}>
        base {model.links.baseHeight.toFixed(3)} · upper {model.links.upperArm.toFixed(3)} · fore {model.links.forearm.toFixed(3)} · wrist {model.links.wristOffset.toFixed(3)} · flange {model.links.flangeOffset.toFixed(3)}
      </div>
    </Panel>
  );

  const controlPanel = (
    <Panel title="CONTROL · PID PER JOINT">
      {JOINTS6.map(([name], i) => (
        <div key={i} className="pid-row">
          <span className="mono" style={{ width: 90, fontSize: 10, color: "var(--ok)" }}>{name}</span>
          <input className="inp mono" style={{ width: 60 }} defaultValue="24.4" />
          <input className="inp mono" style={{ width: 60 }} defaultValue="0.18" />
          <input className="inp mono" style={{ width: 60 }} defaultValue="1.92" />
        </div>
      ))}
      <button className="btn primary" style={{ width: "100%", marginTop: 6 }}>APPLY · LIVE</button>
    </Panel>
  );

  const safetyPanel = (
    <Panel title="SAFETY · LIMITS">
      {[
        ["MAX TCP VELOCITY", "1.5 m/s"],
        ["MAX TCP ACCEL", "5.0 m/s²"],
        ["MAX JOINT VEL", "180 °/s"],
        ["MAX TORQUE", "32 N·m"],
        ["FORCE LIMIT", "150 N"],
        ["HUMAN STOP-DIST", "0.8 m"],
        ["GEOFENCE·X", "±1.2 m"],
        ["GEOFENCE·Z", "−0.5..1.6 m"],
      ].map(([k, v]) => (
        <div key={k} className="form-row" style={{ flexDirection: "row", gap: 8 }}>
          <span className="tag dim" style={{ width: 140 }}>{k}</span>
          <input className="inp mono" defaultValue={v} />
        </div>
      ))}
    </Panel>
  );

  const tcpPanel = (
    <Panel title="TCP CALIBRATION">
      <div className="tag dim">METHOD</div>
      <div style={{ display: "flex", gap: 4 }}>
        {["4-POINT","SPHERE","FREE-DRIVE"].map(m => <button key={m} className="chip">{m}</button>)}
      </div>
      <hr className="hr" />
      <Stat label="CURRENT TCP · TOOL FRAME" value="[0, 0, 0.158, 0, 0, 0]" />
      <button className="btn primary" style={{ width: "100%", marginTop: 6 }}>RUN CALIB</button>
    </Panel>
  );

  const sensorsPanel = (
    <Panel title="SENSORS">
      {["CELL CAM WIDE","CELL CAM TELE","TOOL CAM","F/T","LIGHT-CURTAIN","LASER-SCANNER","TORQUE EST","VIBRATION"].map((s, i) => (
        <div key={s} className="form-row" style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <span className="tag dim">{s}</span>
          <button className={"switch" + (i % 3 !== 0 ? " on" : "")}><span className="switch-thumb" /></button>
        </div>
      ))}
    </Panel>
  );

  const otaPanel = (
    <Panel title="OTA · DEPLOYMENT">
      <Stat label="CHANNEL" value="STABLE" color="var(--ok)" />
      <Stat label="CURRENT" value={robot?.fw ?? "—"} />
      <Stat label="AVAILABLE" value="ARC-5.0.1" color="var(--info)" />
      <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <button className="btn primary">STAGE</button>
        <button className="btn">ROLL BACK</button>
        <button className="btn danger">REBOOT</button>
      </div>
    </Panel>
  );

  const layout: SplitNode = {
    type: "split", direction: "h", key: "root",
    children: [
      { type: "split", direction: "v", key: "col1", size: 33, children: [
        { type: "leaf", key: "identity", size: 35, content: identityPanel },
        { type: "leaf", key: "safety", size: 65, content: safetyPanel },
      ]},
      { type: "split", direction: "v", key: "col2", size: 34, children: [
        { type: "leaf", key: "robot", size: 65, content: robotModelPanel },
        { type: "leaf", key: "tcp", size: 35, content: tcpPanel },
      ]},
      { type: "split", direction: "v", key: "col3", size: 33, children: [
        { type: "leaf", key: "control", size: 40, content: controlPanel },
        { type: "leaf", key: "sensors", size: 32, content: sensorsPanel },
        { type: "leaf", key: "ota", size: 28, content: otaPanel },
      ]},
    ],
  };

  return <SplitScreen id="settings" className="screen settings" node={layout} />;
}
