// data.jsx — mock fleet data + live tickers + reusable widgets

const CALLSIGNS = [
  "ATLAS","TITAN","ORION","HELIOS","ARES","KRONOS","JANUS","HERMES",
  "APOLLO","ICARUS","PERSEUS","THESEUS","HECTOR","ACHILLES","ODYSSEUS",
  "PROMETHEUS","HYPERION","NEMESIS","TARTARUS","CHARON","TRITON","BOREAS",
  "ZEPHYR","PHOENIX","KIRIN","SOLAR","NOVA","VEGA","RIGEL","DRACO"
];

const STATUSES = ["ACTIVE","ACTIVE","ACTIVE","ACTIVE","IDLE","IDLE","CHARGING","TELEOP","FAULT","OFFLINE"];
const TASKS = [
  "SORT-BIN-A7","PALLET-XFER-12","KIT-ASSEMBLY-03","INSPECT-LINE-2",
  "BIN-PICK-B4","STACK-CRATE-09","CHARGE-CYCLE","DIAG-SELFTEST",
  "HANDOFF-OP-22","TOOLCHANGE-T3","RECEIVING-DOCK-1","WAYPOINT-NAV",
  "MANIP-PRECISION-A","CALIB-IMU","IDLE-STANDBY"
];
const ZONES = ["A-NORTH","A-SOUTH","B-WEST","B-EAST","CHARGE-01","CHARGE-02","DOCK","LAB"];

// deterministic pseudo-random so layout is stable
function rng(seed) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

function buildFleet(count = 30) {
  const r = rng(7);
  return Array.from({ length: count }, (_, i) => {
    const num = String(i + 1).padStart(3, "0");
    const cs = CALLSIGNS[i % CALLSIGNS.length];
    const st = STATUSES[Math.floor(r() * STATUSES.length)];
    const battery = st === "CHARGING" ? Math.floor(r() * 40 + 20) :
                    st === "OFFLINE"  ? 0 :
                    Math.floor(r() * 70 + 25);
    return {
      id: `H-${num}`,
      callsign: cs,
      hex: `0x${(0x1A00 + i * 7).toString(16).toUpperCase()}`,
      status: st,
      zone: ZONES[Math.floor(r() * ZONES.length)],
      task: st === "OFFLINE" ? "—" : TASKS[Math.floor(r() * TASKS.length)],
      battery,
      uptime: st === "OFFLINE" ? 0 : Math.floor(r() * 720) + 4, // hours
      latencyMs: st === "OFFLINE" ? null : Math.floor(r() * 80 + 6),
      cpu: Math.floor(r() * 60 + 20),
      ram: Math.floor(r() * 50 + 30),
      temp: Math.floor(r() * 25 + 38), // °C
      x: 0.06 + r() * 0.88,    // 0..1 on map
      y: 0.08 + r() * 0.82,
      heading: Math.floor(r() * 360),
      fw: `2.7.${Math.floor(r()*20) + 100}`,
      payload: Math.floor(r() * 12 * 10) / 10, // kg
      tasksDone: Math.floor(r() * 480),
      faults24h: Math.floor(r() * 4),
      lastSeenSec: st === "OFFLINE" ? Math.floor(r() * 3600 * 4) + 60 : Math.floor(r() * 3),
    };
  });
}

const ALERTS_INIT = [
  { ts: "06:14:22.108", sev: "WARN",  src: "H-014",  msg: "EE-tilt drift exceeds 2.4° threshold" },
  { ts: "06:13:51.902", sev: "INFO",  src: "FLEET",  msg: "Mission #4421 queued · 12 waypoints" },
  { ts: "06:12:09.441", sev: "ERR",   src: "H-022",  msg: "Right shoulder PID saturated — auto-recovery" },
  { ts: "06:09:47.221", sev: "WARN",  src: "H-007",  msg: "Battery cell 4 imbalance 38mV" },
  { ts: "06:07:18.005", sev: "INFO",  src: "OPS",    msg: "Operator KOSTA acknowledged alert #882" },
  { ts: "06:04:02.117", sev: "OK",    src: "H-003",  msg: "Self-test PASSED · 142/142 checks" },
  { ts: "06:01:33.880", sev: "ERR",   src: "H-018",  msg: "LIDAR-front packet loss 12%" },
  { ts: "05:58:11.044", sev: "INFO",  src: "FLEET",  msg: "Heartbeat sweep · 28/30 ACK" },
  { ts: "05:55:48.700", sev: "WARN",  src: "H-011",  msg: "Foot contact estimator low confidence" },
  { ts: "05:52:09.331", sev: "INFO",  src: "H-024",  msg: "Returned to dock CHARGE-02" },
];

const JOINTS = [
  ["NECK_YAW",-180,180], ["NECK_PITCH",-45,60],
  ["SHOULDER_L_PITCH",-180,180],["SHOULDER_L_ROLL",-90,90],["SHOULDER_L_YAW",-180,180],
  ["ELBOW_L",-150,0],["WRIST_L_YAW",-180,180],["WRIST_L_PITCH",-90,90],
  ["SHOULDER_R_PITCH",-180,180],["SHOULDER_R_ROLL",-90,90],["SHOULDER_R_YAW",-180,180],
  ["ELBOW_R",-150,0],["WRIST_R_YAW",-180,180],["WRIST_R_PITCH",-90,90],
  ["TORSO_YAW",-90,90],["TORSO_PITCH",-30,30],
  ["HIP_L_PITCH",-90,90],["HIP_L_ROLL",-45,45],["HIP_L_YAW",-45,45],
  ["KNEE_L",0,135],["ANKLE_L_PITCH",-45,45],["ANKLE_L_ROLL",-30,30],
  ["HIP_R_PITCH",-90,90],["HIP_R_ROLL",-45,45],["HIP_R_YAW",-45,45],
  ["KNEE_R",0,135],["ANKLE_R_PITCH",-45,45],["ANKLE_R_ROLL",-30,30],
];

