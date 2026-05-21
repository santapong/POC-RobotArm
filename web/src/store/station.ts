/**
 * Zustand store mirroring the server-side StationModel.
 *
 * Refetched via GET /api/station after any mutating operation. The store
 * holds a nullable station; null means "not yet loaded".
 */

import { create } from "zustand";
import type { StationModel } from "@/api/types";

interface StationState {
  station: StationModel | null;
  setStation: (s: StationModel) => void;
  clear: () => void;
}

export const useStationStore = create<StationState>()((set) => ({
  station: null,

  setStation: (s) => set({ station: s }),

  clear: () => set({ station: null }),
}));
