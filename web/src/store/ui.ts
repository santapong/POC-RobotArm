/**
 * UI state store: selection, panel visibility, open dialogs, banners.
 */

import { create } from "zustand";
import type { WsEvent } from "@/api/types";

export type EntityKind =
  | "frame"
  | "robot"
  | "tool"
  | "workpiece"
  | "fixture"
  | "io_signal";

export type DialogName =
  | "new"
  | "open"
  | "save"
  | "import"
  | "about"
  | null;

export type CodePanelMode = "post" | "import";

interface UIState {
  selectedEntityKind: EntityKind | null;
  selectedEntityName: string | null;
  activeDialog: DialogName;
  codePanelMode: CodePanelMode;
  // Events log (last N events from /ws/events)
  events: WsEvent[];
  // In-flight operation banner text (empty = no banner)
  operationBanner: string;

  select: (kind: EntityKind | null, name: string | null) => void;
  setDialog: (d: DialogName) => void;
  setCodePanelMode: (mode: CodePanelMode) => void;
  pushEvent: (event: WsEvent) => void;
  setBanner: (text: string) => void;
}

const MAX_EVENTS = 100;

export const useUIStore = create<UIState>()((set) => ({
  selectedEntityKind: null,
  selectedEntityName: null,
  activeDialog: null,
  codePanelMode: "post",
  events: [],
  operationBanner: "",

  select: (kind, name) =>
    set({ selectedEntityKind: kind, selectedEntityName: name }),

  setDialog: (d) => set({ activeDialog: d }),

  setCodePanelMode: (mode) => set({ codePanelMode: mode }),

  pushEvent: (event) =>
    set((state) => ({
      events:
        state.events.length >= MAX_EVENTS
          ? [...state.events.slice(1), event]
          : [...state.events, event],
    })),

  setBanner: (text) => set({ operationBanner: text }),
}));
