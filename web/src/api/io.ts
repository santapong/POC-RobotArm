/**
 * REST client for the /api/io/* endpoints.
 *
 * Mirrors the server router from §E of the Phase 4 master plan.
 * All paths are relative to the shared API_BASE ("/api").
 */

import { get, post, del, request } from "./client";
import type {
  IoConnectionStatusModel,
  IoConnectionCreateRequest,
  SignalSpecModel,
  IoValueSnapshotModel,
  WriteSignalRequest,
  WriteSignalResponse,
} from "./types";

export type { IoConnectionCreateRequest };

// ---------------------------------------------------------------------------
// Connections
// ---------------------------------------------------------------------------

/** Create a new I/O connection. */
export function createConnection(
  req: IoConnectionCreateRequest,
): Promise<IoConnectionStatusModel> {
  return post<IoConnectionStatusModel>("/io/connections", req);
}

/** List all known connections with their current status. */
export function listConnections(): Promise<IoConnectionStatusModel[]> {
  return get<IoConnectionStatusModel[]>("/io/connections");
}

/** Fetch a single connection by name. */
export function getConnection(name: string): Promise<IoConnectionStatusModel> {
  return get<IoConnectionStatusModel>(
    `/io/connections/${encodeURIComponent(name)}`,
  );
}

/** Remove a connection and disconnect its adapter. */
export function deleteConnection(name: string): Promise<{ ok: boolean }> {
  return del<{ ok: boolean }>(`/io/connections/${encodeURIComponent(name)}`);
}

/** Reconnect a connection that is in error or closed state. */
export function reconnectConnection(
  name: string,
): Promise<IoConnectionStatusModel> {
  return post<IoConnectionStatusModel>(
    `/io/connections/${encodeURIComponent(name)}/reconnect`,
  );
}

/** Replace the signal map for a connection. */
export function updateSignals(
  name: string,
  signals: SignalSpecModel[],
): Promise<IoConnectionStatusModel> {
  return request<IoConnectionStatusModel>(
    "PUT",
    `/io/connections/${encodeURIComponent(name)}/signals`,
    signals,
  );
}

// ---------------------------------------------------------------------------
// Values
// ---------------------------------------------------------------------------

/** Get last-known values for every signal across all connections. */
export function getAllValues(): Promise<IoValueSnapshotModel[]> {
  return get<IoValueSnapshotModel[]>("/io/values");
}

/** Get last-known values for a single connection. */
export function getConnectionValues(
  name: string,
): Promise<IoValueSnapshotModel[]> {
  return get<IoValueSnapshotModel[]>(
    `/io/connections/${encodeURIComponent(name)}/values`,
  );
}

// ---------------------------------------------------------------------------
// Read / Write
// ---------------------------------------------------------------------------

/** Trigger an on-demand read of a single signal. */
export function readSignal(
  connection: string,
  signal: string,
): Promise<IoValueSnapshotModel> {
  return post<IoValueSnapshotModel>(
    `/io/connections/${encodeURIComponent(connection)}/signals/${encodeURIComponent(signal)}/read`,
  );
}

/** Write a value to a single signal. */
export function writeSignal(
  connection: string,
  signal: string,
  req: WriteSignalRequest,
): Promise<WriteSignalResponse> {
  return post<WriteSignalResponse>(
    `/io/connections/${encodeURIComponent(connection)}/signals/${encodeURIComponent(signal)}/write`,
    req,
  );
}
