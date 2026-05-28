// ROBOT page (was FLEET). The selected robot's live 3D arm fills the entire
// screen; everything else — factory cell map, roster, alerts, deep inspect
// data, stats, jump-to-screen actions — lives on a right-edge icon rail
// modelled on AutoCAD's tool palette. Click an icon to slide a flyout in
// over the 3D; click the same icon (or the X) to slide it back out. The 3D
// itself never reflows.

import { useMemo, useState } from "react";
import type { Alert, Robot } from "@/types";
import { Panel, Stat, StatusDot } from "@/components/common";
import { Arm3D } from "@/components/three/Arm3D";
import { jointStateFor } from "@/lib/fleet";
import { resolveRobot } from "@/lib/robots";
import { useDocStore } from "@/store/useDocStore";
import { useUiStore, type Screen } from "@/store/useUiStore";

interface Props { fleet: Robot[]; alerts: Alert[]; }

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: "var(--ok)", IDLE: "var(--fg-mute)", TELEOP: "var(--magenta)",
  FAULT: "var(--err)", OFFLINE: "var(--off)",
};

type FlyoutKey = "factory" | "roster" | "alerts" | "inspect" | "stats";
const FLYOUT_TITLE: Record<FlyoutKey, string> = {
  factory: "FACTORY · CELL MAP",
  roster:  "ROSTER",
  alerts:  "ALERTS",
  inspect: "INSPECT · DEEP DATA",
  stats:   "STATS · LIVE",
};

interface ActionDef { id: Screen; icon: string; label: string; }
// "Jump to other screen" actions on the upper half of the rail. Listed in
// roughly the same order the side-nav used to use, so muscle memory carries
// across. CONFIG and ANALYTICS are kept here too so every workspace screen
// remains reachable from ROBOT without hunting through hotkeys.
const ACTIONS: ActionDef[] = [
  { id: "teleop",    icon: "⌖", label: "TELEOP" },
  { id: "scene",     icon: "◐", label: "SCENE" },
  { id: "program",   icon: "▸", label: "PROGRAM" },
  { id: "path",      icon: "↳", label: "PATH" },
  { id: "cam",       icon: "⦿", label: "CAM" },
  { id: "import",    icon: "↓", label: "IMPORT" },
  { id: "tasks",     icon: "▶", label: "MISSIONS" },
  { id: "analytics", icon: "⌬", label: "ANALYTICS" },
  { id: "logs",      icon: "⌗", label: "LOGS" },
  { id: "settings",  icon: "⚙", label: "CONFIG" },
];

