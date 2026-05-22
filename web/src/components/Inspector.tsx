/**
 * Inspector panel — displays read-only properties of the selected entity.
 *
 * Phase 1: read-only display. Editing is out of scope.
 */

import { ScrollArea } from "@/components/ui/scroll-area";
import { useUIStore } from "@/store/ui";
import type { EntityKind } from "@/store/ui";
import { useStationStore } from "@/store/station";
import type {
  FrameModel,
  RobotEntryModel,
  ToolEntryModel,
  WorkpieceEntryModel,
  FixtureEntryModel,
  IOSignalModel,
  StationModel,
} from "@/api/types";

type SelectedEntity =
  | FrameModel
  | RobotEntryModel
  | ToolEntryModel
  | WorkpieceEntryModel
  | FixtureEntryModel
  | IOSignalModel
  | null;

function findEntity(
  kind: EntityKind | null,
  name: string | null,
  station: StationModel | null,
): SelectedEntity {
  if (kind === null || name === null || station === null) return null;
  switch (kind) {
    case "frame":
      return station.frames.find((f) => f.name === name) ?? null;
    case "robot":
      return station.robots.find((r) => r.name === name) ?? null;
    case "tool":
      return station.tools.find((t) => t.name === name) ?? null;
    case "workpiece":
      return station.workpieces.find((w) => w.name === name) ?? null;
    case "fixture":
      return station.fixtures.find((f) => f.name === name) ?? null;
    case "io_signal":
      return station.io_signals.find((s) => s.name === name) ?? null;
    default:
      return null;
  }
}

interface PropertyRowProps {
  label: string;
  value: string;
}

function PropertyRow({ label, value }: PropertyRowProps) {
  return (
    <div className="flex flex-col border-b px-3 py-1.5 last:border-b-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="break-all font-mono text-xs">{value}</span>
    </div>
  );
}

export function Inspector() {
  const { selectedEntityKind, selectedEntityName } = useUIStore((s) => ({
    selectedEntityKind: s.selectedEntityKind,
    selectedEntityName: s.selectedEntityName,
  }));
  const station = useStationStore((s) => s.station);

  const entity = findEntity(selectedEntityKind, selectedEntityName, station);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Inspector
      </div>
      <ScrollArea className="flex-1">
        {entity === null ? (
          <div className="px-3 py-4 text-xs text-muted-foreground">
            Select an entity in the outliner to inspect its properties.
          </div>
        ) : (
          <div>
            {Object.entries(entity).map(([key, value]) => (
              <PropertyRow
                key={key}
                label={key}
                value={
                  typeof value === "object" && value !== null
                    ? JSON.stringify(value)
                    : String(value)
                }
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
