// FloatingPanel — an absolutely-positioned, draggable, resizable info panel.
// Use it where the main content needs to be full-bleed (the 3D scene) and
// the supporting data wants to float over it without locking a fixed layout.
//
// What it does
//   * Drag the header to move the panel around.
//   * Bottom-right CSS resize handle to resize.
//   * Position is persisted in localStorage per `storageKey`.
//   * Initial size is applied once on mount via a ref (so a later user
//     resize isn't overwritten on re-render).
//   * On window resize, the saved position is clamped back into the
//     viewport so the panel can never end up off-screen.

import { useEffect, useRef, useState, type ReactNode } from "react";

interface Pos { x: number; y: number; }
interface Size { w: number; h: number; }

export type FloatPreset = "top-left" | "top-right" | "bottom-left" | "bottom-right";

export interface FloatingPanelProps {
  title: ReactNode;
  /** Unique key for localStorage persistence (e.g. "scene.robot"). */
  storageKey: string;
  /** Where to anchor on first render (before the user has dragged). */
  defaultPreset: FloatPreset;
  /** Initial width/height — overrideable by the user via the resize handle. */
  defaultSize?: Size;
  /** When provided, an ✕ button is rendered in the header. */
  onClose?: () => void;
  children: ReactNode;
}

const STORAGE_PREFIX = "arc:float:v1:";
// Margins used by computeDefault so the preset position clears the topbar
// (52px), bottombar (32px), and the ROBOT page's 50px right-edge toolbox.
const TOP_RESERVED = 70;
const BOT_RESERVED = 50;
const RIGHT_RESERVED = 70;
const SIDE_PAD = 12;

function loadPos(key: string): Pos | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.x !== "number" || typeof parsed?.y !== "number") return null;
    return parsed;
  } catch { return null; }
}

function savePos(key: string, pos: Pos): void {
  try { localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(pos)); }
  catch { /* quota / private mode — ignore */ }
}

function computeDefault(preset: FloatPreset, size: Size): Pos {
  const ww = window.innerWidth;
  const wh = window.innerHeight;
  switch (preset) {
    case "top-left":     return { x: SIDE_PAD,                          y: TOP_RESERVED };
    case "top-right":    return { x: ww - size.w - RIGHT_RESERVED,      y: TOP_RESERVED };
    case "bottom-left":  return { x: SIDE_PAD,                          y: wh - size.h - BOT_RESERVED };
    case "bottom-right": return { x: ww - size.w - RIGHT_RESERVED,      y: wh - size.h - BOT_RESERVED };
  }
}

function clampPos(p: Pos, el: HTMLElement | null): Pos {
  const w = el?.offsetWidth ?? 200;
  const minVisible = 60; // keep at least 60px of the panel reachable
  return {
    x: Math.max(-(w - minVisible),                    Math.min(p.x, window.innerWidth  - minVisible)),
    y: Math.max(52,                                   Math.min(p.y, window.innerHeight - minVisible)),
  };
}

export function FloatingPanel({
  title, storageKey, defaultPreset,
  defaultSize = { w: 300, h: 260 },
  onClose, children,
}: FloatingPanelProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ sx: number; sy: number; x0: number; y0: number } | null>(null);
  const [pos, setPos] = useState<Pos>(() =>
    loadPos(storageKey) ?? computeDefault(defaultPreset, defaultSize)
  );

  // Apply initial size to the DOM exactly once. After this, the user's CSS
  // resize handle owns width/height — React never re-applies them, so a
  // re-render driven by a position change won't reset the size.
  useEffect(() => {
    if (!ref.current) return;
    ref.current.style.width = defaultSize.w + "px";
    ref.current.style.height = defaultSize.h + "px";
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist position whenever it changes.
  useEffect(() => { savePos(storageKey, pos); }, [storageKey, pos]);

  // Re-clamp when the window shrinks so the panel never disappears off-screen.
  useEffect(() => {
    const onResize = () => setPos(p => clampPos(p, ref.current));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Drag handlers — pointer events with pointer capture so the drag keeps
  // tracking even if the cursor leaves the header element.
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
    dragRef.current = { sx: e.clientX, sy: e.clientY, x0: pos.x, y0: pos.y };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.sx;
    const dy = e.clientY - dragRef.current.sy;
    setPos(clampPos({ x: dragRef.current.x0 + dx, y: dragRef.current.y0 + dy }, ref.current));
  };
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    (e.currentTarget as HTMLDivElement).releasePointerCapture(e.pointerId);
    dragRef.current = null;
  };

  return (
    <div
      ref={ref}
      className="float-panel"
      style={{ position: "absolute", left: pos.x, top: pos.y }}
    >
      <div
        className="float-panel-hd"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <span className="panel-title">{title}</span>
        {onClose && (
          <button
            className="chip"
            onPointerDown={e => e.stopPropagation()}
            onClick={onClose}
            title="Close"
          >
            ✕
          </button>
        )}
      </div>
      <div className="float-panel-body">{children}</div>
    </div>
  );
}
