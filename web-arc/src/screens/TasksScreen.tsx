// MISSIONS / TASKS: queue + simple Gantt.

import type { Robot } from "@/types";
import { Panel, SplitScreen, Stat, type SplitNode } from "@/components/common";

interface Props { fleet: Robot[]; }

export function TasksScreen({ fleet }: Props) {
  const queue = fleet.filter(r => r.status !== "OFFLINE").slice(0, 12);

  const queuePanel = (
    <Panel title="QUEUE · PRIORITY" pad={false}>
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
  );

  const ganttPanel = (
    <Panel title="GANTT · LIVE">
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
  );

  const availPanel = (
    <Panel title="AVAILABILITY">
      {fleet.slice(0, 14).map(r => (
        <div key={r.id} className="avail-row">
          <span className="mono" style={{ fontSize: 10, width: 70 }}>{r.id}</span>
          <span className="mono dim" style={{ fontSize: 9, flex: 1 }}>{r.task}</span>
          <span className="mono" style={{ fontSize: 10, color: r.status === "ACTIVE" ? "var(--ok)" : "var(--fg-mute)" }}>{r.status}</span>
        </div>
      ))}
    </Panel>
  );

  const statsPanel = (
    <Panel title="STATS">
      <Stat label="QUEUED" value={queue.length} color="var(--ok)" />
      <Stat label="ACTIVE" value={fleet.filter(r => r.status === "ACTIVE").length} />
      <Stat label="FAULT" value={fleet.filter(r => r.status === "FAULT").length} color="var(--err)" />
    </Panel>
  );

  const newTaskPanel = (
    <Panel title="NEW TASK">
      <div className="form-row"><span className="tag dim">NAME</span><input className="inp" placeholder="WELD-SEAM·V5" /></div>
      <div className="form-row"><span className="tag dim">ROBOT</span><input className="inp" placeholder="ARM-003" /></div>
      <button className="btn primary" style={{ width: "100%", marginTop: 6 }}>QUEUE</button>
    </Panel>
  );

  const layout: SplitNode = {
    type: "split", direction: "h", key: "root",
    children: [
      { type: "split", direction: "v", key: "main", size: 55, children: [
        { type: "leaf", key: "queue", size: 50, content: queuePanel },
        { type: "leaf", key: "gantt", size: 50, content: ganttPanel },
      ]},
      { type: "leaf", key: "avail", size: 25, content: availPanel },
      { type: "split", direction: "v", key: "right", size: 20, children: [
        { type: "leaf", key: "stats", size: 40, content: statsPanel },
        { type: "leaf", key: "new", size: 60, content: newTaskPanel },
      ]},
    ],
  };

  return <SplitScreen id="tasks" className="screen tasks" node={layout} />;
}
