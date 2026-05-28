// arm-console.jsx — in-app command console (REPL) over the project document.
// Toggle with the backtick (`) key or the console button. Commands call the
// SAME DocStore mutators + helpers the UI uses (makeOp, genPicks, compileJob),
// so there is no parallel edit logic to drift. Loaded AFTER arm-doc.jsx +
// arm-program.jsx, BEFORE arm-app.jsx.

const CONSOLE_HELP = [
  "commands (ops are addressed by 1-based index, see `ls`):",
  "  help                         this list",
  "  ls                           list operations",
  "  new                          start a fresh program",
  "  save [name]                  download project (.arcjob.json)",
  "  load                         open a project file",
  "  undo / redo                  step history",
  "  add <pickplace|weld|mill|dispense>",
  "  rm <n>                       remove op n",
  "  on <n> / off <n>             enable / disable op n",
  "  tool <n> <id|name>           set op tool",
  "  part <n> <id|name>           set op part (regenerates picks)",
  "  tcp  <n> <id|name>           set op TCP frame",
  "  strat <n> <points|contour|raster|seam>",
  "  vel|acc|standoff|approach <n> <value>",
  "  weave <n> <none|sine|zigzag|triangle|trapezoid> [ampMm] [wlMm]",
  "  goto <screen>                switch screen",
  "  compile                      compile job → open in PATH",
];

function applyJob(mut, label) { DocStore.apply(d => mut(d.job), label); }

function resolveById(list, tok) {
  if (!tok) return null;
  const t = String(tok).toLowerCase();
  const norm = s => String(s).toLowerCase().replace(/[^a-z0-9]/g, "");
  return list.find(x => x.id.toLowerCase() === t) ||
         list.find(x => x.name.toLowerCase() === t || norm(x.name) === norm(tok)) || null;
}

// Run one command line; returns an array of { text, cls } output lines.
function runCommand(line, ctx) {
  const out = [];
  const log = (text, cls) => out.push({ text, cls });
  const args = String(line || "").trim().split(/\s+/).filter(Boolean);
  const cmd = (args.shift() || "").toLowerCase();
  const job = DocStore.getSnapshot().job;
  const opAt = (n) => job.ops[(parseInt(n, 10) || 0) - 1];

  switch (cmd) {
    case "": break;
    case "help": case "?": CONSOLE_HELP.forEach(l => log(l)); break;

    case "ls": case "ops":
      if (!job.ops.length) { log("(no operations)", "dim"); break; }
      job.ops.forEach((o, i) => log(
        `${String(i + 1).padStart(2)} ${o.enabled ? "◉" : "○"} ${o.name}  [${o.kind}]  tool=${o.toolId} part=${o.partId}  ${(o.params.picks || []).length}pt`,
        o.enabled ? "" : "dim"));
      break;

    case "new": DocStore.replace(makeDefaultDoc(), "new"); log("new program created", "ok"); break;

    case "save": {
      const name = args.join(" ").trim();
      if (name) DocStore.apply(d => { d.meta.name = name; d.job.name = name; }, "rename");
      downloadDoc(DocStore.getSnapshot());
      log("saved " + (name || (DocStore.getSnapshot().meta.name) || "program"), "ok");
      break;
    }
    case "load": ctx.load(); log("choose a .json project…", "info"); break;

    case "undo": log(DocStore.undo() ? "undo" : "nothing to undo", DocStore.canUndo() ? "info" : "dim"); break;
    case "redo": log(DocStore.redo() ? "redo" : "nothing to redo", "info"); break;

    case "add": {
      const kind = (args[0] || "").toUpperCase();
      if (!["PICKPLACE", "WELD", "MILL", "DISPENSE"].includes(kind)) { log("usage: add <pickplace|weld|mill|dispense>", "err"); break; }
      applyJob(j => { const nid = Math.max(0, ...j.ops.map(o => o.id)) + 1; j.ops.push(makeOp(nid, kind)); });
      log("added " + kind, "ok");
      break;
    }
    case "rm": case "del": {
      const o = opAt(args[0]); if (!o) { log("usage: rm <opIndex>", "err"); break; }
      applyJob(j => { j.ops = j.ops.filter(x => x.id !== o.id); });
      log("removed " + o.name, "ok");
      break;
    }
    case "on": case "off": {
      const o = opAt(args[0]); if (!o) { log("usage: " + cmd + " <opIndex>", "err"); break; }
      applyJob(j => { j.ops.find(x => x.id === o.id).enabled = (cmd === "on"); });
      log(o.name + " " + (cmd === "on" ? "enabled" : "disabled"), "ok");
      break;
    }
    case "tool": {
      const o = opAt(args[0]), t = resolveById(TOOL_LIBRARY, args[1]);
      if (!o || !t) { log("usage: tool <opIndex> <id|name> — " + TOOL_LIBRARY.map(x => x.id).join(", "), "err"); break; }
      applyJob(j => { j.ops.find(x => x.id === o.id).toolId = t.id; });
      log(o.name + " → tool " + t.name, "ok");
      break;
    }
    case "part": {
      const o = opAt(args[0]), p = resolveById(PART_LIBRARY, args[1]);
      if (!o || !p) { log("usage: part <opIndex> <id|name> — " + PART_LIBRARY.map(x => x.id).join(", "), "err"); break; }
      applyJob(j => { const t = j.ops.find(x => x.id === o.id); t.partId = p.id; t.params.picks = genPicks(t.strategy, p); });
      log(o.name + " → part " + p.name, "ok");
      break;
    }
    case "tcp": {
      const o = opAt(args[0]), f = resolveById(TCP_LIBRARY, args[1]);
      if (!o || !f) { log("usage: tcp <opIndex> <id|name> — " + TCP_LIBRARY.map(x => x.id).join(", "), "err"); break; }
      applyJob(j => { j.ops.find(x => x.id === o.id).tcpId = f.id; });
      log(o.name + " → tcp " + f.name, "ok");
      break;
    }
    case "strat": case "strategy": {
      const o = opAt(args[0]), s = (args[1] || "").toUpperCase();
      if (!o || !["POINTS", "CONTOUR", "RASTER", "SEAM"].includes(s)) { log("usage: strat <opIndex> <points|contour|raster|seam>", "err"); break; }
      applyJob(j => { const t = j.ops.find(x => x.id === o.id); t.strategy = s; t.params.picks = genPicks(s, findPart(t.partId)); });
      log(o.name + " → " + s, "ok");
      break;
    }
    case "vel": case "acc": case "standoff": case "approach": {
      const o = opAt(args[0]), v = parseFloat(args[1]);
      if (!o || isNaN(v)) { log("usage: " + cmd + " <opIndex> <value>", "err"); break; }
      applyJob(j => { j.ops.find(x => x.id === o.id).params[cmd] = v; });
      log(o.name + " " + cmd + " = " + v, "ok");
      break;
    }
    case "weave": {
      const o = opAt(args[0]), ty = (args[1] || "").toUpperCase();
      if (!o || !["NONE", "SINE", "ZIGZAG", "TRIANGLE", "TRAPEZOID"].includes(ty)) {
        log("usage: weave <opIndex> <none|sine|zigzag|triangle|trapezoid> [ampMm] [wlMm]", "err"); break;
      }
      const amp = args[2] != null ? parseFloat(args[2]) / 1000 : null;
      const wl = args[3] != null ? parseFloat(args[3]) / 1000 : null;
      applyJob(j => {
        const w = j.ops.find(x => x.id === o.id).params.weave;
        w.type = ty;
        if (amp != null && !isNaN(amp)) w.amplitude = amp;
        if (wl != null && !isNaN(wl)) w.wavelength = wl;
      });
      log(o.name + " weave " + ty, "ok");
      break;
    }
    case "goto": {
      const s = (args[0] || "").toLowerCase();
      const item = (window.NAV || []).find(n => n.id === s);
      if (!item) { log("usage: goto <" + (window.NAV || []).map(n => n.id).join("|") + ">", "err"); break; }
      ctx.onGoto(s); log("→ " + s, "info");
      break;
    }
    case "compile": {
      const c = compileJob(DocStore.getSnapshot().job);
      if (!c.waypoints.length) { log("nothing to compile (no enabled ops with picks)", "err"); break; }
      window.GENERATED_TRAJECTORY = c; ctx.onGoto("path");
      log("compiled " + c.waypoints.length + " waypoints · " + c.totalTime.toFixed(2) + "s → PATH", "ok");
      break;
    }
    default: log("unknown command: " + cmd + "  (type 'help')", "err");
  }
  return out;
}

