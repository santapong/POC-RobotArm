// Placeholder shell (P0). Real screens land in P4.
export default function App() {
  return (
    <div className="app" style={{ gridTemplateAreas: '"top" "main" "bot"', gridTemplateColumns: "1fr", gridTemplateRows: "52px 1fr 32px" }}>
      <header className="topbar" style={{ gridArea: "top" }}>
        <div className="brand">
          <div>
            <div style={{ fontSize: 11, letterSpacing: ".18em", color: "var(--fg)" }}>ARC·OPS</div>
            <div className="tag dim" style={{ fontSize: 9 }}>6-DoF ARM FLEET · web-arc</div>
          </div>
        </div>
      </header>
      <main style={{ gridArea: "main", display: "grid", placeItems: "center" }}>
        <div className="panel" style={{ padding: 24, maxWidth: 420 }}>
          <div className="panel-title">Vite + React + TypeScript scaffold</div>
          <hr className="hr" />
          <p className="mono" style={{ fontSize: 12, color: "var(--fg-mute)" }}>
            Toolchain online. Screens, stores and 3D viewers are ported in the
            following phases.
          </p>
        </div>
      </main>
      <footer className="bottombar" style={{ gridArea: "bot" }}>
        <div className="bb-item"><span className="tag dim">BUILD</span><span className="mono" style={{ color: "var(--ok)" }}>OK</span></div>
      </footer>
    </div>
  );
}