export function FleetScreen({ fleet, alerts }: Props) {
  const selectedId = useUiStore(s => s.selectedId);
  const setSelectedId = useUiStore(s => s.setSelectedId);
  const setScreen = useUiStore(s => s.setScreen);
  const selected = fleet.find(r => r.id === selectedId);
  const docRobotId = useDocStore(s => s.doc.robotId);
  const robotModel = resolveRobot(docRobotId);

  // Driver pose for the 3D arm. Stable per robot (jointStateFor is seeded by
  // numeric id), so the arm strikes the same pose every time the user revisits.
  const seed = parseInt((selected?.id ?? "ARM-001").replace("ARM-", "") || "1", 10);
  const joints = jointStateFor(seed);
  const joint5 = joints[4]?.pos ?? 0;
  const nearWristSing = !!selected && Math.abs(joint5) < 6;

  const [flyout, setFlyout] = useState<FlyoutKey | null>(null);
  const toggleFlyout = (k: FlyoutKey) => setFlyout(prev => (prev === k ? null : k));
  const openAlerts = useMemo(
    () => alerts.filter(a => a.sev === "ERR" || a.sev === "WARN").length,
    [alerts],
  );

  return (
    <div className="screen robot-page">
      {/* main stage: live 3D arm fills the entire viewport behind the rail */}
      <div className="robot-3d-stage">
        <Arm3D
          key={(selected?.id ?? "none") + ":" + robotModel.id}
          jointAngles={joints.map(j => j.pos)}
          robot={robotModel}
          reach={robotModel.reach}
          width="100%"
          height="100%"
        />
        {/* overlays that read at-a-glance status without opening a flyout */}
        <div className="robot-hud-tl">
          <div className="mono" style={{ color: "var(--ok)", fontSize: 11 }}>
            ● {selected?.id ?? "—"} {selected ? `· ${selected.callsign}` : ""}
          </div>
          <div className="mono dim" style={{ fontSize: 9 }}>
            {selected ? `${robotModel.manufacturer} ${robotModel.name} · ${selected.task}` : "Pick a robot from FACTORY"}
          </div>
        </div>
        {selected && (
          <div className="robot-hud-tr">
            <span className="mono" style={{ fontSize: 10, color: STATUS_COLOR[selected.status] }}>
              ● {selected.status}
            </span>
            <span className="mono dim" style={{ fontSize: 10 }}>{selected.battery}% batt</span>
            <span className="mono dim" style={{ fontSize: 10 }}>{selected.latencyMs ?? "—"} ms</span>
          </div>
        )}
        {nearWristSing && (
          <div className="robot-hud-warn">⚠ WRIST · J5≈0</div>
        )}
      </div>

      {/* flyout panel — slides over the 3D from the right edge */}
      {flyout && (
        <aside className="tbx-flyout">
          <div className="tbx-flyout-hd">
            <span className="panel-title">{FLYOUT_TITLE[flyout]}</span>
            <button className="chip" onClick={() => setFlyout(null)}>✕</button>
          </div>
          <div className="tbx-flyout-body">
            {flyout === "factory" && (
              <FactoryFlyout fleet={fleet} selectedId={selectedId} onSelect={id => { setSelectedId(id); }} />
            )}
            {flyout === "roster" && (
              <RosterFlyout fleet={fleet} selectedId={selectedId} onSelect={setSelectedId} />
            )}
            {flyout === "alerts" && <AlertsFlyout alerts={alerts} />}
            {flyout === "inspect" && (
              selected
                ? <InspectFlyout robot={selected} joints={joints} />
                : <Empty>No robot selected.</Empty>
            )}
            {flyout === "stats" && (
              selected
                ? <StatsFlyout robot={selected} />
                : <Empty>No robot selected.</Empty>
            )}
          </div>
        </aside>
      )}

      {/* the toolbox rail itself */}
      <aside className="tbx-rail">
        {ACTIONS.map(a => (
          <RailButton
            key={a.id}
            icon={a.icon}
            label={a.label}
            onClick={() => setScreen(a.id)}
          />
        ))}
        <div className="tbx-rail-divider" />
        <RailButton icon="▦"  label="FACTORY" active={flyout === "factory"} onClick={() => toggleFlyout("factory")} />
        <RailButton icon="≡"  label="ROSTER"  active={flyout === "roster"}  onClick={() => toggleFlyout("roster")} />
        <RailButton icon="⚠" label="ALERTS" active={flyout === "alerts"}  badge={openAlerts || undefined} onClick={() => toggleFlyout("alerts")} />
        <RailButton icon="ℹ"  label="INSPECT" active={flyout === "inspect"} onClick={() => toggleFlyout("inspect")} />
        <RailButton icon="◫"  label="STATS"   active={flyout === "stats"}   onClick={() => toggleFlyout("stats")} />
      </aside>
    </div>
  );
}

// ───── Toolbox rail button ────────────────────────────────────────────────
interface RailButtonProps {
  icon: string;
  label: string;
  active?: boolean;
  badge?: number;
  onClick: () => void;
}
function RailButton({ icon, label, active, badge, onClick }: RailButtonProps) {
  return (
    <button
      className={"tbx-btn" + (active ? " active" : "")}
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={!!active}
    >
      <span className="tbx-icon">{icon}</span>
      <span className="tbx-label">{label}</span>
      {badge !== undefined && badge > 0 && <span className="tbx-badge">{badge}</span>}
    </button>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: 24, textAlign: "center", color: "var(--dim)" }} className="mono">
      {children}
    </div>
  );
}

// ───── Flyout body components ─────────────────────────────────────────────

