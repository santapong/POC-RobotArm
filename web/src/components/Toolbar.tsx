/**
 * Application toolbar with File / Robot / Run / Help dropdown menus.
 *
 * Uses shadcn DropdownMenu. Each item dispatches a REST action or opens a
 * dialog via `useUIStore.setDialog`. Catalog entries come from
 * `useCatalogStore` (pre-loaded at app mount).
 */

import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/store/ui";
import { useCatalogStore } from "@/store/catalog";
import { useStationStore } from "@/store/station";
import { useProgramStore } from "@/store/programs";
import { spawnRobot } from "@/api/station";
import { postProgram } from "@/api/programs";
import { ApiError } from "@/api/client";

export function Toolbar() {
  const setDialog = useUIStore((s) => s.setDialog);
  const setCodePanelMode = useUIStore((s) => s.setCodePanelMode);
  const catalogEntries = useCatalogStore((s) => s.entries);
  const setStation = useStationStore((s) => s.setStation);
  const setEmitted = useProgramStore((s) => s.setEmitted);

  async function handleSpawn(catalogName: string) {
    try {
      const result = await spawnRobot({ catalog_name: catalogName });
      setStation(result.station);
      toast.info(`Spawned ${catalogName}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Spawn failed: ${msg}`);
    }
  }

  async function handleEmit(vendor: "rapid" | "krl" | "urscript") {
    try {
      const result = await postProgram("demo", { vendor });
      setEmitted("demo", vendor, result.source);
      setCodePanelMode("post");
      toast.info(`Emitted ${vendor.toUpperCase()}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Emit failed: ${msg}`);
    }
  }

  return (
    <div className="flex h-full items-center gap-1 px-2">
      {/* File menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            File
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={() => setDialog("new")}>
            New Station
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setDialog("open")}>
            Open Station...
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setDialog("save")}>
            Save Station
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setDialog("import")}>
            Import CAD...
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Robot menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            Robot
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {catalogEntries.length === 0 ? (
            <DropdownMenuItem disabled>Loading catalog...</DropdownMenuItem>
          ) : (
            catalogEntries.map((entry) => (
              <DropdownMenuItem
                key={entry.name}
                onSelect={() => void handleSpawn(entry.name)}
              >
                Spawn {entry.name}
              </DropdownMenuItem>
            ))
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Run menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            Run
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={() => void handleEmit("rapid")}>
            Emit RAPID
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => void handleEmit("krl")}>
            Emit KRL
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => void handleEmit("urscript")}>
            Emit URScript
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Help menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            Help
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={() => setDialog("about")}>
            About
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
