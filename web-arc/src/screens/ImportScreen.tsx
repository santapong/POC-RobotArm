// IMPORT — asset library tree + program editor + dropzone. The dead
// SAVE/UNDO/REDO chips of the prototype are wired to the doc store here.

import { useState } from "react";
import { Panel, SplitScreen, type SplitNode } from "@/components/common";
import { downloadDoc } from "@/lib/doc";
import { useCanRedo, useCanUndo, useDoc, useDocStore } from "@/store/useDocStore";

type AssetType = "URDF" | "STEP" | "STL" | "PROG" | "PY" | "TRAJ" | "CSV";
interface Asset { path: string; type: AssetType; size: number; modified: string; author: string; }

const EXAMPLE_IMPORTS: Asset[] = [
  { path: "models/arm_ur5e.urdf",        type: "URDF", size: 28412,   modified: "2026-05-22T09:11:00Z", author: "ENG·LIN" },
  { path: "models/gripper_2f.urdf",      type: "URDF", size:  9418,   modified: "2026-05-22T09:14:00Z", author: "ENG·LIN" },
  { path: "cad/part_v4.step",            type: "STEP", size: 1894244, modified: "2026-05-20T16:08:00Z", author: "MECH·JI" },
  { path: "cad/fixture_jaws.stl",        type: "STL",  size: 412800,  modified: "2026-05-21T10:30:00Z", author: "MECH·JI" },
  { path: "programs/pick_place.urpx",    type: "PROG", size: 4218,    modified: "2026-05-26T05:48:00Z", author: "OP·KOSTA" },
  { path: "programs/calibrate_tcp.py",   type: "PY",   size: 3110,    modified: "2026-05-20T12:00:00Z", author: "ENG·LIN" },
  { path: "trajectories/PICK-PLACE.json",type: "TRAJ", size: 12480,   modified: "2026-05-26T06:11:48Z", author: "OP·KOSTA" },
  { path: "waypoints/bin_locations.csv", type: "CSV",  size: 842,     modified: "2026-05-18T11:00:00Z", author: "ENG·DAR" },
];

const EXAMPLE_PROG = `# pick_place.urpx
DEF pick_place_a7():
    set_payload(1.8, [0, 0, 0.05])
    set_tcp(p[0, 0, 0.158, 0, 0, 0])
    movej([0, -1.57, 0, 0, 1.57, 0], a=1.0, v=1.05)
    movel(p[0.420, -0.180, 0.180, 3.14, 0, 0], a=0.6, v=0.3)
    set_digital_out(0, True)
END
`;

export function ImportScreen() {
  const [files, setFiles] = useState<Asset[]>(EXAMPLE_IMPORTS);
  const [sel, setSel] = useState<string>(EXAMPLE_IMPORTS[4].path);
  const [code, setCode] = useState(EXAMPLE_PROG);
  const [drag, setDrag] = useState(false);
  const doc = useDocStore(useDoc);
  const undo = useDocStore(s => s.undo);
  const redo = useDocStore(s => s.redo);
  const canUndo = useDocStore(useCanUndo);
  const canRedo = useDocStore(useCanRedo);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDrag(false);
    Array.from(e.dataTransfer.files || []).forEach(file => {
      const ext = (file.name.split(".").pop() || "").toUpperCase();
      const map: Record<string, AssetType> = { URDF: "URDF", STEP: "STEP", STL: "STL", URPX: "PROG", PY: "PY", JSON: "TRAJ", CSV: "CSV" };
      setFiles(f => [
        { path: "uploads/" + file.name, type: map[ext] ?? "PROG", size: file.size, modified: new Date().toISOString(), author: "OP·KOSTA" },
        ...f,
      ]);
    });
  };

  const assetsPanel = (
    <Panel title="ASSETS" pad={false}>
      <div className="ftree">
        {files.map(f => (
          <button key={f.path} className={"ftree-file" + (f.path === sel ? " sel" : "")}
            onClick={() => setSel(f.path)}>
            <span className={"ft-type tag"} style={{ color: "var(--info)" }}>{f.type}</span>
            <span className="ftree-name">{f.path}</span>
            <span className="mono dim" style={{ fontSize: 9 }}>{(f.size / 1024).toFixed(1)} kB</span>
          </button>
        ))}
      </div>
    </Panel>
  );

  const previewPanel = (
    <Panel title="PREVIEW" pad={false}>
      <div className="proged-wrap">
        <div className="proged">
          {EXAMPLE_PROG.split("\n").map((line, i) => (
            <div key={i} className="proged-line">
              <span className="proged-num mono">{i + 1}</span>
              <span className="proged-text mono">{line}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );

  const inspectorPanel = (
    <Panel title="INSPECTOR">
      <div className="mono dim" style={{ fontSize: 10 }}>{sel}</div>
      <hr className="hr" />
      <div className="tag dim">VALIDATION</div>
      {["SHA OK","SCHEMA OK","REFERENCES OK"].map(k =>
        <div key={k} className="check-row"><span className="mono" style={{ color: "var(--ok)" }}>✓</span><span className="tag" style={{ color: "var(--fg-mute)" }}>{k}</span></div>
      )}
    </Panel>
  );

  const editorPanel = (
    <Panel title="EDITOR" pad={false}
      right={
        <div style={{ display: "flex", gap: 4 }}>
          <span className="tag dim">UTF-8 · LF</span>
          <button className={"chip" + (canUndo ? "" : " disabled")} onClick={() => undo()}>UNDO</button>
          <button className={"chip" + (canRedo ? "" : " disabled")} onClick={() => redo()}>REDO</button>
          <button className="chip on" onClick={() => downloadDoc(doc)}>SAVE · ⌘S</button>
        </div>
      }>
      <div className="editor-wrap">
        <textarea className="editor" value={code} onChange={e => setCode(e.target.value)} spellCheck={false} />
      </div>
    </Panel>
  );

  const dropPanel = (
    <Panel title="DROPZONE" pad={false}>
      <div className={"dropzone" + (drag ? " on" : "")}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}>
        <span className="mono" style={{ color: "var(--ok)" }}>DROP FILES HERE</span>
        <span className="tag dim">URDF · STEP · STL · URPX · PY · JSON · CSV</span>
      </div>
    </Panel>
  );

  const recentPanel = (
    <Panel title="RECENT" pad={false}>
      <div className="recent">
        {files.slice(0, 6).map(f => (
          <button key={f.path} className="recent-row">
            <span className="mono" style={{ fontSize: 10, flex: 1 }}>{f.path}</span>
            <span className="mono dim" style={{ fontSize: 9 }}>{f.author}</span>
          </button>
        ))}
      </div>
    </Panel>
  );

  const layout: SplitNode = {
    type: "split", direction: "v", key: "root",
    children: [
      { type: "split", direction: "h", key: "top", size: 60, children: [
        { type: "leaf", key: "assets", size: 22, content: assetsPanel },
        { type: "split", direction: "v", key: "mid", size: 50, children: [
          { type: "leaf", key: "preview", size: 60, content: previewPanel },
          { type: "leaf", key: "drop", size: 40, content: dropPanel },
        ]},
        { type: "split", direction: "v", key: "right", size: 28, children: [
          { type: "leaf", key: "inspector", size: 55, content: inspectorPanel },
          { type: "leaf", key: "recent", size: 45, content: recentPanel },
        ]},
      ]},
      { type: "leaf", key: "editor", size: 40, content: editorPanel },
    ],
  };

  return <SplitScreen id="import" className="screen import" node={layout} />;
}
