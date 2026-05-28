// Project document = serialized form of the editable state (job + meta +
// active TCP). The store (store/useDocStore.ts) holds it in memory and runs
// the undo/redo history; this module owns the on-disk format.

import type { Doc, Job } from "@/types";
import { DEFAULT_JOB } from "./program";

// v1: { version, meta, job, activeTcpId }
// v2: + optional `robotId` (RobotModel selection). Missing → default.
export const DOC_VERSION = 2;
// localStorage key kept stable across the v1→v2 migration; the in-memory
// shape is upgraded on read by deserializeDoc().
export const DOC_LS_KEY = "arc_ops_project_v1";

export function makeDefaultDoc(): Doc {
  const base: Job = JSON.parse(JSON.stringify(DEFAULT_JOB));
  return {
    version: DOC_VERSION,
    meta: { name: base.name || "Untitled Program", author: base.author || "OP·KOSTA", modified: new Date().toISOString() },
    job: base,
    activeTcpId: base.activeTcpId || "tcp-tip",
    // Leave robotId unset; resolveRobot() falls back to DEFAULT_ROBOT_ID.
  };
}

export function serializeDoc(doc: Doc): string {
  const payload: Record<string, unknown> = {
    version: DOC_VERSION,
    meta: doc.meta,
    job: doc.job,
    activeTcpId: doc.activeTcpId,
  };
  if (doc.robotId) payload.robotId = doc.robotId;
  return JSON.stringify(payload, null, 2);
}

export function deserializeDoc(input: string | unknown): Doc {
  const o = typeof input === "string" ? JSON.parse(input) : input;
  if (!o || typeof o !== "object") throw new Error("Not a valid ARC·OPS project");
  const j = (o as { job?: Job }).job;
  if (!j || !Array.isArray(j.ops)) throw new Error("Not a valid ARC·OPS project (missing job.ops)");
  const m = (o as { meta?: Doc["meta"] }).meta;
  const tcp = (o as { activeTcpId?: string }).activeTcpId;
  const robotId = (o as { robotId?: string }).robotId;   // v1 docs leave this unset
  return {
    version: DOC_VERSION,
    meta: m ?? { name: "Imported Program", author: "OP", modified: new Date().toISOString() },
    job: j,
    activeTcpId: tcp ?? j.activeTcpId ?? "tcp-tip",
    ...(robotId ? { robotId } : {}),
  };
}

export function downloadDoc(doc: Doc): void {
  const name = ((doc.meta && doc.meta.name) || "program").replace(/[^\w.-]+/g, "_");
  const blob = new Blob([serializeDoc(doc)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name + ".arcjob.json";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export function openDocFile(): Promise<Doc> {
  return new Promise<Doc>((resolve, reject) => {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = ".json,application/json";
    inp.onchange = () => {
      const f = inp.files && inp.files[0];
      if (!f) { reject(new Error("no file selected")); return; }
      f.text().then(t => resolve(deserializeDoc(t))).catch(reject);
    };
    inp.click();
  });
}

export function autosave(doc: Doc): void {
  try { localStorage.setItem(DOC_LS_KEY, serializeDoc(doc)); } catch { /* quota/denied */ }
}
export function loadAutosave(): Doc | null {
  try { const s = localStorage.getItem(DOC_LS_KEY); return s ? deserializeDoc(s) : null; } catch { return null; }
}
