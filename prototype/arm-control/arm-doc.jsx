// arm-doc.jsx — single serializable project document + undo/redo history +
// save/load. Loaded AFTER arm-program.jsx (uses DEFAULT_JOB) and BEFORE
// arm-app.jsx.
//
// The "project" is the operation tree (job) + active TCP + meta. The tool /
// part / TCP *libraries* stay as code catalogs (arm-tooling.jsx); the job
// references them by id — exactly like Robotmaster keeps a tool DB separate
// from the part program. Undo/redo and save/load operate on this one document.

const DOC_VERSION = 1;
const DOC_LS_KEY = "arc_ops_project_v1";

function makeDefaultDoc() {
  const base = (typeof DEFAULT_JOB !== "undefined") ? DEFAULT_JOB
    : { id: "0", name: "PROGRAM", author: "OP", activeTcpId: "tcp-tip", postFormat: "URScript", ops: [] };
  return {
    version: DOC_VERSION,
    meta: { name: base.name || "Untitled Program", author: base.author || "OP·KOSTA", modified: new Date().toISOString() },
    job: JSON.parse(JSON.stringify(base)),
    activeTcpId: base.activeTcpId || "tcp-tip",
  };
}

function serializeDoc(doc) {
  return JSON.stringify({ version: DOC_VERSION, meta: doc.meta, job: doc.job, activeTcpId: doc.activeTcpId }, null, 2);
}

function deserializeDoc(str) {
  const o = (typeof str === "string") ? JSON.parse(str) : str;
  if (!o || typeof o !== "object" || !o.job || !Array.isArray(o.job.ops)) {
    throw new Error("Not a valid ARC·OPS project (missing job.ops)");
  }
  // (only v1 exists; migrations would go here keyed off o.version)
  return {
    version: DOC_VERSION,
    meta: o.meta || { name: "Imported Program", author: "OP", modified: new Date().toISOString() },
    job: o.job,
    activeTcpId: o.activeTcpId || o.job.activeTcpId || "tcp-tip",
  };
}

// ── store: holds the current doc + past/future snapshot stacks ───────────────
const DocStore = (function () {
  let doc = null;
  const past = [], future = [];
  const listeners = new Set();
  const CAP = 100, COALESCE_MS = 400;
  let lastLabel = null, lastTime = 0;
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const emit = () => listeners.forEach(l => l());

  function init(initial) { doc = initial || makeDefaultDoc(); past.length = 0; future.length = 0; lastLabel = null; emit(); }
  function getSnapshot() { return doc; }
  function subscribe(l) { listeners.add(l); return () => listeners.delete(l); }

  // push the previous doc onto history unless this edit coalesces with the last
  // one (same label within COALESCE_MS — e.g. a continuous slider drag)
  function pushHistory(prev, label) {
    const now = Date.now();
    const coalesce = label != null && label === lastLabel && (now - lastTime) < COALESCE_MS;
    lastLabel = label; lastTime = now;
    if (coalesce) return;
    past.push(prev); if (past.length > CAP) past.shift();
    future.length = 0;
  }

  function apply(mutator, label) {
    const next = clone(doc);
    mutator(next);
    next.meta = Object.assign({}, next.meta, { modified: new Date().toISOString() });
    pushHistory(doc, label);
    doc = next; emit();
  }

  // whole-document swap (load / new) — always a discrete history entry
  function replace(nextDoc, label) {
    past.push(doc); if (past.length > CAP) past.shift();
    future.length = 0; lastLabel = null;
    doc = nextDoc; emit();
  }

  function undo() { if (!past.length) return false; future.push(doc); doc = past.pop(); lastLabel = null; emit(); return true; }
  function redo() { if (!future.length) return false; past.push(doc); doc = future.pop(); lastLabel = null; emit(); return true; }
  const canUndo = () => past.length > 0;
  const canRedo = () => future.length > 0;
  const histLen = () => ({ past: past.length, future: future.length });

  return { init, getSnapshot, subscribe, apply, replace, undo, redo, canUndo, canRedo, histLen };
})();

// re-render hook: subscribe a component to the store
function useDoc() {
  const [, force] = React.useReducer(x => x + 1, 0);
  React.useEffect(() => DocStore.subscribe(force), []);
  return DocStore.getSnapshot();
}

// ── save / load (browser only, no backend) ──────────────────────────────────
function downloadDoc(doc) {
  const name = ((doc.meta && doc.meta.name) || "program").replace(/[^\w.-]+/g, "_");
  const blob = new Blob([serializeDoc(doc)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name + ".arcjob.json";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

// open a file picker; resolves to a validated doc
function openDocFile() {
  return new Promise((resolve, reject) => {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = ".json,application/json";
    inp.onchange = () => {
      const f = inp.files && inp.files[0];
      if (!f) return reject(new Error("no file selected"));
      f.text().then(t => resolve(deserializeDoc(t))).catch(reject);
    };
    inp.click();
  });
}

// localStorage autosave — restore last session on boot, save on every change
function autosave(doc) { try { localStorage.setItem(DOC_LS_KEY, serializeDoc(doc)); } catch (e) { /* quota/denied */ } }
function loadAutosave() { try { const s = localStorage.getItem(DOC_LS_KEY); return s ? deserializeDoc(s) : null; } catch (e) { return null; } }

DocStore.init(loadAutosave() || makeDefaultDoc());
DocStore.subscribe(() => autosave(DocStore.getSnapshot()));

Object.assign(window, {
  DOC_VERSION, DocStore, useDoc,
  makeDefaultDoc, serializeDoc, deserializeDoc, downloadDoc, openDocFile, loadAutosave,
});
