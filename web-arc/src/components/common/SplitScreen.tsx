// SplitScreen — turns the per-screen CSS-grid layouts into nested
// `react-resizable-panels` groups so users can drag any panel boundary.
// Sizes persist in localStorage via the library's useDefaultLayout hook,
// keyed off the screen's `id` and each split's `key`.

import { Fragment, type ReactNode } from "react";
import { Group, Panel as RPanel, Separator, useDefaultLayout } from "react-resizable-panels";

export type SplitDir = "h" | "v";

export type SplitNode =
  | { type: "leaf"; key: string; size?: number; minSize?: number; content: ReactNode }
  | { type: "split"; key: string; size?: number; minSize?: number; direction: SplitDir; children: SplitNode[] };

export interface SplitScreenProps {
  /** Persist key for this screen — combined with each split's key for storage. */
  id: string;
  /** Root layout tree. */
  node: SplitNode;
  /** Optional class on the outer wrapper (e.g. "screen fleet"). */
  className?: string;
}

export function SplitScreen({ id, node, className }: SplitScreenProps) {
  return (
    <div className={className} style={{ height: "100%", display: "flex" }}>
      <div style={{ flex: 1, minWidth: 0, minHeight: 0 }}>
        <RenderNode node={node} autoSaveId={id} />
      </div>
    </div>
  );
}

interface RenderNodeProps { node: SplitNode; autoSaveId: string; }

function RenderNode({ node, autoSaveId }: RenderNodeProps) {
  if (node.type === "leaf") return <>{node.content}</>;
  return <SplitGroup node={node} autoSaveId={autoSaveId} />;
}

interface SplitGroupProps {
  node: Extract<SplitNode, { type: "split" }>;
  autoSaveId: string;
}

// Storage key prefix. Bump the version when default layouts change so the
// new defaults are picked up instead of stale localStorage entries from a
// previous build.
const STORAGE_PREFIX = "arc:v2";

function SplitGroup({ node, autoSaveId }: SplitGroupProps) {
  const groupId = `${STORAGE_PREFIX}:${autoSaveId}:${node.key}`;
  const panelIds = node.children.map(c => c.key);
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({
    id: groupId,
    panelIds,
    storage: typeof window !== "undefined" ? window.localStorage : undefined,
  });

  return (
    <Group
      orientation={node.direction === "h" ? "horizontal" : "vertical"}
      defaultLayout={defaultLayout}
      onLayoutChanged={onLayoutChanged}
      style={{ height: "100%", width: "100%" }}
    >
      {node.children.map((child, i) => (
        <Fragment key={child.key}>
          {i > 0 && (
            <Separator
              className={node.direction === "h" ? "splitter splitter-v" : "splitter splitter-h"}
            />
          )}
          <RPanel
            id={child.key}
            defaultSize={child.size}
            minSize={child.minSize ?? 4}
          >
            <RenderNode node={child} autoSaveId={autoSaveId} />
          </RPanel>
        </Fragment>
      ))}
    </Group>
  );
}
