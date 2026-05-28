// Backtick-toggled REPL overlay. Reads from useDocStore so `ls` and similar
// stay live as the doc changes; commands themselves run via commands.ts which
// calls the same DocStore actions the UI uses.

import { useEffect, useRef, useState } from "react";
import { openDocFile } from "@/lib/doc";
import { useDocStore } from "@/store/useDocStore";
import { useUiStore } from "@/store/useUiStore";
import { runCommand, type CmdLine } from "./commands";

export function CommandConsole() {
  const open = useUiStore(s => s.consoleOpen);
  const setOpen = useUiStore(s => s.setConsoleOpen);
  useDocStore();   // re-render on doc change so `ls` reflects current state

  const [lines, setLines] = useState<CmdLine[]>([{ text: "ARC·OPS console — type 'help'", cls: "dim" }]);
  const [input, setInput] = useState("");
  const [hist, setHist] = useState<string[]>([]);
  const [, setHix] = useState(-1);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { if (open && inputRef.current) inputRef.current.focus(); }, [open]);
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [lines, open]);

  if (!open) return null;

  const loadFile = () => openDocFile()
    .then(d => {
      useDocStore.getState().replace(d, "load");
      setLines(l => [...l, { text: "loaded " + (d.meta?.name || "program"), cls: "ok" }]);
    })
    .catch(e => setLines(l => [...l, { text: "load failed: " + (e as Error).message, cls: "err" }]));

  const submit = () => {
    const line = input;
    const echo: CmdLine = { text: "› " + line, cls: "cmd" };
    if (line.trim()) setHist(h => [line, ...h].slice(0, 50));
    setHix(-1);
    const out = runCommand(line, { load: loadFile });
    setLines(l => [...l, echo, ...out]);
    setInput("");
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); submit(); }
    else if (e.key === "`") { e.preventDefault(); setOpen(false); }
    else if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
    else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHix(i => { const ni = Math.min(hist.length - 1, i + 1); if (hist[ni] != null) setInput(hist[ni]); return ni; });
    }
    else if (e.key === "ArrowDown") {
      e.preventDefault();
      setHix(i => { const ni = Math.max(-1, i - 1); setInput(ni < 0 ? "" : (hist[ni] || "")); return ni; });
    }
  };

  return (
    <div className="console">
      <div className="console-hd">
        <span className="mono" style={{ color: "var(--ok)" }}>▸ CONSOLE</span>
        <span className="tag dim">type 'help' · ↑↓ history · Esc / ` to close</span>
        <span style={{ flex: 1 }} />
        <span className="chip" onClick={() => setLines([])}>CLEAR</span>
        <span className="chip" onClick={() => setOpen(false)}>✕</span>
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
