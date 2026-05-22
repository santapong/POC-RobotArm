/**
 * IoValueStream — right-column panel showing live I/O events and write controls.
 *
 * Displays recent events for the selected connection in a scrollable table,
 * and provides a signal dropdown + value input + Write button.
 */

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ApiError } from "@/api/client";
import { writeSignal } from "@/api/io";
import { useIoStore } from "@/store/io";

interface IoValueStreamProps {
  connectionName: string | null;
}

function protocolLabel(protocol: string): string {
  switch (protocol) {
    case "modbus_tcp":
      return "TCP";
    case "modbus_rtu":
      return "RTU";
    case "opcua":
      return "OPC";
    case "mqtt":
      return "MQTT";
    default:
      return protocol.slice(0, 4).toUpperCase();
  }
}

export function IoValueStream({ connectionName }: IoValueStreamProps): JSX.Element {
  const recentEvents = useIoStore((s) => s.recentEvents);
  const connections = useIoStore((s) => s.connections);
  const signalMap = useIoStore((s) => s.signalMap);

  const [writeSignalName, setWriteSignalName] = useState<string>("");
  const [writeValue, setWriteValue] = useState<string>("0");
  const [writing, setWriting] = useState(false);

  // Filter events to the selected connection.
  const filteredEvents = connectionName !== null
    ? recentEvents.filter((e) => e.connection === connectionName)
    : recentEvents;

  // Available signals for the write dropdown.
  const availableSignals =
    connectionName !== null
      ? (signalMap[connectionName] ?? []).filter(
          (s) => s.kind === "digital_out" || s.kind === "analog_out",
        )
      : [];

  const selectedConn =
    connectionName !== null ? connections[connectionName] : undefined;

  async function handleWrite(): Promise<void> {
    if (!connectionName || !writeSignalName) return;
    const raw = parseFloat(writeValue);
    const value = isNaN(raw) ? 0 : raw;
    setWriting(true);
    try {
      await writeSignal(connectionName, writeSignalName, { value });
      toast.success(`Written ${value} to ${connectionName}.${writeSignalName}`);
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
      } else {
        toast.error(String(err));
      }
    } finally {
      setWriting(false);
    }
  }

  return (
    <div className="flex h-full flex-col gap-2 overflow-hidden">
      {/* Live values table */}
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Live values{connectionName !== null ? ` — ${connectionName}` : " — all connections"}
      </div>

      <ScrollArea className="flex-1 rounded border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b bg-muted/50 text-muted-foreground">
              <th className="px-2 py-1 text-left font-medium">Signal</th>
              <th className="px-2 py-1 text-left font-medium">Proto</th>
              <th className="px-2 py-1 text-left font-medium">Address</th>
              <th className="px-2 py-1 text-right font-medium">Value</th>
              <th className="px-2 py-1 text-right font-medium">t (s)</th>
            </tr>
          </thead>
          <tbody>
            {filteredEvents.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-2 py-3 text-center text-muted-foreground"
                >
                  No events yet.
                </td>
              </tr>
            )}
            {[...filteredEvents].reverse().map((ev, idx) => {
              const proto =
                ev.connection in connections
                  ? protocolLabel(connections[ev.connection].config.protocol)
                  : "—";
              const sigSpec =
                ev.signal !== null && ev.connection in (signalMap ?? {})
                  ? (signalMap[ev.connection] ?? []).find(
                      (s) => s.name === ev.signal,
                    )
                  : undefined;
              return (
                <tr
                  key={idx}
                  className="border-b last:border-0 hover:bg-muted/30"
                >
                  <td className="px-2 py-0.5">
                    {ev.connection}.{ev.signal ?? "—"}
                  </td>
                  <td className="px-2 py-0.5 text-muted-foreground">{proto}</td>
                  <td className="px-2 py-0.5 text-muted-foreground">
                    {sigSpec?.address ?? "—"}
                  </td>
                  <td className="px-2 py-0.5 text-right">
                    {ev.value !== null ? String(ev.value) : "—"}
                  </td>
                  <td className="px-2 py-0.5 text-right text-muted-foreground">
                    {ev.monotonic_s.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ScrollArea>

      {/* Write controls */}
      <div className="space-y-1 rounded border p-2">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Write a signal
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={writeSignalName}
            onValueChange={setWriteSignalName}
            disabled={availableSignals.length === 0}
          >
            <SelectTrigger className="h-7 flex-1 text-xs">
              <SelectValue
                placeholder={
                  connectionName === null
                    ? "Select a connection"
                    : availableSignals.length === 0
                    ? "No output signals"
                    : "Signal"
                }
              />
            </SelectTrigger>
            <SelectContent>
              {availableSignals.map((s) => (
                <SelectItem key={s.name} value={s.name} className="text-xs">
                  {s.name} ({s.address})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Input
            className="h-7 w-20 text-xs"
            placeholder="value"
            value={writeValue}
            onChange={(e) => setWriteValue(e.target.value)}
          />

          <Button
            size="sm"
            className="h-7 text-xs"
            onClick={() => void handleWrite()}
            disabled={
              writing ||
              !connectionName ||
              !writeSignalName ||
              selectedConn?.status !== "open"
            }
          >
            Send
          </Button>
        </div>
        {selectedConn !== undefined && selectedConn.status !== "open" && (
          <div className="text-xs text-muted-foreground">
            Connection is {selectedConn.status} — writes disabled.
          </div>
        )}
      </div>
    </div>
  );
}
