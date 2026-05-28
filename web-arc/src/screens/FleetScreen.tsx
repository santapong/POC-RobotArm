// FLEET: factory cell grid + selected-robot rail + alerts.

import type { Alert, Robot } from "@/types";
import { Panel, Stat, StatusDot } from "@/components/common";
import { useUiStore } from "@/store/useUiStore";

interface Props { fleet: Robot[]; alerts: Alert[]; }

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: "var(--ok)", IDLE: "var(--fg-mute)", TELEOP: "var(--magenta)",
  FAULT: "var(--err)", OFFLINE: "var(--off)",
};

export function FleetScreen({ fleet, alerts }: Props) {
  const selectedId = useUiStore(s => s.selectedId);
  const setSelectedId = useUiStore(s => s.setSelectedId);
  const setScreen = useUiStore(s => s.setScreen);
  const selected = fleet.find(r => r.id === selectedId);

  return (
    <div className="screen fleet">
      <Panel title="FACTORY · CELL MAP" pad={false} style={{ gridColumn: "screen-l-start", gridRow: "1 / span 1" }}>
        <div className="cells">
          {fleet.map(r => (
            <button key={r.id} className={"cell st-" + r.status + (r.id === selectedId ? " sel" : "")}
              style={{ ["--sc" as string]: STATUS_COLOR[r.status] }}
              onClick={() => setSelectedId(r.id)}>
              <div className="cell-hd">
                <span className="cell-id">{r.id}</span>
                <StatusDot status={r.status} size={6} />
              </div>
              <div className="cell-body">
                <div className="cell-meta">
                  <span className="mono" style={{ fontSize: 9, color: "var(--fg-mute)" }}>{r.callsign}</span>
                  <span className="mono" style={{ fontSize: 8, color: "var(--dim)" }}>{r.tool}</span>
                </div>
              </div>
              <div className="cell-task">{r.task}</div>
              <div className="cell-foot mono">
                <span style={{ color: "var(--fg-mute)" }}>{r.cpu}%cpu</span>
                <span style={{ color: r.temp > 60 ? "var(--warn)" : "var(--fg-mute)" }}>{r.temp}°C</span>
              </div>
            </button>
          ))}
        </div>
      </Panel>

      <Panel title="ROSTER" pad={false} style={{ gridColumn: "screen-l-start", gridRow: "2" }}>
        <div className="table-wrap">
          <table className="dtable">
            <thead><tr><th>ID</th><th>STATUS</th><th>TASK</th><th>BATT</th><th>LAT</th></tr></thead>
            <tbody>
              {fleet.map(r => (
                <tr key={r.id} className={r.id === selectedId ? "sel" : ""} onClick={() => setSelectedId(r.id)}>
                  <td>{r.id}</td>
                  <td style={{ color: STATUS_COLOR[r.status] }}>{r.status}</td>
                  <td style={{ color: "var(--fg-mute)" }}>{r.task}</td>
                  <td>{r.battery}%</td>
                  <td>{r.latencyMs ?? "—"} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="SELECTED" style={{ gridColumn: "screen-r-start", gridRow: "1" }}>
        {selected ? (
          <>
            <Stat label="ID" value={selected.id} color="var(--ok)" />
            <Stat label="CALLSIGN" value={selected.callsign} />
            <Stat label="ZONE" value={selected.zone} />
            <Stat label="TASK" value={selected.task} sub={`uptime ${selected.uptime}h`} />
            <Stat label="TOOL" value={selected.tool} />
            <hr className="hr" />
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button className="btn" onClick={() => setScreen("robot")}>DETAIL</button>
              <button className="btn" onClick={() => setScreen("teleop")}>TELEOP</button>
              <button className="btn" onClick={() => setScreen("scene")}>SCENE</button>
            </div>
          </>
        ) : <div className="mono dim">No robot selected.</div>}
      </Panel>

      <Panel title="ALERTS" pad={false} style={{ gridColumn: "screen-r-start", gridRow: "2" }}>
        <div className="alerts">
          {alerts.map((a, i) => (
            <div key={i} className="alert">
              <span className="mono dim" style={{ fontSize: 9 }}>{a.ts}</span>
              <span className={"sev sev-" + a.sev}>{a.sev}</span>
              <span className="mono" style={{ fontSize: 10, color: "var(--info)" }}>{a.src}</span>
              <span className="mono" style={{ fontSize: 10 }}>{a.msg}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
