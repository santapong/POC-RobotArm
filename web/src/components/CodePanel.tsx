/**
 * Code preview panel — shows emitted RAPID / KRL / URScript or CAD import
 * summary depending on `useUIStore.codePanelMode`.
 *
 * The vendor selector drives `postProgram("demo", { vendor })` and caches
 * the result in `useProgramStore`. Import summaries are stored under a
 * synthetic "import" key.
 */

import { useState } from "react";
import { toast } from "sonner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useProgramStore } from "@/store/programs";
import { useUIStore } from "@/store/ui";
import { postProgram } from "@/api/programs";
import { ApiError } from "@/api/client";

type Vendor = "rapid" | "krl" | "urscript";

const VENDOR_LABELS: Record<Vendor, string> = {
  rapid: "RAPID (ABB)",
  krl: "KRL (KUKA)",
  urscript: "URScript (UR)",
};

export function CodePanel() {
  const [vendor, setVendor] = useState<Vendor>("rapid");

  const codePanelMode = useUIStore((s) => s.codePanelMode);
  const setCodePanelMode = useUIStore((s) => s.setCodePanelMode);
  const emitted = useProgramStore((s) => s.emitted);
  const setEmitted = useProgramStore((s) => s.setEmitted);

  const postKey = `demo:${vendor}`;
  const importKey = "demo:import";

  const source =
    codePanelMode === "import"
      ? (emitted[importKey] ?? "")
      : (emitted[postKey] ?? "");

  async function handleVendorChange(v: string) {
    const selected = v as Vendor;
    setVendor(selected);
    setCodePanelMode("post");

    // Fetch if not already cached
    const key = `demo:${selected}`;
    if (emitted[key] !== undefined) return;

    try {
      const result = await postProgram("demo", { vendor: selected });
      setEmitted("demo", selected, result.source);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      toast.error(`Failed to emit ${selected}: ${msg}`);
    }
  }

  const placeholder =
    codePanelMode === "import"
      ? "Use File → Import CAD... to import a mesh or DXF."
      : "Use the Run menu to emit RAPID, KRL, or URScript for the demo program.";

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar row */}
      <div className="flex items-center gap-2 border-b px-2 py-1">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {codePanelMode === "import" ? "Import Summary" : "Code Preview"}
        </span>
        {codePanelMode === "post" && (
          <Select value={vendor} onValueChange={(v) => void handleVendorChange(v)}>
            <SelectTrigger className="h-6 w-44 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.entries(VENDOR_LABELS) as [Vendor, string][]).map(
                ([v, label]) => (
                  <SelectItem key={v} value={v} className="text-xs">
                    {label}
                  </SelectItem>
                ),
              )}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Code area */}
      <div className="min-h-0 flex-1 overflow-auto">
        {source ? (
          <pre className="h-full overflow-auto p-2 font-mono text-xs leading-5 text-foreground">
            {source}
          </pre>
        ) : (
          <p className="px-3 py-4 text-xs text-muted-foreground">
            {placeholder}
          </p>
        )}
      </div>
    </div>
  );
}
