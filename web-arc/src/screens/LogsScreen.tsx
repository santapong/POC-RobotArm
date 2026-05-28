// LOGS — streaming alert log + topic rates + ROS-style diagnostics tree.

import type { Alert } from "@/types";
import { Panel, SplitScreen, type SplitNode } from "@/components/common";

interface Props { alerts: Alert[]; }

export function LogsScreen({ alerts }: Props) {
  const streamPanel = (
    <Panel title="ALERT STREAM" pad={false}
      right={<input className="inp" placeholder="grep ›" style={{ width: 160 }} />}>
      <div className="logstream">
        {alerts.concat(alerts).concat(alerts).map((a, i) => (
          <div key={i} className="logline">
            <span className="mono dim" style={{ fontSize: 10 }}>{a.ts}</span>
            <span className={"sev sev-" + a.sev}>{a.sev}</span>
            <span className="mono" style={{ fontSize: 10, color: "var(--info)" }}>{a.src}</span>
            <span className="mono" style={{ fontSize: 10 }}>{a.msg}</span>
          </div>
        ))}
      </div>
    </Panel>
  );

  const ratesPanel = (
    <Panel title="TOPIC RATES · ROS2">
      {[
        ["/tcp/pose", "200 Hz", "var(--ok)"],
        ["/joints/state", "500 Hz", "var(--ok)"],
        ["/ft_sensor", "1000 Hz", "var(--ok)"],
        ["/io/digital", "50 Hz", "var(--info)"],
        ["/program/state", "10 Hz", "var(--info)"],
        ["/diagnostics", "1 Hz", "var(--fg-mute)"],
      ].map(([t, r, c]) => (
        <div key={t} className="topic-row">
          <span className="mono" style={{ fontSize: 10 }}>{t}</span>
          <span className="mono" style={{ fontSize: 10, color: c }}>{r}</span>
        </div>
      ))}
    </Panel>
  );

  const diagPanel = (
    <Panel title="DIAGNOSTICS">
      <div className="diag-tree">
        {[
          ["controller_manager", "OK"],
          ["  joint_state_broadcaster", "OK"],
          ["  scaled_joint_trajectory_controller", "OK"],
          ["ur_robot_driver", "OK"],
          ["  rtde_communication", "OK"],
          ["  dashboard_client", "WARN"],
          ["vision_pipeline", "OK"],
          ["safety_monitor", "OK"],
        ].map(([k, s]) => (
          <div key={k} className="diag-row">
            <span className={"sev sev-" + s}>{s}</span>
            <span className="mono" style={{ fontSize: 10 }}>{k}</span>
          </div>
        ))}
      </div>
    </Panel>
  );

  const layout: SplitNode = {
    type: "split", direction: "h", key: "root",
    children: [
      { type: "leaf", key: "stream", size: 55, content: streamPanel },
      { type: "split", direction: "v", key: "right", size: 45, children: [
        { type: "leaf", key: "rates", size: 50, content: ratesPanel },
        { type: "leaf", key: "diag", size: 50, content: diagPanel },
      ]},
    ],
  };

  return <SplitScreen id="logs" className="screen logs" node={layout} />;
}
