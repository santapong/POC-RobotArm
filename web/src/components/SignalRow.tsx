/**
 * SignalRow — a single row in the signal-map editor table.
 *
 * Renders editable fields for one `SignalSpecModel` and exposes callbacks
 * for changes and deletion.
 */

import type { SignalSpecModel, SignalKindModel } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";

interface SignalRowProps {
  signal: SignalSpecModel;
  onChange: (updated: SignalSpecModel) => void;
  onRemove: () => void;
}

const KIND_OPTIONS: { value: SignalKindModel; label: string }[] = [
  { value: "digital_in", label: "DI" },
  { value: "digital_out", label: "DO" },
  { value: "analog_in", label: "AI" },
  { value: "analog_out", label: "AO" },
];

export function SignalRow({ signal, onChange, onRemove }: SignalRowProps): JSX.Element {
  return (
    <div className="grid grid-cols-[1fr_56px_1fr_64px] gap-1 items-center">
      <Input
        className="h-6 text-xs px-1"
        placeholder="name"
        value={signal.name}
        onChange={(e) => onChange({ ...signal, name: e.target.value })}
      />
      <Select
        value={signal.kind}
        onValueChange={(v) => onChange({ ...signal, kind: v as SignalKindModel })}
      >
        <SelectTrigger className="h-6 text-xs px-1">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {KIND_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value} className="text-xs">
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        className="h-6 text-xs px-1"
        placeholder="address"
        value={signal.address}
        onChange={(e) => onChange({ ...signal, address: e.target.value })}
      />
      <Button
        size="sm"
        variant="ghost"
        className="h-6 text-xs px-1 text-destructive hover:text-destructive"
        onClick={onRemove}
      >
        Remove
      </Button>
    </div>
  );
}
