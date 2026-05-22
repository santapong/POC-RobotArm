/**
 * IoPanel — two-column layout for the I/O tab (Phase 4).
 *
 * Left column: connection list with status badges, action buttons
 *   (Add/Reconnect/Disconnect/Remove), and an inline signal-map editor for
 *   the selected connection.
 * Right column: `IoValueStream` showing live events and write controls.
 *
 * Notes:
 * - On mount, refreshes the connection list from the server and syncs it into
 *   the store so the UI reflects any server-side state.
 * - The `ioUnavailable` flag is set when the server returns IO_UNAVAILABLE and
 *   disables the "New connection" button for the session.
 */

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ApiError } from "@/api/client";
import {
  listConnections,
  deleteConnection,
  reconnectConnection,
} from "@/api/io";
import { useIoStore } from "@/store/io";
import { ConnectionDialog } from "./ConnectionDialog";
import { SignalMapEditor } from "./SignalMapEditor";
import { IoValueStream } from "./IoValueStream";
import type { ConnectionStatusKind } from "@/api/types";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<ConnectionStatusKind, string> = {
  open: "bg-green-500",
  connecting: "bg-yellow-500",
  closing: "bg-yellow-500",
  error: "bg-red-500",
  disconnected: "bg-gray-400",
};

function StatusBadge({ status }: { status: ConnectionStatusKind }): JSX.Element {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${STATUS_COLORS[status] ?? "bg-gray-400"}`}
      title={status}
    />
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function IoPanel(): JSX.Element {
  const connections = useIoStore((s) => s.connections);
  const selectedConnection = useIoStore((s) => s.selectedConnection);
  const setConnections = useIoStore((s) => s.setConnections);
  const upsertConnection = useIoStore((s) => s.upsertConnection);
  const removeConnectionFromStore = useIoStore((s) => s.removeConnection);
  const selectConnection = useIoStore((s) => s.selectConnection);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [ioUnavailable, setIoUnavailable] = useState(false);
  const [busy, setBusy] = useState<string | null>(null); // tracks which connection name is being acted on

  // Refresh connection list from server on mount.
  useEffect(() => {
    listConnections()
      .then((list) => {
        const next: ReturnType<typeof useIoStore.getState>["connections"] = {};
        for (const conn of list) {
          next[conn.name] = conn;
        }
        setConnections(next);
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError) {
          toast.error(`Failed to load connections: ${err.detail}`);
        }
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleReconnect(name: string): Promise<void> {
    setBusy(name);
    try {
      const updated = await reconnectConnection(name);
      upsertConnection(updated);
      toast.success(`Reconnecting ${name}…`);
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
      } else {
        toast.error(String(err));
      }
    } finally {
      setBusy(null);
    }
  }

  async function handleRemove(name: string): Promise<void> {
    setBusy(name);
    try {
      await deleteConnection(name);
      removeConnectionFromStore(name);
      if (selectedConnection === name) selectConnection(null);
      toast.success(`Connection "${name}" removed.`);
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
      } else {
        toast.error(String(err));
      }
    } finally {
      setBusy(null);
    }
  }

  const connectionList = Object.values(connections);

  return (
    <div className="flex h-full gap-2 overflow-hidden p-2">
      {/* Left column: connection management */}
      <div className="flex w-64 shrink-0 flex-col gap-2 overflow-y-auto">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Connections
        </div>

        {connectionList.length === 0 && (
          <div className="text-xs text-muted-foreground">No connections configured.</div>
        )}

        {connectionList.map((conn) => {
          const isSelected = selectedConnection === conn.name;
          const isBusy = busy === conn.name;
          return (
            <div
              key={conn.name}
              className={`rounded border p-2 text-xs cursor-pointer space-y-1 ${
                isSelected ? "border-primary bg-muted" : "hover:bg-muted/50"
              }`}
              onClick={() => selectConnection(isSelected ? null : conn.name)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-medium">
                  <StatusBadge status={conn.status} />
                  <span className="truncate max-w-[120px]">{conn.name}</span>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-5 px-1 text-xs text-destructive hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleRemove(conn.name);
                  }}
                  disabled={isBusy}
                >
                  X
                </Button>
              </div>

              <div className="text-muted-foreground">
                {conn.config.protocol} — {conn.status}
              </div>

              {conn.last_error !== null && (
                <div className="text-destructive truncate" title={conn.last_error}>
                  {conn.last_error}
                </div>
              )}

              {(conn.status === "error" || conn.status === "disconnected") && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-5 w-full text-xs"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleReconnect(conn.name);
                  }}
                  disabled={isBusy}
                >
                  Reconnect
                </Button>
              )}
            </div>
          );
        })}

        <Button
          size="sm"
          variant="outline"
          className="text-xs"
          onClick={() => setDialogOpen(true)}
          disabled={ioUnavailable}
        >
          {ioUnavailable ? "I/O unavailable" : "+ New connection"}
        </Button>

        <Separator />

        {/* Signal map editor for selected connection */}
        {selectedConnection !== null && (
          <SignalMapEditor connectionName={selectedConnection} />
        )}
      </div>

      {/* Right column: live value stream */}
      <div className="min-w-0 flex-1 overflow-hidden">
        <IoValueStream connectionName={selectedConnection} />
      </div>

      <ConnectionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onIoUnavailable={() => setIoUnavailable(true)}
      />
    </div>
  );
}
