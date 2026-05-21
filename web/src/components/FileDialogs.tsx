/**
 * File dialog helpers for New / Open / Save / Import CAD operations.
 *
 * Exports a `useFileDialogs()` hook that returns handlers for each operation.
 * The dialogs themselves use shadcn Dialog with hidden file inputs where
 * needed. The parent (App.tsx) mounts <FileDialogs /> to render the actual
 * modals.
 */

import { useRef } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/store/ui";
import { useStationStore } from "@/store/station";
import { useProgramStore } from "@/store/programs";
import { newStation, loadStation, saveStation } from "@/api/station";
import { importAsset } from "@/api/assets";
import { ApiError } from "@/api/client";

export function useFileDialogs() {
  const setDialog = useUIStore((s) => s.setDialog);
  return { setDialog };
}

export function FileDialogs() {
  const activeDialog = useUIStore((s) => s.activeDialog);
  const setDialog = useUIStore((s) => s.setDialog);
  const setCodePanelMode = useUIStore((s) => s.setCodePanelMode);
  const setStation = useStationStore((s) => s.setStation);
  const setEmitted = useProgramStore((s) => s.setEmitted);

  const openFileRef = useRef<HTMLInputElement>(null);
  const importFileRef = useRef<HTMLInputElement>(null);

  // ---- New Station ---------------------------------------------------------
  async function handleNew() {
    try {
      const station = await newStation();
      setStation(station);
      toast.info("New station created");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`New station failed: ${msg}`);
    } finally {
      setDialog(null);
    }
  }

  // ---- Open Station --------------------------------------------------------
  function handleOpenPickFile() {
    openFileRef.current?.click();
  }

  async function handleOpenFileChange(
    e: React.ChangeEvent<HTMLInputElement>,
  ) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const station = await loadStation(file);
      setStation(station);
      toast.info(`Loaded station: ${station.name}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Open failed: ${msg}`);
    } finally {
      // Reset so re-selecting the same file fires the event again
      e.target.value = "";
      setDialog(null);
    }
  }

  // ---- Save Station --------------------------------------------------------
  async function handleSave() {
    try {
      const result = await saveStation();
      const stationName =
        (result.json["name"] as string | undefined) ?? "station";
      const blob = new Blob([JSON.stringify(result.json, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${stationName}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.info(`Station saved as ${stationName}.json`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Save failed: ${msg}`);
    } finally {
      setDialog(null);
    }
  }

  // ---- Import CAD ----------------------------------------------------------
  function handleImportPickFile() {
    importFileRef.current?.click();
  }

  async function handleImportFileChange(
    e: React.ChangeEvent<HTMLInputElement>,
  ) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const result = await importAsset(file);
      // Store the summary string using the synthetic "import" key
      setEmitted("demo", "import", result.summary);
      setCodePanelMode("import");
      toast.info(`Imported ${result.filename}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Import failed: ${msg}`);
    } finally {
      e.target.value = "";
      setDialog(null);
    }
  }

  return (
    <>
      {/* Hidden file inputs */}
      <input
        ref={openFileRef}
        type="file"
        accept="application/json"
        className="hidden"
        onChange={(e) => void handleOpenFileChange(e)}
      />
      <input
        ref={importFileRef}
        type="file"
        accept=".stl,.obj,.ply,.dxf"
        className="hidden"
        onChange={(e) => void handleImportFileChange(e)}
      />

      {/* New Station confirmation dialog */}
      <Dialog
        open={activeDialog === "new"}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Station</DialogTitle>
            <DialogDescription>
              This will replace the current station with an empty one. Any
              unsaved changes will be lost.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button onClick={() => void handleNew()}>Create New</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Open Station dialog */}
      <Dialog
        open={activeDialog === "open"}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Open Station</DialogTitle>
            <DialogDescription>
              Select a station JSON file to load.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button onClick={handleOpenPickFile}>Choose File...</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Save Station — fires immediately, no modal needed */}
      {activeDialog === "save" && (
        <SaveTrigger onSave={() => void handleSave()} />
      )}

      {/* Import CAD dialog */}
      <Dialog
        open={activeDialog === "import"}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Import CAD</DialogTitle>
            <DialogDescription>
              Select a mesh (.stl, .obj, .ply) or DXF file to import.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button onClick={handleImportPickFile}>Choose File...</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * Invisible helper component that fires the save action on mount, then closes
 * itself. Used to avoid a modal for the save action (mirrors desktop behaviour
 * where Save fires immediately without a confirmation).
 */
function SaveTrigger({ onSave }: { onSave: () => void }) {
  // Use a plain useEffect substitute by calling during render via a ref trick
  // is not ideal, so instead we just render a "Saving..." indicator that calls
  // onSave via an auto-click pattern.
  //
  // Simpler: call onSave() directly on first render.
  // This is intentionally side-effect-on-render; acceptable for a fire-once trigger.
  const firedRef = useRef(false);
  if (!firedRef.current) {
    firedRef.current = true;
    // Schedule via setTimeout so we're past the render phase
    setTimeout(onSave, 0);
  }
  return null;
}
