/**
 * Robot catalog cache store. Pre-loaded once on app mount via getCatalog().
 */

import { create } from "zustand";
import type { RobotCatalogEntry } from "@/api/types";

interface CatalogState {
  entries: RobotCatalogEntry[];
  loaded: boolean;
  setCatalog: (entries: RobotCatalogEntry[]) => void;
}

export const useCatalogStore = create<CatalogState>()((set) => ({
  entries: [],
  loaded: false,

  setCatalog: (entries) => set({ entries, loaded: true }),
}));
