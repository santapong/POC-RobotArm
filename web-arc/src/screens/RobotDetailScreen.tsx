// ROBOT detail: side-view, TCP pose, joint table, I/O bits, F/T.

import type { Robot } from "@/types";
import { Panel, Stat } from "@/components/common";
import { ArmSideView } from "@/components/three/ArmSideView";
import { jointStateFor } from "@/lib/fleet";

interface Props { robot: Robot | undefined; }

export function RobotDetailScreen({ robot }: Props) {
  const seed = parseInt(robot?.id.replace("ARM-", "") || "1", 10);
  const joints = jointStateFor(seed);
  return (
    <div className="screen robot">
      <div className="robot-grid">
        <Panel title="SIDE VIEW" pad={false}><ArmSideView jointAngles={joints.map(j => j.pos)} /></Panel>

        <Panel title="CURRENT TCP POSE · base_link">
          <div className="tcp-pose">
            <div><span className="tag dim">X</span><span className="mono">{robot?.tcp.x.toFixed(3)}</span></div>
            <div><span className="tag dim">Y</span><span className="mono">{robot?.tcp.y.toFixed(3)}</span></div>
            <div><span className="tag dim">Z</span><span className="mono">{robot?.tcp.z.toFixed(3)}</span></div>
            <div><span className="tag dim">RX</span><span className="mono">{robot?.tcp.rx.toFixed(1)}°</span></div>
            <div><span className="tag dim">RY</span><span className="mono">{robot?.tcp.ry.toFixed(1)}°</span></div>
            <div><span className="tag dim">RZ</span><span className="mono">{robot?.tcp.rz.toFixed(1)}°</span></div>
          </div>
          <hr className="hr" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <Stat label="TOOL" value={robot?.tool ?? "—"} />
            <Stat label="PAYLOAD" value={`${(robot?.payload ?? 0).toFixed(1)} kg`} />
            <Stat label="REACH" value={`${(robot?.reach ?? 0).toFixed(2)} m`} />
            <Stat label="TCP·v" value={`${(robot?.tcpSpeed ?? 0).toFixed(2)} m/s`} />
          </div>
        </Panel>

        <Panel title="JOINTS · STATE" pad={false}>
          <div className="table-wrap small">
            <table className="dtable">
              <thead><tr><th>J</th><th>POS</th><th>VEL</th><th>τ</th><th>°C</th><th>A</th></tr></thead>
              <tbody>
                {joints.map((j, i) => (
                  <tr key={i} className={j.err ? "row-err" : ""}>
                    <td style={{ color: "var(--ok)" }}>J{i + 1}</td>
                    <td>{j.pos.toFixed(1)}°</td>
                    <td>{j.vel.toFixed(0)}°/s</td>
                    <td>{j.torque.toFixed(1)}</td>
                    <td style={{ color: j.temp > 60 ? "var(--warn)" : "var(--fg-mute)" }}>{j.temp}</td>
                    <td>{j.current.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="DIGITAL I/O · 16+16">
          <div className="tag dim">DI 0-15</div>
          <div className="iogrid">{Array.from({ length: 16 }).map((_, i) => <div key={i} className={"iobit" + (i % 3 === 0 ? " on" : "")}>{i}</div>)}</div>
          <hr className="hr" />
          <div className="tag dim">DO 0-15</div>
          <div className="iogrid">{Array.from({ length: 16 }).map((_, i) => <div key={i} className={"iobit out" + (i % 5 === 0 ? " on" : "")}>{i}</div>)}</div>
        </Panel>

        <Panel title="F/T SENSOR">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <Stat label="FX" value="2.3 N" />
            <Stat label="FY" value="-0.4 N" />
            <Stat label="FZ" value="11.7 N" />
            <Stat label="TX" value="0.18 Nm" />
            <Stat label="TY" value="0.04 Nm" />
            <Stat label="TZ" value="-0.22 Nm" />
          </div>
        </Panel>

        <Panel title="STATUS">
          <Stat label="STATUS" value={robot?.status ?? "—"} color={robot?.status === "ACTIVE" ? "var(--ok)" : "var(--fg-mute)"} />
          <Stat label="FW" value={robot?.fw ?? "—"} />
          <Stat label="UPTIME" value={`${robot?.uptime ?? 0} h`} />
          <Stat label="TASKS·24H" value={`${robot?.tasksDone ?? 0}`} />
          <Stat label="FAULTS·24H" value={`${robot?.faults24h ?? 0}`} color={(robot?.faults24h ?? 0) > 0 ? "var(--warn)" : undefined} />
        </Panel>
      </div>
    </div>
  );
}
