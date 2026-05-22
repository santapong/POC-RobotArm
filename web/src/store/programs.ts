/**
 * Program cache store: ProgramModels by id, last-emitted code by (id, vendor).
 */

import { create } from "zustand";
import type { ProgramModel } from "@/api/types";

interface ProgramsState {
  programs: Record<string, ProgramModel>;
  // Key is "<id>:<vendor>", value is the emitted source string
  emitted: Record<string, string>;

  setProgram: (id: string, program: ProgramModel) => void;
  setEmitted: (id: string, vendor: string, source: string) => void;
}

export const useProgramStore = create<ProgramsState>()((set) => ({
  programs: {},
  emitted: {},

  setProgram: (id, program) =>
    set((state) => ({ programs: { ...state.programs, [id]: program } })),

  setEmitted: (id, vendor, source) =>
    set((state) => ({
      emitted: { ...state.emitted, [`${id}:${vendor}`]: source },
    })),
}));
