// CONFIG — robot identity, PID per joint, safety limits, sensors, OTA.

import type { Robot } from "@/types";
import { Panel, Stat } from "@/components/common";
import { JOINTS6 } from "@/lib/fleet";

interface Props { robot: Robot | undefined; }

export function SettingsScreen({ robot }: Props) {
  return (
    <div className="screen settings">
      <div className="settings-grid">
        <Panel title="IDENTITY">
          <div className="form-row"><span className="tag dim">CALLSIGN</span><input className="inp" defaultValue={robot?.callsign ?? ""} /></div>
          <div className="form-row"><span className="tag dim">HOSTNAME</span><input className="inp" defaultValue={(robot?.id ?? "").toLowerCase()} /></div>
          <div className="form-row"><span className="tag dim">CELL</span><input className="inp" defaultValue={robot?.zone ?? ""} /></div>
          <Stat label="FIRMWARE" value={robot?.fw ?? "—"} />
        </Panel>

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

        <Panel title="TCP CALIBRATION">
          <div className="tag dim">METHOD</div>
          <div style={{ display: "flex", gap: 4 }}>
            {["4-POINT","SPHERE","FREE-DRIVE"].map(m => <button key={m} className="chip">{m}</button>)}
          </div>
          <hr className="hr" />
          <Stat label="CURRENT TCP · TOOL FRAME" value="[0, 0, 0.158, 0, 0, 0]" />
          <button className="btn primary" style={{ width: "100%", marginTop: 6 }}>RUN CALIB</button>
        </Panel>

        <Panel title="SENSORS">
          {["CELL CAM WIDE","CELL CAM TELE","TOOL CAM","F/T","LIGHT-CURTAIN","LASER-SCANNER","TORQUE EST","VIBRATION"].map((s, i) => (
            <div key={s} className="form-row" style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <span className="tag dim">{s}</span>
              <button className={"switch" + (i % 3 !== 0 ? " on" : "")}><span className="switch-thumb" /></button>
            </div>
          ))}
        </Panel>

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
      </div>
    </div>
  );
}