// generate a stable mock joint state per robot
function jointStateFor(seed) {
  const r = rng(seed);
  return JOINTS.map(([name, lo, hi]) => {
    const cur = lo + r() * (hi - lo);
    const tgt = cur + (r() - 0.5) * 8;
    return {
      name, lo, hi,
      pos: +cur.toFixed(2),
      tgt: +tgt.toFixed(2),
      vel: +((r()-0.5)*30).toFixed(2),
      torque: +((r()-0.5)*22).toFixed(2),
      temp: Math.floor(38 + r()*30),
      err: r() < 0.04 ? "STALL" : r() < 0.08 ? "OVERTEMP" : null,
    };
  });
}

// ── live tickers ──
function useClock() {
  const [now, setNow] = React.useState(() => new Date());
  React.useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function utcHMS(d) {
  const p = n => String(n).padStart(2, "0");
  return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}
function utcDate(d) {
  const p = n => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())}`;
}

// stream a tiny number that breathes
function useBreath(seed = 1, period = 1000, amp = 1) {
  const [v, setV] = React.useState(0);
  React.useEffect(() => {
    const t = setInterval(() => {
      setV(Math.sin(Date.now() / 400 + seed) * amp);
    }, period);
    return () => clearInterval(t);
  }, [seed, period, amp]);
  return v;
}

// rolling sparkline data
function useSeries(seed, len = 60, base = 50, swing = 25) {
  const [series, setSeries] = React.useState(() => {
    const r = rng(seed);
    return Array.from({ length: len }, () => base + (r() - 0.5) * swing);
  });
  React.useEffect(() => {
    const t = setInterval(() => {
      setSeries(s => {
        const last = s[s.length - 1];
        const next = Math.max(0, Math.min(100, last + (Math.random() - 0.5) * (swing/4)));
        return [...s.slice(1), next];
      });
    }, 800);
    return () => clearInterval(t);
  }, [swing]);
  return series;
}

// ── reusable widgets ──

function StatusDot({ status, size = 8 }) {
  const c = {
    ACTIVE:   "var(--ok)",
    IDLE:     "var(--dim)",
    CHARGING: "var(--info)",
    TELEOP:   "var(--magenta)",
    FAULT:    "var(--err)",
    OFFLINE:  "var(--off)",
  }[status] || "var(--dim)";
  const pulse = status === "ACTIVE" || status === "TELEOP" || status === "FAULT";
  return (
    <span style={{
      display: "inline-block", width: size, height: size, background: c,
      borderRadius: "50%", boxShadow: `0 0 0 2px ${c}22`,
      animation: pulse ? "pulse 1.6s ease-in-out infinite" : "none",
      flexShrink: 0,
    }} />
  );
}

function Sparkline({ data, width = 120, height = 28, color = "var(--ok)", fill = true }) {
  if (!data || !data.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return [x, y];
  });
  const path = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const area = path + ` L${width},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {fill && <path d={area} fill={color} opacity={0.12} />}
      <path d={path} fill="none" stroke={color} strokeWidth="1.2" />
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="1.6" fill={color} />
    </svg>
  );
}

function Bar({ value, max = 100, color = "var(--ok)", height = 4, width = "100%", showVal = false }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, width }}>
      <div style={{ flex: 1, height, background: "var(--track)", position: "relative" }}>
        <div style={{
          position: "absolute", inset: 0, right: `${100 - pct}%`,
          background: color,
        }} />
      </div>
      {showVal && <span className="mono dim" style={{ fontSize: 10, minWidth: 32, textAlign: "right" }}>{pct.toFixed(0)}%</span>}
    </div>
  );
}

function Stat({ label, value, sub, color, mono = true }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
      <div className="tag dim">{label}</div>
      <div className={mono ? "mono" : ""} style={{ fontSize: 18, color: color || "var(--fg)", lineHeight: 1.1, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
      {sub && <div className="mono" style={{ fontSize: 10, color: "var(--dim)" }}>{sub}</div>}
    </div>
  );
}

function Panel({ title, right, children, style, pad = true }) {
  return (
    <div className="panel" style={style}>
      {(title || right) && (
        <div className="panel-hd">
          <div className="panel-title">{title}</div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>{right}</div>
        </div>
      )}
      <div className="panel-body" style={pad ? {} : { padding: 0 }}>{children}</div>
    </div>
  );
}

function Crosshair({ size = 24, color = "var(--ok)" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ display: "block" }}>
      <circle cx="12" cy="12" r="9" fill="none" stroke={color} strokeOpacity="0.4" />
      <circle cx="12" cy="12" r="1.5" fill={color} />
      <line x1="12" y1="0" x2="12" y2="6" stroke={color} strokeOpacity="0.6" />
      <line x1="12" y1="18" x2="12" y2="24" stroke={color} strokeOpacity="0.6" />
      <line x1="0" y1="12" x2="6" y2="12" stroke={color} strokeOpacity="0.6" />
      <line x1="18" y1="12" x2="24" y2="12" stroke={color} strokeOpacity="0.6" />
    </svg>
  );
}

// expose
Object.assign(window, {
  buildFleet, ALERTS_INIT, JOINTS, jointStateFor,
  useClock, utcHMS, utcDate, useBreath, useSeries,
  StatusDot, Sparkline, Bar, Stat, Panel, Crosshair,
  ZONES, TASKS,
});
