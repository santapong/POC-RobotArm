/**
 * SignalMapEditor — inline CRUD editor for a connection's signal list.
 *
 * Displays the current signal map for the selected connection and allows the
 * operator to add, remove, or edit signals and then save the list to the
 * server via PUT /api/io/connections/{name}/signals.
 */

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/api/client";
import { updateSignals } from "@/api/io";
import { useIoStore } from "@/store/io";
import { SignalRow } from "./SignalRow";
import type { SignalSpecModel } from "@/api/types";

interface SignalMapEditorProps {
  connectionName: string;
}

const DEFAULT_SIGNAL: SignalSpecModel = {
  name: "",
  kind: "digital_in",
  address: "",
  scale: 1.0,
  offset: 0.0,
  poll_interval_s: null,
};

export function SignalMapEditor({ connectionName }: SignalMapEditorProps): JSX.Element {
  const storedSignals = useIoStore((s) => s.signalMap[connectionName] ?? []);
  const setSignalMap = useIoStore((s) => s.setSignalMap);
  const upsertConnection = useIoStore((s) => s.upsertConnection);

  const [signals, setSignals] = useState<SignalSpecModel[]>(storedSignals);
  const [saving, setSaving] = useState(false);

  function handleChange(index: number, updated: SignalSpecModel): void {
    setSignals((prev) => prev.map((s, i) => (i === index ? updated : s)));
  }

  function handleRemove(index: number): void {
    setSignals((prev) => prev.filter((_, i) => i !== index));
  }

  function handleAdd(): void {
    setSignals((prev) => [...prev, { ...DEFAULT_SIGNAL }]);
  }

  async function handleSave(): Promise<void> {
    setSaving(true);
    try {
      const updated = await updateSignals(connectionName, signals);
      setSignalMap(connectionName, updated.signals);
      upsertConnection(updated);
      toast.success(`Signals saved for ${connectionName}`);
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
      } else {
        toast.error(String(err));
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-1">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Signals — {connectionName}
      </div>

      {signals.length === 0 && (
        <div className="text-xs text-muted-foreground">No signals defined.</div>
      )}

      {signals.map((sig, i) => (
        <SignalRow
          key={i}
          signal={sig}
          onChange={(updated) => handleChange(i, updated)}
          onRemove={() => handleRemove(i)}
        />
      ))}

      <div className="flex gap-1 pt-1">
        <Button size="sm" variant="outline" className="text-xs" onClick={handleAdd}>
          + Add signal
        </Button>
        <Button
          size="sm"
          className="text-xs"
          onClick={() => void handleSave()}
          disabled={saving}
        >
          Save
        </Button>
      </div>
    </div>
  );
}