function FactoryFlyout({
  fleet, selectedId, onSelect,
}: { fleet: Robot[]; selectedId: string; onSelect: (id: string) => void }) {
  return (
    <div className="cells" style={{ position: "static", inset: "auto", padding: 6, height: "auto" }}>
      {fleet.map(r => (
        <button key={r.id} className={"cell st-" + r.status + (r.id === selectedId ? " sel" : "")}
          style={{ ["--sc" as string]: STATUS_COLOR[r.status] }}
          onClick={() => onSelect(r.id)}>
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
  );
}

function RosterFlyout({
  fleet, selectedId, onSelect,
}: { fleet: Robot[]; selectedId: string; onSelect: (id: string) => void }) {
  return (
    <div className="table-wrap">
      <table className="dtable">
        <thead><tr><th>ID</th><th>STATUS</th><th>TASK</th><th>BATT</th></tr></thead>
        <tbody>
          {fleet.map(r => (
            <tr key={r.id} className={r.id === selectedId ? "sel" : ""} onClick={() => onSelect(r.id)}>
              <td>{r.id}</td>
              <td style={{ color: STATUS_COLOR[r.status] }}>{r.status}</td>
              <td style={{ color: "var(--fg-mute)" }}>{r.task}</td>
              <td>{r.battery}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AlertsFlyout({ alerts }: { alerts: Alert[] }) {
  return (
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
  );
}

function StatsFlyout({ robot }: { robot: Robot }) {
  return (
    <div style={{ padding: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
      <Stat label="STATUS" value={robot.status} color={STATUS_COLOR[robot.status]} />
      <Stat label="ZONE" value={robot.zone} />
      <Stat label="TASK" value={robot.task} sub={`cycle ${robot.cycleTime.toFixed(1)}s`} />
      <Stat label="TOOL" value={robot.tool} />
      <Stat label="TCP·v" value={`${robot.tcpSpeed.toFixed(2)} m/s`} />
      <Stat label="REACH" value={`${robot.reach.toFixed(2)} m`} />
      <Stat label="PAYLOAD" value={`${robot.payload.toFixed(1)} kg`} />
      <Stat label="BATTERY" value={`${robot.battery}%`} color={robot.battery < 20 ? "var(--warn)" : undefined} />
      <Stat label="LATENCY" value={`${robot.latencyMs ?? "—"} ms`} />
      <Stat label="UPTIME" value={`${robot.uptime} h`} />
      <Stat label="FAULTS·24H" value={robot.faults24h} color={robot.faults24h > 0 ? "var(--warn)" : undefined} />
      <Stat label="TASKS·24H" value={robot.tasksDone} />
    </div>
  );
}

// Inspector: TCP pose + joint state table + I/O + F/T + status. The 2D
// side view from the old RobotDetailScreen is gone — the user has the live
// 3D in the background already.
function InspectFlyout({
  robot, joints,
}: { robot: Robot; joints: ReturnType<typeof jointStateFor> }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 10 }}>
      <Panel title="CURRENT TCP POSE · base_link">
        <div className="tcp-pose">
          <div><span className="tag dim">X</span><span className="mono">{robot.tcp.x.toFixed(3)}</span></div>
          <div><span className="tag dim">Y</span><span className="mono">{robot.tcp.y.toFixed(3)}</span></div>
          <div><span className="tag dim">Z</span><span className="mono">{robot.tcp.z.toFixed(3)}</span></div>
          <div><span className="tag dim">RX</span><span className="mono">{robot.tcp.rx.toFixed(1)}°</span></div>
          <div><span className="tag dim">RY</span><span className="mono">{robot.tcp.ry.toFixed(1)}°</span></div>
          <div><span className="tag dim">RZ</span><span className="mono">{robot.tcp.rz.toFixed(1)}°</span></div>
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
        <Stat label="FW" value={robot.fw} />
        <Stat label="UPTIME" value={`${robot.uptime} h`} />
        <Stat label="TASKS·24H" value={`${robot.tasksDone}`} />
        <Stat label="FAULTS·24H" value={`${robot.faults24h}`} color={robot.faults24h > 0 ? "var(--warn)" : undefined} />
      </Panel>
    </div>
  );
}
