// Command-console dispatch. Each command operates on the SAME store actions
// and lib helpers the UI uses (makeOp / genPicks / compileJob / DocStore), so
// there's no parallel edit logic to drift.

import type { Job, OpKind, Strategy } from "@/types";
import { PART_LIBRARY, TCP_LIBRARY, TOOL_LIBRARY, findPart } from "@/lib/catalogs";
import { downloadDoc, makeDefaultDoc } from "@/lib/doc";
import { compileJob, genPicks, makeOp } from "@/lib/program";
import { useDocStore } from "@/store/useDocStore";
import { useUiStore, SCREENS, type Screen } from "@/store/useUiStore";

export interface CmdLine { text: string; cls?: "ok" | "err" | "info" | "dim" | "cmd"; }

export const CONSOLE_HELP: string[] = [
  "commands (ops are addressed by 1-based index, see `ls`):",
  "  help                         this list",
  "  ls                           list operations",
  "  new                          start a fresh program",
  "  save                         download project (.arcjob.json)",
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

const KINDS: OpKind[] = ["PICKPLACE", "WELD", "MILL", "DISPENSE"];
const STRATS: Strategy[] = ["POINTS", "CONTOUR", "RASTER", "SEAM"];
const WEAVES = ["NONE", "ZIGZAG", "SINE", "TRIANGLE", "TRAPEZOID"] as const;

function resolveById<T extends { id: string; name: string }>(list: T[], tok: string | undefined): T | null {
  if (!tok) return null;
  const t = tok.toLowerCase();
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  return list.find(x => x.id.toLowerCase() === t) ||
         list.find(x => x.name.toLowerCase() === t || norm(x.name) === norm(tok)) || null;
}

const applyJob = (mut: (j: Job) => void, label?: string) =>
  useDocStore.getState().apply(d => mut(d.job), label);

export interface CmdContext {
  load: () => void;
}

export function runCommand(line: string, ctx: CmdContext): CmdLine[] {
  const out: CmdLine[] = [];
  const log = (text: string, cls?: CmdLine["cls"]) => out.push({ text, cls });
  const args = String(line || "").trim().split(/\s+/).filter(Boolean);
  const cmd = (args.shift() || "").toLowerCase();
  const job = useDocStore.getState().doc.job;
  const opAt = (n: string | undefined) => job.ops[(parseInt(n || "0", 10) || 0) - 1];

  switch (cmd) {
    case "": break;
    case "help": case "?":
      CONSOLE_HELP.forEach(l => log(l));
      break;

    case "ls": case "ops":
      if (!job.ops.length) { log("(no operations)", "dim"); break; }
      job.ops.forEach((o, i) => log(
        `${String(i + 1).padStart(2)} ${o.enabled ? "◉" : "○"} ${o.name}  [${o.kind}]  tool=${o.toolId} part=${o.partId}  ${(o.params.picks || []).length}pt`,
        o.enabled ? undefined : "dim",
      ));
      break;

    case "new":
      useDocStore.getState().replace(makeDefaultDoc(), "new");
      log("new program created", "ok");
      break;

    case "save":
      downloadDoc(useDocStore.getState().doc);
      log("saved", "ok");
      break;
    case "load":
      ctx.load();
      log("choose a .json project…", "info");
      break;

    case "undo": log(useDocStore.getState().undo() ? "undo" : "nothing to undo", "info"); break;
    case "redo": log(useDocStore.getState().redo() ? "redo" : "nothing to redo", "info"); break;

    case "add": {
      const kind = (args[0] || "").toUpperCase() as OpKind;
      if (!KINDS.includes(kind)) { log("usage: add <pickplace|weld|mill|dispense>", "err"); break; }
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
      applyJob(j => { const t = j.ops.find(x => x.id === o.id); if (t) t.enabled = cmd === "on"; });
      log(o.name + " " + (cmd === "on" ? "enabled" : "disabled"), "ok");
      break;
    }
    case "tool": {
      const o = opAt(args[0]); const t = resolveById(TOOL_LIBRARY, args[1]);
      if (!o || !t) { log("usage: tool <opIndex> <id|name>", "err"); break; }
      applyJob(j => { const x = j.ops.find(p => p.id === o.id); if (x) x.toolId = t.id; });
      log(o.name + " → tool " + t.name, "ok");
      break;
    }
    case "part": {
      const o = opAt(args[0]); const p = resolveById(PART_LIBRARY, args[1]);
      if (!o || !p) { log("usage: part <opIndex> <id|name>", "err"); break; }
      applyJob(j => {
        const x = j.ops.find(q => q.id === o.id); if (!x) return;
        x.partId = p.id;
        x.params.picks = genPicks(x.strategy, p);
      });
      log(o.name + " → part " + p.name, "ok");
      break;
    }
    case "tcp": {
      const o = opAt(args[0]); const f = resolveById(TCP_LIBRARY, args[1]);
      if (!o || !f) { log("usage: tcp <opIndex> <id|name>", "err"); break; }
      applyJob(j => { const x = j.ops.find(p => p.id === o.id); if (x) x.tcpId = f.id; });
      log(o.name + " → tcp " + f.name, "ok");
      break;
    }
    case "strat": case "strategy": {
      const o = opAt(args[0]); const s = (args[1] || "").toUpperCase() as Strategy;
      if (!o || !STRATS.includes(s)) { log("usage: strat <opIndex> <points|contour|raster|seam>", "err"); break; }
      applyJob(j => {
        const x = j.ops.find(p => p.id === o.id); if (!x) return;
        x.strategy = s;
        x.params.picks = genPicks(s, findPart(x.partId));
      });
      log(o.name + " → " + s, "ok");
      break;
    }
    case "vel": case "acc": case "standoff": case "approach": {
      const o = opAt(args[0]); const v = parseFloat(args[1]);
      if (!o || isNaN(v)) { log("usage: " + cmd + " <opIndex> <value>", "err"); break; }
      applyJob(j => {
        const x = j.ops.find(p => p.id === o.id); if (!x) return;
        if (cmd === "vel") x.params.vel = v;
        else if (cmd === "acc") x.params.acc = v;
        else if (cmd === "standoff") x.params.standoff = v;
        else x.params.approach = v;
      });
      log(o.name + " " + cmd + " = " + v, "ok");
      break;
    }
    case "weave": {
      const o = opAt(args[0]); const ty = (args[1] || "").toUpperCase() as typeof WEAVES[number];
      if (!o || !WEAVES.includes(ty)) { log("usage: weave <opIndex> <none|sine|zigzag|triangle|trapezoid> [ampMm] [wlMm]", "err"); break; }
      const amp = args[2] != null ? parseFloat(args[2]) / 1000 : null;
      const wl = args[3] != null ? parseFloat(args[3]) / 1000 : null;
      applyJob(j => {
        const x = j.ops.find(p => p.id === o.id); if (!x) return;
        x.params.weave.type = ty;
        if (amp != null && !isNaN(amp)) x.params.weave.amplitude = amp;
        if (wl != null && !isNaN(wl)) x.params.weave.wavelength = wl;
      });
      log(o.name + " weave " + ty, "ok");
      break;
    }
    case "goto": {
      const s = (args[0] || "").toLowerCase() as Screen;
      if (!SCREENS.includes(s)) { log("usage: goto <" + SCREENS.join("|") + ">", "err"); break; }
      useUiStore.getState().setScreen(s);
      log("→ " + s, "info");
      break;
    }
    case "compile": {
      const c = compileJob(useDocStore.getState().doc.job);
      if (!c.waypoints.length) { log("nothing to compile", "err"); break; }
      useUiStore.getState().openInPath(c);
      log("compiled " + c.waypoints.length + " waypoints · " + c.totalTime.toFixed(2) + "s → PATH", "ok");
      break;
    }
    default:
      log("unknown command: " + cmd + "  (type 'help')", "err");
  }
  return out;
}
