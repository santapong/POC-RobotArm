/**
 * Bottom panel wrapping CodePanel and VisionPanel in shadcn Tabs.
 *
 * A chevron button at the top-right toggles between:
 *   - collapsed: h-56 (default, same as the old CodePanel height)
 *   - expanded:  h-[40vh]
 *
 * Height state is local — no Zustand involved.
 */

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CodePanel } from "./CodePanel";
import { VisionPanel } from "./VisionPanel";
import { PlanPanel } from "./PlanPanel";
import { IoPanel } from "./IoPanel";

export function BottomPanel() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`shrink-0 border-t transition-[height] duration-150 ${
        expanded ? "h-[40vh]" : "h-56"
      }`}
    >
      <Tabs defaultValue="code" className="flex h-full flex-col">
        {/* Tab bar */}
        <div className="flex items-center justify-between border-b px-2">
          <TabsList className="h-8 rounded-none bg-transparent p-0">
            <TabsTrigger
              value="code"
              className="rounded-none border-b-2 border-transparent px-3 py-1 text-xs data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground"
            >
              Code
            </TabsTrigger>
            <TabsTrigger
              value="vision"
              className="rounded-none border-b-2 border-transparent px-3 py-1 text-xs data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground"
            >
              Vision
            </TabsTrigger>
            <TabsTrigger
              value="plan"
              className="rounded-none border-b-2 border-transparent px-3 py-1 text-xs data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground"
            >
              Plan
            </TabsTrigger>
            <TabsTrigger
              value="io"
              className="rounded-none border-b-2 border-transparent px-3 py-1 text-xs data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground"
            >
              I/O
            </TabsTrigger>
          </TabsList>

          {/* Expand/collapse chevron */}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={expanded ? "Collapse panel" : "Expand panel"}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </button>
        </div>

        {/* Tab content — each fills remaining height */}
        <TabsContent value="code" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <CodePanel />
        </TabsContent>

        <TabsContent value="vision" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <VisionPanel />
        </TabsContent>

        <TabsContent value="plan" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <PlanPanel />
        </TabsContent>

        <TabsContent value="io" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <IoPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
