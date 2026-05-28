// MISSIONS / TASKS: queue + simple Gantt.

import type { Robot } from "@/types";
import { Panel, Stat } from "@/components/common";

interface Props { fleet: Robot[]; }

export function TasksScreen({ fleet }: Props) {
  const queue = fleet.filter(r => r.status !== "OFFLINE").slice(0, 12);
  return (
    <div className="screen tasks">
      <div className="tasks-grid">
        <Panel title="QUEUE · PRIORITY" style={{ gridColumn: "1 / span 2", gridRow: "1" }} pad={false}>
          <div className="table-wrap small">
            <table className="dtable">
              <thead><tr><th>#</th><th>ROBOT</th><th>TASK</th><th>STATE</th><th>ETA</th></tr></thead>
              <tbody>
                {queue.map((r, i) => (
                  <tr key={r.id}>
                    <td className="mono">{String(i + 1).padStart(2, "0")}</td>
                    <td>{r.id}</td>
                    <td style={{ color: "var(--fg-mute)" }}>{r.task}</td>
                    <td style={{ color: "var(--ok)" }}>{r.status}</td>
                    <td className="mono">{r.cycleTime.toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="GANTT · LIVE" style={{ gridColumn: "1 / span 2", gridRow: "2" }}>
          <div className="gantt">
            <div className="gantt-axis">{[0,1,2,3,4,5,6,7,8,9].map(i => <div key={i} className="gantt-tick mono dim" style={{ fontSize: 9 }}>{i*5}s</div>)}</div>
            {queue.slice(0, 6).map((r, i) => (
              <div key={r.id} className="gantt-row">
                <div className="gantt-label">{r.id}</div>
                <div className="gantt-track">
                  <div className="gantt-bar" style={{ left: `${(i*7) % 40}%`, width: `${10 + r.cycleTime*2}%`, background: "var(--ok)" }} />
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="AVAILABILITY" style={{ gridColumn: "3", gridRow: "1 / span 2" }}>
          {fleet.slice(0, 14).map(r => (
            <div key={r.id} className="avail-row">
              <span className="mono" style={{ fontSize: 10, width: 70 }}>{r.id}</span>
              <span className="mono dim" style={{ fontSize: 9, flex: 1 }}>{r.task}</span>
              <span className="mono" style={{ fontSize: 10, color: r.status === "ACTIVE" ? "var(--ok)" : "var(--fg-mute)" }}>{r.status}</span>
            </div>
          ))}
        </Panel>

        <Panel title="STATS" style={{ gridColumn: "4", gridRow: "1" }}>
          <Stat label="QUEUED" value={queue.length} color="var(--ok)" />
          <Stat label="ACTIVE" value={fleet.filter(r => r.status === "ACTIVE").length} />
          <Stat label="FAULT" value={fleet.filter(r => r.status === "FAULT").length} color="var(--err)" />
        </Panel>

        <Panel title="NEW TASK" style={{ gridColumn: "4", gridRow: "2" }}>
          <div className="form-row"><span className="tag dim">NAME</span><input className="inp" placeholder="WELD-SEAM·V5" /></div>
          <div className="form-row"><span className="tag dim">ROBOT</span><input className="inp" placeholder="ARM-003" /></div>
          <button className="btn primary" style={{ width: "100%", marginTop: 6 }}>QUEUE</button>
        </Panel>
      </div>
    </div>
  );
}
