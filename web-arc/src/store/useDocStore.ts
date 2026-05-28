// Project document store (Zustand). Owns the single editable Doc, the
// undo/redo history (past/future snapshot stacks), the drag-coalescing rule
// (consecutive same-label edits within 400 ms collapse into one history
// entry), and autosaves the doc to localStorage. Ports the prototype's
// hand-rolled DocStore into idiomatic React/Zustand.

import { create } from "zustand";
import type { Doc, Job } from "@/types";
import { autosave, loadAutosave, makeDefaultDoc } from "@/lib/doc";

interface DocState {
  doc: Doc;
  past: Doc[];
  future: Doc[];
  apply: (mut: (doc: Doc) => void, label?: string) => void;
  replace: (next: Doc, label?: string) => void;
  undo: () => boolean;
  redo: () => boolean;
}

const HISTORY_CAP = 100;
const COALESCE_MS = 400;
let _lastLabel: string | null = null;
let _lastTime = 0;

const clone = <T>(o: T): T => JSON.parse(JSON.stringify(o));

function pushHistory(past: Doc[], prev: Doc, label: string | undefined): Doc[] {
  const now = Date.now();
  const coalesce = label != null && label === _lastLabel && (now - _lastTime) < COALESCE_MS;
  _lastLabel = label ?? null;
  _lastTime = now;
  if (coalesce) return past;
  const next = past.length >= HISTORY_CAP ? past.slice(1) : past.slice();
  next.push(prev);
  return next;
}

export const useDocStore = create<DocState>((set) => ({
  doc: loadAutosave() ?? makeDefaultDoc(),
  past: [],
  future: [],
  apply: (mut, label) => set((s) => {
    const next = clone(s.doc);
    mut(next);
    next.meta = { ...next.meta, modified: new Date().toISOString() };
    return {
      doc: next,
      past: pushHistory(s.past, s.doc, label),
      future: [],
    };
  }),
  replace: (next, _label) => set((s) => {
    _lastLabel = null;
    return {
      doc: next,
      past: pushHistory(s.past, s.doc, undefined),
      future: [],
    };
  }),
  undo: () => {
    let ok = false;
    set((s) => {
      if (!s.past.length) return s;
      ok = true;
      _lastLabel = null;
      const past = s.past.slice(0, -1);
      const prev = s.past[s.past.length - 1];
      return { doc: prev, past, future: [...s.future, s.doc] };
    });
    return ok;
  },
  redo: () => {
    let ok = false;
    set((s) => {
      if (!s.future.length) return s;
      ok = true;
      _lastLabel = null;
      const future = s.future.slice(0, -1);
      const next = s.future[s.future.length - 1];
      return { doc: next, past: [...s.past, s.doc], future };
    });
    return ok;
  },
}));

// Autosave on every doc change. Lives outside the store so listeners are
// installed once at module load (not per component).
let _lastSaved: Doc | null = null;
useDocStore.subscribe((s) => {
  if (s.doc !== _lastSaved) { autosave(s.doc); _lastSaved = s.doc; }
});

// Convenience selectors — `useDocStore(useJob)` re-renders only when job
// identity changes, not on past/future updates.
export const useJob = (s: DocState): Job => s.doc.job;
export const useDoc = (s: DocState): Doc => s.doc;
export const useCanUndo = (s: DocState): boolean => s.past.length > 0;
export const useCanRedo = (s: DocState): boolean => s.future.length > 0;
