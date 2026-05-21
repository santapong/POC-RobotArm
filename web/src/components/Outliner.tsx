/**
 * Station outliner — collapsible flat-list tree grouped by entity kind.
 *
 * The six group headers (Frames / Robots / Tools / Workpieces / Fixtures / IO)
 * are always rendered, mirroring StationOutliner.GROUPS from the desktop.
 * Clicking an entity sets the selection in useUIStore.
 */

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useStationStore } from "@/store/station";
import { useUIStore } from "@/store/ui";
import type { EntityKind } from "@/store/ui";
import type { StationModel } from "@/api/types";

const GROUPS = [
  "Frames",
  "Robots",
  "Tools",
  "Workpieces",
  "Fixtures",
  "IO",
] as const;

type GroupName = (typeof GROUPS)[number];

const GROUP_KIND_MAP: Record<GroupName, EntityKind> = {
  Frames: "frame",
  Robots: "robot",
  Tools: "tool",
  Workpieces: "workpiece",
  Fixtures: "fixture",
  IO: "io_signal",
};

interface GroupSection {
  name: GroupName;
  items: { name: string; detail: string }[];
}

function buildSections(
  station: StationModel | null,
): GroupSection[] {
  if (station === null) {
    return GROUPS.map((g) => ({ name: g, items: [] }));
  }

  return [
    {
      name: "Frames",
      items: station.frames.map((f) => ({
        name: f.name,
        detail: `parent=${f.parent ?? "<root>"}  xyz=(${f.xyz_m.map((v) => v.toFixed(3)).join(", ")})`,
      })),
    },
    {
      name: "Robots",
      items: station.robots.map((r) => ({
        name: r.name,
        detail: `catalog=${r.robot_catalog_name}  base=${r.base_frame}`,
      })),
    },
    {
      name: "Tools",
      items: station.tools.map((t) => ({
        name: t.name,
        detail: `parent=${t.parent_frame}  mesh=${t.mesh_path ?? "(none)"}`,
      })),
    },
    {
      name: "Workpieces",
      items: station.workpieces.map((w) => ({
        name: w.name,
        detail: `parent=${w.parent_frame}  mesh=${w.mesh_path ?? "(none)"}`,
      })),
    },
    {
      name: "Fixtures",
      items: station.fixtures.map((fx) => ({
        name: fx.name,
        detail: `parent=${fx.parent_frame}  mesh=${fx.mesh_path ?? "(none)"}`,
      })),
    },
    {
      name: "IO",
      items: station.io_signals.map((sig) => ({
        name: sig.name,
        detail: `${sig.kind}  default=${String(sig.default_value)}`,
      })),
    },
  ];
}

export function Outliner() {
  const station = useStationStore((s) => s.station);
  const { selectedEntityName, select } = useUIStore((s) => ({
    selectedEntityName: s.selectedEntityName,
    select: s.select,
  }));

  const [collapsed, setCollapsed] = useState<Set<GroupName>>(new Set());

  const sections = buildSections(station);

  function toggleGroup(name: GroupName) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Outliner
      </div>
      <ScrollArea className="flex-1">
        <div className="py-1">
          {sections.map((section) => {
            const isCollapsed = collapsed.has(section.name);
            const kind = GROUP_KIND_MAP[section.name];
            return (
              <div key={section.name}>
                {/* Group header */}
                <button
                  className="flex w-full items-center gap-1 px-2 py-0.5 text-left text-xs font-semibold hover:bg-accent"
                  onClick={() => toggleGroup(section.name)}
                >
                  {isCollapsed ? (
                    <ChevronRight className="h-3 w-3 shrink-0" />
                  ) : (
                    <ChevronDown className="h-3 w-3 shrink-0" />
                  )}
                  <span>{section.name}</span>
                  <span className="ml-auto text-muted-foreground">
                    {section.items.length}
                  </span>
                </button>

                {/* Group items */}
                {!isCollapsed &&
                  section.items.map((item) => (
                    <button
                      key={item.name}
                      className={[
                        "flex w-full flex-col px-4 py-0.5 text-left text-xs hover:bg-accent",
                        selectedEntityName === item.name
                          ? "bg-accent/60 font-medium"
                          : "",
                      ].join(" ")}
                      onClick={() => select(kind, item.name)}
                    >
                      <span className="truncate">{item.name}</span>
                      <span className="truncate text-muted-foreground">
                        {item.detail}
                      </span>
                    </button>
                  ))}
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
