import { useUiStore, type Tweaks } from "@/store/useUiStore";

const ACCENTS = ["#4ade80", "#38bdf8", "#fbbf24", "#e879f9", "#f97316"];

// Display-tweaks popover. The launcher chips (⚙ TWEAKS and the active-robot
// badge) live in the TopBar now — this component only renders the popover
// itself, driven by `useUiStore.tweaksOpen`. The popover anchors to the
// right edge offset past the ROBOT page's 50px toolbox rail so it doesn't
// overlap.
export function TweaksPanel() {
  const open = useUiStore(s => s.tweaksOpen);
  const setOpen = useUiStore(s => s.setTweaksOpen);
  const tweaks = useUiStore(s => s.tweaks);
  const setTweak = useUiStore(s => s.setTweak);
  const set = <K extends keyof Tweaks>(k: K) => (v: Tweaks[K]) => setTweak(k, v);

  if (!open) return null;

  return (
    <aside
      className="panel"
      style={{ position: "fixed", top: 60, right: 62, width: 240, zIndex: 1100, padding: 0 }}
    >
      <div className="panel-hd">
        <div className="panel-title">DISPLAY TWEAKS</div>
        <button className="chip" onClick={() => setOpen(false)}>✕</button>
      </div>
      <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Row label="ACCENT">
          <div style={{ display: "flex", gap: 4 }}>
            {ACCENTS.map(c => (
              <button
                key={c}
                onClick={() => setTweak("accent", c)}
                title={c}
                style={{
                  width: 18, height: 18, background: c, border: "1px solid var(--border-2)",
                  outline: tweaks.accent === c ? `2px solid ${c}` : "none", cursor: "pointer",
                }}
              />
            ))}
          </div>
        </Row>
        <Row label="DENSITY">
          <div style={{ display: "flex", gap: 4 }}>
            {(["dense", "comfy"] as const).map(d => (
              <button
                key={d}
                className={"chip" + (tweaks.density === d ? " on" : "")}
                onClick={() => set("density")(d)}
              >
                {d.toUpperCase()}
              </button>
            ))}
          </div>
        </Row>
        <Toggle label="SHOW WORKSPACE" value={tweaks.showWorkspace} onChange={set("showWorkspace")} />
        <Toggle label="SHOW SINGULARITY" value={tweaks.showSingularity} onChange={set("showSingularity")} />
        <Toggle label="AUTO-ROTATE 3D" value={tweaks.autoRotate3D} onChange={set("autoRotate3D")} />
        <Row label="SCENE BG">
          <div style={{ display: "flex", gap: 4 }}>
            {(["dark", "mid", "light"] as const).map(b => (
              <button
                key={b}
                className={"chip" + (tweaks.sceneBg === b ? " on" : "")}
                onClick={() => set("sceneBg")(b)}
              >
                {b.toUpperCase()}
              </button>
            ))}
          </div>
        </Row>
        <Row label={`ARM COUNT · ${tweaks.armCount}`}>
          <input
            type="range" className="slider" min={6} max={60} step={1}
            value={tweaks.armCount}
            onChange={e => set("armCount")(parseInt(e.target.value, 10))}
          />
        </Row>
      </div>
    </aside>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span className="tag dim">{label}</span>
      {children}
    </div>
  );
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
      <span className="tag dim">{label}</span>
      <button
        className={"switch" + (value ? " on" : "")}
        onClick={() => onChange(!value)}
        aria-pressed={value}
        type="button"
      >
        <span className="switch-thumb" />
      </button>
    </div>
  );
}
