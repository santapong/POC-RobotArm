// ANALYTICS — KPI cards + horizontal bars + heatmap.

import type { Robot } from "@/types";
import { Panel, Stat, Bar, Sparkline } from "@/components/common";
import { useSeries } from "@/hooks/useSeries";

interface Props { fleet: Robot[]; }

export function AnalyticsScreen({ fleet }: Props) {
  const throughput = useSeries(11, 60, 60, 30);
  const energy = useSeries(22, 60, 45, 20);
  const active = fleet.filter(r => r.status === "ACTIVE").length;
  const totalDone = fleet.reduce((a, b) => a + b.tasksDone, 0);
  return (
    <div className="screen analytics">
      <div className="kpi-row">
        <Panel title="ACTIVE"><Stat label="ROBOTS" value={`${active}/${fleet.length}`} color="var(--ok)" /></Panel>
        <Panel title="TASKS·24H"><Stat label="COMPLETED" value={totalDone} /></Panel>
        <Panel title="UPTIME"><Stat label="AVG" value="98.7%" color="var(--ok)" /></Panel>
        <Panel title="CYCLE-TIME"><Stat label="MEDIAN" value="6.4 s" /></Panel>
        <Panel title="FAULTS·24H"><Stat label="OPEN" value={fleet.reduce((a, b) => a + b.faults24h, 0)} color="var(--warn)" /></Panel>
        <Panel title="ENERGY"><Stat label="kWh" value="142.3" /></Panel>
      </div>
      <div className="analytics-grid">
        <Panel title="THROUGHPUT · TASKS/MIN">
          <Sparkline data={throughput} width={400} height={70} />
        </Panel>
        <Panel title="ENERGY · kW">
          <Sparkline data={energy} width={400} height={70} color="var(--warn)" />
        </Panel>
        <Panel title="UTILIZATION · BY CELL">
          <div className="hbars">
            {fleet.slice(0, 10).map(r => (
              <div key={r.id} className="hbar-row">
                <span className="mono" style={{ width: 70, fontSize: 10 }}>{r.id}</span>
                <Bar value={r.cpu} max={100} color={r.cpu > 75 ? "var(--warn)" : "var(--ok)"} height={6} />
                <span className="mono dim" style={{ fontSize: 10, width: 36 }}>{r.cpu}%</span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="JOINT-FAULT HEATMAP">
          <div className="heatmap heatmap-6">
            {Array.from({ length: 18 }).map((_, i) => {
              const n = (i * 13) % 7;
              const c = n === 0 ? "var(--ok)" : n < 3 ? "var(--info)" : n < 5 ? "var(--warn)" : "var(--err)";
              return (
                <div key={i} className="heat-cell" style={{ background: c + "22", borderColor: c }}>
                  <span className="tag dim" style={{ fontSize: 9 }}>J{(i % 6) + 1}</span>
                  <span className="mono" style={{ fontSize: 11, color: c }}>{n}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}