function CommandConsole({ open, onClose, onGoto }) {
  useDoc(); // re-render on doc changes so `ls`/state stay live
  const [lines, setLines] = React.useState([{ text: "ARC·OPS console — type 'help'", cls: "dim" }]);
  const [input, setInput] = React.useState("");
  const [hist, setHist] = React.useState([]);
  const [hix, setHix] = React.useState(-1);
  const inputRef = React.useRef(null);
  const logRef = React.useRef(null);

  React.useEffect(() => { if (open && inputRef.current) inputRef.current.focus(); }, [open]);
  React.useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [lines, open]);

  if (!open) return null;

  const loadFile = () => openDocFile()
    .then(d => { DocStore.replace(d, "load"); setLines(l => [...l, { text: "loaded " + ((d.meta && d.meta.name) || "program"), cls: "ok" }]); })
    .catch(e => setLines(l => [...l, { text: "load failed: " + e.message, cls: "err" }]));

  const submit = () => {
    const line = input;
    const echo = [{ text: "› " + line, cls: "cmd" }];
    if (line.trim()) setHist(h => [line, ...h].slice(0, 50));
    setHix(-1);
    const out = runCommand(line, { onGoto, load: loadFile });
    setLines(l => [...l, ...echo, ...out]);
    setInput("");
  };

  const onKey = (e) => {
    if (e.key === "Enter") { e.preventDefault(); submit(); }
    else if (e.key === "`") { e.preventDefault(); onClose(); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHix(i => { const ni = Math.min(hist.length - 1, i + 1); if (hist[ni] != null) setInput(hist[ni]); return ni; }); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setHix(i => { const ni = Math.max(-1, i - 1); setInput(ni < 0 ? "" : (hist[ni] || "")); return ni; }); }
  };

  return (
    <div className="console">
      <div className="console-hd">
        <span className="mono" style={{ color: "var(--ok)" }}>▸ CONSOLE</span>
        <span className="tag dim">type 'help' · ↑↓ history · Esc / ` to close</span>
        <span style={{ flex: 1 }} />
        <span className="chip" onClick={() => setLines([])}>CLEAR</span>
        <span className="chip" onClick={onClose}>✕</span>
      </div>
      <div className="console-log" ref={logRef}>
        {lines.map((l, i) => <div key={i} className={"console-line " + (l.cls || "")}>{l.text}</div>)}
      </div>
      <div className="console-prompt">
        <span className="mono" style={{ color: "var(--ok)" }}>›</span>
        <input ref={inputRef} className="console-input mono" value={input} spellCheck={false}
          onChange={e => setInput(e.target.value)} onKeyDown={onKey}
          placeholder="add weld · tool 2 mig · weave 2 sine 4 12 · save · undo · compile" />
      </div>
    </div>
  );
}

Object.assign(window, { CommandConsole, runCommand });
