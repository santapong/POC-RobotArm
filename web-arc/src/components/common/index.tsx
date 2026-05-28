// Shared mission-control widgets used across every screen. Styled with the
// prototype's class names (.panel/.panel-hd/.tag/.mono/.dim/.track …) which
// are defined in src/index.css under Tailwind layers.

import type { CSSProperties, ReactNode } from "react";
import type { Status } from "@/types";

export { SplitScreen } from "./SplitScreen";
export type { SplitNode, SplitDir, SplitScreenProps } from "./SplitScreen";
export { FloatingPanel } from "./FloatingPanel";
export type { FloatingPanelProps, FloatPreset } from "./FloatingPanel";

export interface PanelProps {
  title?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  style?: CSSProperties;
  pad?: boolean;
}

export function Panel({ title, right, children, style, pad = true }: PanelProps) {
  return (
    <div className="panel" style={style}>
      {(title || right) && (
        <div className="panel-hd">
          <div className="panel-title">{title}</div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>{right}</div>
        </div>
      )}
      <div className="panel-body" style={pad ? undefined : { padding: 0 }}>{children}</div>
    </div>
  );
}

export interface StatProps {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  color?: string;
  mono?: boolean;
}

export function Stat({ label, value, sub, color, mono = true }: StatProps) {
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

export interface BarProps {
  value: number;
  max?: number;
  color?: string;
  height?: number;
  width?: string | number;
  showVal?: boolean;
}

export function Bar({ value, max = 100, color = "var(--ok)", height = 4, width = "100%", showVal = false }: BarProps) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, width }}>
      <div style={{ flex: 1, height, background: "var(--track)", position: "relative" }}>
        <div style={{ position: "absolute", inset: 0, right: `${100 - pct}%`, background: color }} />
      </div>
      {showVal && <span className="mono dim" style={{ fontSize: 10, minWidth: 32, textAlign: "right" }}>{pct.toFixed(0)}%</span>}
    </div>
  );
}

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  fill?: boolean;
}

export function Sparkline({ data, width = 120, height = 28, color = "var(--ok)", fill = true }: SparklineProps) {
  if (!data || !data.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return [x, y] as const;
  });
  const path = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const area = path + ` L${width},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {fill && <path d={area} fill={color} opacity={0.12} />}
      <path d={path} fill="none" stroke={color} strokeWidth="1.2" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="1.6" fill={color} />
    </svg>
  );
}

export interface StatusDotProps {
  status: Status | "CHARGING";
  size?: number;
}

export function StatusDot({ status, size = 8 }: StatusDotProps) {
  const c =
    status === "ACTIVE"   ? "var(--ok)" :
    status === "TELEOP"   ? "var(--magenta)" :
    status === "FAULT"    ? "var(--err)" :
    status === "OFFLINE"  ? "var(--off)" :
    status === "CHARGING" ? "var(--info)" :
                            "var(--dim)";
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

export interface TagProps {
  children: ReactNode;
  dim?: boolean;
  color?: string;
}

export function Tag({ children, dim, color }: TagProps) {
  return <span className={"tag" + (dim ? " dim" : "")} style={color ? { color } : undefined}>{children}</span>;
}

export interface CrosshairProps { size?: number; color?: string; }
export function Crosshair({ size = 24, color = "var(--ok)" }: CrosshairProps) {
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
