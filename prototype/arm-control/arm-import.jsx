// arm-import.jsx — import & edit panel for CAD models, programs, trajectories

function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1024*1024) return (n/1024).toFixed(1) + " KB";
  return (n/1024/1024).toFixed(2) + " MB";
}
function fmtAge(iso) {
  const d = new Date(iso);
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 60) return Math.floor(sec) + "s ago";
  if (sec < 3600) return Math.floor(sec/60) + "m ago";
  if (sec < 86400) return Math.floor(sec/3600) + "h ago";
  return Math.floor(sec/86400) + "d ago";
}

function typeColor(t) {
  return ({
    URDF:"var(--ok)", STEP:"var(--info)", STL:"var(--info)",
    PROG:"var(--magenta)", PY:"var(--warn)", TRAJ:"var(--ok)", CSV:"var(--fg-mute)",
  })[t] || "var(--fg-mute)";
}
function typeIcon(t) {
  return ({ URDF: "◉", STEP: "▦", STL: "▦", PROG: "≡", PY: "≡", TRAJ: "↝", CSV: "⊞" })[t] || "•";
}

function FileTree({ files, selectedPath, onSelect }) {
  // group files by directory
  const tree = React.useMemo(() => {
    const dirs = {};
    files.forEach(f => {
      const dir = f.path.includes("/") ? f.path.split("/")[0] : "";
      if (!dirs[dir]) dirs[dir] = [];
      dirs[dir].push(f);
    });
    return Object.entries(dirs);
  }, [files]);

  return (
    <div className="ftree">
      {tree.map(([dir, items]) => (
        <div key={dir} className="ftree-grp">
          <div className="ftree-dir">
            <span className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>▼</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--fg)", fontWeight: 500 }}>{dir}/</span>
            <span className="mono dim" style={{ fontSize: 9, marginLeft: "auto" }}>{items.length}</span>
          </div>
          {items.map(f => {
            const name = f.path.split("/").pop();
            const isSel = f.path === selectedPath;
            return (
              <button key={f.path} className={"ftree-file" + (isSel ? " sel" : "")} onClick={() => onSelect(f.path)}>
                <span className="mono" style={{ color: typeColor(f.type), width: 12 }}>{typeIcon(f.type)}</span>
                <span className="mono ftree-name" style={{ fontSize: 10.5 }}>{name}</span>
                <span className="ft-type mono" style={{ color: typeColor(f.type), fontSize: 8 }}>{f.type}</span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function HighlightedProgram({ text }) {
  // very light keyword/string/number coloring for *.urpx-style programs
  const lines = text.split("\n");
  return (
    <div className="proged">
      {lines.map((line, i) => {
        // tokenize
        const isComment = line.trim().startsWith("#");
        let html;
        if (isComment) {
          html = <span style={{ color: "var(--dim)" }}>{line || "\u00A0"}</span>;
        } else {
          // split by keywords / numbers / strings
          const parts = [];
          let rest = line;
          const tok = /([A-Z_][A-Z_0-9]*\s*\(|[a-z_]+_[a-z_]+|movej|movel|movec|movep|sleep|set_tcp|set_payload|set_digital_out|DEF|END|p\[|\d+\.\d+|\d+|True|False)/g;
          let m;
          let lastIdx = 0;
          while ((m = tok.exec(rest)) !== null) {
            if (m.index > lastIdx) parts.push(<span key={parts.length}>{rest.slice(lastIdx, m.index)}</span>);
            const t = m[0];
            let color = "var(--fg)";
            if (/^(DEF|END)$/.test(t)) color = "var(--magenta)";
            else if (/^(movej|movel|movec|movep|sleep|set_tcp|set_payload|set_digital_out)/.test(t)) color = "var(--info)";
            else if (/^\d/.test(t)) color = "var(--warn)";
            else if (/^p\[/.test(t)) color = "var(--ok)";
            else if (/^(True|False)$/.test(t)) color = "var(--magenta)";
            parts.push(<span key={parts.length} style={{ color }}>{t}</span>);
            lastIdx = m.index + t.length;
          }
          if (lastIdx < rest.length) parts.push(<span key={parts.length}>{rest.slice(lastIdx)}</span>);
          html = parts;
        }
        return (
          <div key={i} className="proged-line">
            <span className="proged-num mono">{String(i + 1).padStart(3, " ")}</span>
            <span className="proged-text mono">{html}</span>
          </div>
        );
      })}
    </div>
  );
}

function CADPreview({ file }) {
  // synthetic preview: a wireframe-style SVG representing the file's category
  const type = file.type;
  if (type === "URDF") {
    return (
      <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid meet" style={{ width: "100%", height: "100%", display: "block" }}>
        <defs>
          <pattern id="grdc" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(120,180,200,.1)" strokeWidth="1"/>
          </pattern>
        </defs>
        <rect width="400" height="300" fill="url(#grdc)" />
        {/* mini arm wireframe */}
        <g transform="translate(200 270)" stroke="var(--ok)" fill="none" strokeWidth="1.5">
          <rect x="-25" y="-10" width="50" height="10" />
          <circle cx="0" cy="-20" r="9" />
          <line x1="0" y1="-20" x2="60" y2="-100" />
          <circle cx="60" cy="-100" r="7" />
          <line x1="60" y1="-100" x2="120" y2="-160" />
          <circle cx="120" cy="-160" r="6" />
          <line x1="120" y1="-160" x2="160" y2="-130" />
          <circle cx="160" cy="-130" r="5" />
          <line x1="160" y1="-130" x2="180" y2="-110" stroke="var(--magenta)" />
        </g>
        <text x="8" y="14" fill="rgba(120,180,200,.5)" fontSize="9" fontFamily="JetBrains Mono">URDF · 6-LINK CHAIN</text>
        <text x="392" y="14" textAnchor="end" fill="rgba(120,180,200,.5)" fontSize="9" fontFamily="JetBrains Mono">REVOLUTE × 6</text>
      </svg>
    );
  }
  if (type === "STEP" || type === "STL") {
    return (
      <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid meet" style={{ width: "100%", height: "100%", display: "block" }}>
        <rect width="400" height="300" fill="#02060a" />
        {/* iso wireframe part */}
        <g transform="translate(200 160)" stroke="var(--info)" fill="rgba(56,189,248,.05)" strokeWidth="1.2">
          <polygon points="-60,-40 60,-40 80,-20 80,40 60,60 -60,60 -80,40 -80,-20" />
          <polygon points="-60,-40 60,-40 80,-20 -40,-20" />
          <polygon points="60,-40 80,-20 80,40 60,60" />
          <line x1="-40" y1="-20" x2="-40" y2="60" />
          <line x1="60" y1="60" x2="60" y2="-40" />
          {/* hole */}
          <ellipse cx="-10" cy="20" rx="20" ry="8" fill="#02060a" />
          <ellipse cx="20" cy="0" rx="12" ry="5" fill="#02060a" />
        </g>
        {/* dimensions */}
        <line x1="120" y1="240" x2="280" y2="240" stroke="var(--warn)" />
        <line x1="120" y1="234" x2="120" y2="246" stroke="var(--warn)" />
        <line x1="280" y1="234" x2="280" y2="246" stroke="var(--warn)" />
        <text x="200" y="258" textAnchor="middle" fill="var(--warn)" fontSize="9" fontFamily="JetBrains Mono">142.8 mm</text>
        <text x="8" y="14" fill="rgba(120,180,200,.5)" fontSize="9" fontFamily="JetBrains Mono">{type} · MESH</text>
        <text x="392" y="14" textAnchor="end" fill="rgba(120,180,200,.5)" fontSize="9" fontFamily="JetBrains Mono">ISO · 1:2</text>
      </svg>
    );
  }
  if (type === "TRAJ") {
    return (
      <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid meet" style={{ width: "100%", height: "100%", display: "block" }}>
        <rect width="400" height="300" fill="#02060a" />
        {/* path */}
        <path d="M 80 220 Q 100 80 200 100 T 320 220" fill="none" stroke="var(--ok)" strokeWidth="2" />
        {[[80,220],[140,120],[200,100],[260,140],[320,220]].map(([x,y],i) => (
          <g key={i}>
            <circle cx={x} cy={y} r="6" fill="var(--warn)" />
            <text x={x + 8} y={y + 3} fill="var(--warn)" fontSize="9" fontFamily="JetBrains Mono">{i+1}</text>
          </g>
        ))}
        <text x="8" y="14" fill="rgba(120,180,200,.5)" fontSize="9" fontFamily="JetBrains Mono">TRAJ · {file.path.split("/").pop()}</text>
      </svg>
    );
  }
  return (
    <div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--dim)" }}>
      <span className="mono">No preview available</span>
    </div>
  );
}

function ImportScreen({ onGoto }) {
  const [files, setFiles] = React.useState(EXAMPLE_IMPORTS);
  const [selectedPath, setSelectedPath] = React.useState("programs/pick_place.urpx");
  const [drag, setDrag] = React.useState(false);
  const [code, setCode] = React.useState(EXAMPLE_PROGRAM);

  const sel = files.find(f => f.path === selectedPath);

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    if (!e.dataTransfer) return;
    Array.from(e.dataTransfer.files || []).forEach(file => {
      const ext = file.name.split(".").pop().toUpperCase();
      const typeMap = { URDF:"URDF", SDF:"URDF", STEP:"STEP", STP:"STEP", STL:"STL", URPX:"PROG", URP:"PROG", PY:"PY", JSON:"TRAJ", CSV:"CSV", GCODE:"PROG" };
      setFiles(f => [{
        path: "uploads/" + file.name,
        type: typeMap[ext] || "PROG",
        size: file.size,
        modified: new Date().toISOString(),
        author: "OP·KOSTA",
      }, ...f]);
    });
  };

  return (
    <div className="screen import">
      <div className="import-grid">
        {/* file tree */}
        <Panel title="LIBRARY · 14 ASSETS" right={
          <div style={{ display: "flex", gap: 4 }}>
            <input className="inp" placeholder="filter ›" style={{ width: 100 }} />
            <button className="chip on">ALL</button>
          </div>
        } pad={false}>
          <FileTree files={files} selectedPath={selectedPath} onSelect={setSelectedPath} />
        </Panel>

        {/* preview / editor */}
        <Panel title={sel ? `▸ ${sel.path}` : "NO FILE"} right={
          sel && (
            <div style={{ display: "flex", gap: 4 }}>
              <button className="chip on">PREVIEW</button>
              <button className="chip">SOURCE</button>
              <button className="chip">PROPERTIES</button>
              <button className="chip">DIFF</button>
            </div>
          )
        } pad={false}>
          {sel ? (
            <div className="preview-wrap">
              {(sel.type === "PROG" || sel.type === "PY") ? (
                <div className="proged-wrap">
                  <HighlightedProgram text={code} />
                </div>
              ) : (
                <CADPreview file={sel} />
              )}
            </div>
          ) : (
            <div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--dim)" }}>
              <span className="mono">Select a file</span>
            </div>
          )}
        </Panel>

        {/* inspector */}
        <Panel title="INSPECTOR">
          {sel ? (
            <>
              <Stat label="NAME" value={sel.path.split("/").pop()} mono />
              <hr className="hr" />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <Stat label="TYPE" value={sel.type} color={typeColor(sel.type)} />
                <Stat label="SIZE" value={fmtBytes(sel.size)} />
                <Stat label="MODIFIED" value={fmtAge(sel.modified)} />
                <Stat label="AUTHOR" value={sel.author} />
              </div>
              <hr className="hr" />
              <div className="tag dim">SHA-256</div>
              <div className="mono" style={{ fontSize: 9, color: "var(--fg-mute)", wordBreak: "break-all" }}>
                e7b41a3d8c4f29b7d5a0e16f8c2b4a91c3d7e8f0a1b2c3d4e5f6789a0b1c2d3e4
              </div>
              <hr className="hr" />
              <div className="tag dim">VALIDATION</div>
              {[
                ["SCHEMA", "PASS", "var(--ok)"],
                ["JOINT LIMITS", "PASS", "var(--ok)"],
                ["UNITS · m / rad", "PASS", "var(--ok)"],
                ["UNRESOLVED REFS", "0", "var(--ok)"],
                ["MESH COMPLEXITY", "OK · 12.4k tri", "var(--info)"],
              ].map(([k, v, c]) =>
                <div key={k} className="check-row">
                  <span className="mono" style={{ fontSize: 10, color: c }}>{c === "var(--ok)" ? "✓" : "•"}</span>
                  <span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span>
                  <span className="mono" style={{ fontSize: 10, color: c, marginLeft: "auto" }}>{v}</span>
                </div>
              )}
              <hr className="hr" />
              <div className="tag dim">ACTIONS</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {sel.type === "TRAJ" && <button className="btn primary" onClick={() => onGoto("path")}>OPEN IN PATH EDITOR ›</button>}
                {sel.type === "PROG" && <button className="btn primary">RUN ON ARM ›</button>}
                {(sel.type === "URDF" || sel.type === "STEP" || sel.type === "STL") && <button className="btn primary" onClick={() => onGoto("scene")}>VIEW IN 3D CAD ›</button>}
                <button className="btn">SIMULATE</button>
                <button className="btn">ASSIGN TO ARM</button>
                <button className="btn">DOWNLOAD</button>
                <button className="btn">SHARE LINK</button>
                <button className="btn danger">DELETE</button>
              </div>
            </>
          ) : (
            <div style={{ color: "var(--dim)" }} className="mono">No file selected</div>
          )}
        </Panel>

        {/* code editor */}
        <Panel title={sel && (sel.type === "PROG" || sel.type === "PY") ? `EDITOR · ${sel.path.split("/").pop()}` : "EDITOR"} right={
          <div style={{ display: "flex", gap: 4 }}>
            <span className="tag dim">UTF-8 · LF</span>
            <button className="chip">UNDO</button>
            <button className="chip">REDO</button>
            <button className="chip">FORMAT</button>
            <button className="chip on">SAVE · ⌘S</button>
          </div>
        } pad={false} style={{ gridColumn: "1 / span 3" }}>
          <div className="editor-wrap">
            <textarea
              className="editor mono"
              value={code}
              onChange={e => setCode(e.target.value)}
              spellCheck={false}
            />
          </div>
        </Panel>

        {/* drop zone + recent */}
        <Panel title="IMPORT · DRAG & DROP" pad={false}>
          <div
            className={"dropzone" + (drag ? " on" : "")}
            onDragOver={e => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
          >
            <div className="mono" style={{ fontSize: 20, color: drag ? "var(--ok)" : "var(--fg-mute)" }}>↓</div>
            <div className="mono" style={{ color: drag ? "var(--ok)" : "var(--fg-mute)", fontSize: 11 }}>DROP FILES HERE</div>
            <div className="mono dim" style={{ fontSize: 9, marginTop: 4 }}>URDF · SDF · STEP · STL · URPX · GCODE · JSON · CSV · PY</div>
            <button className="btn primary" style={{ marginTop: 10 }}>BROWSE…</button>
          </div>
        </Panel>

        <Panel title="RECENT IMPORTS" pad={false}>
          <div className="recent">
            {files.slice(0, 8).map(f => (
              <button key={f.path} className="recent-row" onClick={() => setSelectedPath(f.path)}>
                <span className="mono" style={{ color: typeColor(f.type), width: 14 }}>{typeIcon(f.type)}</span>
                <span className="mono" style={{ fontSize: 10.5, flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{f.path.split("/").pop()}</span>
                <span className="mono dim" style={{ fontSize: 9 }}>{fmtBytes(f.size)}</span>
                <span className="mono dim" style={{ fontSize: 9 }}>{fmtAge(f.modified)}</span>
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="IMPORT QUEUE">
          <div className="queue-row">
            <span className="mono" style={{ fontSize: 11, flex: 1 }}>cell_layout.step</span>
            <Bar value={64} color="var(--info)" height={6} />
            <span className="mono" style={{ fontSize: 10, color: "var(--info)", marginLeft: 8 }}>64%</span>
          </div>
          <div className="queue-row">
            <span className="mono" style={{ fontSize: 11, flex: 1 }}>gripper_v2.urdf</span>
            <Bar value={18} color="var(--info)" height={6} />
            <span className="mono" style={{ fontSize: 10, color: "var(--info)", marginLeft: 8 }}>18%</span>
          </div>
          <hr className="hr" />
          <div className="tag dim">PARSER · VALIDATING</div>
          <div className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>● cell_layout.step: 12,442 / 19,200 tri</div>
          <div className="mono" style={{ fontSize: 10, color: "var(--ok)" }}>● gripper_v2.urdf: schema OK</div>
          <hr className="hr" />
          <div className="tag dim">SOURCES</div>
          {[
            ["GIT · ops/main", "synced 2m ago", "var(--ok)"],
            ["FILE SHARE · /lab", "online", "var(--ok)"],
            ["FUSION 360 · live", "12 parts", "var(--info)"],
            ["S3 · cad-archive", "1,402 files", "var(--info)"],
          ].map(([k, v, c]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid var(--border)" }}>
              <span className="mono" style={{ fontSize: 10, color: c }}>● {k}</span>
              <span className="mono dim" style={{ fontSize: 10 }}>{v}</span>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

Object.assign(window, { ImportScreen });
