// ANALYTICS — KPI cards + horizontal bars + heatmap.

import type { Robot } from "@/types";
import { Panel, SplitScreen, Stat, Bar, Sparkline, type SplitNode } from "@/components/common";
import { useSeries } from "@/hooks/useSeries";

interface Props { fleet: Robot[]; }

export function AnalyticsScreen({ fleet }: Props) {
  const throughput = useSeries(11, 60, 60, 30);
  const energy = useSeries(22, 60, 45, 20);
  const active = fleet.filter(r => r.status === "ACTIVE").length;
  const totalDone = fleet.reduce((a, b) => a + b.tasksDone, 0);

  const kpis: { key: string; title: string; el: JSX.Element }[] = [
    { key: "active", title: "ACTIVE",    el: <Stat label="ROBOTS" value={`${active}/${fleet.length}`} color="var(--ok)" /> },
    { key: "done",   title: "TASKS·24H", el: <Stat label="COMPLETED" value={totalDone} /> },
    { key: "up",     title: "UPTIME",    el: <Stat label="AVG" value="98.7%" color="var(--ok)" /> },
    { key: "cycle",  title: "CYCLE-TIME",el: <Stat label="MEDIAN" value="6.4 s" /> },
    { key: "fault",  title: "FAULTS·24H",el: <Stat label="OPEN" value={fleet.reduce((a, b) => a + b.faults24h, 0)} color="var(--warn)" /> },
    { key: "energy", title: "ENERGY",    el: <Stat label="kWh" value="142.3" /> },
  ];

  const throughputPanel = (
    <Panel title="THROUGHPUT · TASKS/MIN">
      <Sparkline data={throughput} width={400} height={70} />
    </Panel>
  );

  const energyPanel = (
    <Panel title="ENERGY · kW">
      <Sparkline data={energy} width={400} height={70} color="var(--warn)" />
    </Panel>
  );

  const utilPanel = (
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
  );

  const heatPanel = (
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
  );

  const layout: SplitNode = {
    type: "split", direction: "v", key: "root",
    children: [
      { type: "split", direction: "h", key: "kpi", size: 18, children: kpis.map(k => ({
        type: "leaf" as const, key: k.key, size: 100 / kpis.length, content: <Panel title={k.title}>{k.el}</Panel>,
      })) },
      { type: "split", direction: "h", key: "charts", size: 82, children: [
        { type: "split", direction: "v", key: "L", size: 50, children: [
          { type: "leaf", key: "thru", size: 40, content: throughputPanel },
          { type: "leaf", key: "util", size: 60, content: utilPanel },
        ]},
        { type: "split", direction: "v", key: "R", size: 50, children: [
          { type: "leaf", key: "energy", size: 40, content: energyPanel },
          { type: "leaf", key: "heat", size: 60, content: heatPanel },
        ]},
      ]},
    ],
  };

  return <SplitScreen id="analytics" className="screen analytics" node={layout} />;
}
