/**
 * Thin fetch wrapper for the RobotArm REST API.
 *
 * All non-2xx responses are parsed as `ErrorResponse` and thrown as
 * `ApiError`. Callers receive typed errors with `.code`, `.detail`,
 * `.hint`, and `.violations`.
 */

import type { ErrorResponse } from "./types";

// import.meta.env is typed by vite/client; cast to unknown first to satisfy
// strict mode when vite-env.d.ts is absent from the Phase 0 scaffold.
const API_BASE =
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ((import.meta as unknown as { env: Record<string, string | undefined> }).env
    .VITE_API_BASE) ?? "/api";

/** Typed error thrown for every non-2xx response from the server. */
export class ApiError extends Error {
  readonly code: string;
  readonly detail: string;
  readonly hint: string | null;
  readonly violations: Record<string, unknown>[] | null;
  readonly status: number;

  constructor(status: number, body: ErrorResponse) {
    super(body.detail);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.detail = body.detail;
    this.hint = body.hint ?? null;
    this.violations = body.violations ?? null;
  }
}

async function parseError(resp: Response): Promise<ApiError> {
  let body: ErrorResponse;
  try {
    body = (await resp.json()) as ErrorResponse;
  } catch {
    body = {
      detail: `HTTP ${resp.status} ${resp.statusText}`,
      code: "UNKNOWN_ERROR",
      hint: null,
      violations: null,
    };
  }
  return new ApiError(resp.status, body);
}

/** Perform a JSON request (GET/DELETE with no body, or POST/PATCH with body). */
export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const init: RequestInit = {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };
  const resp = await fetch(url, init);
  if (!resp.ok) {
    throw await parseError(resp);
  }
  // 204 No Content has no body
  if (resp.status === 204) {
    return undefined as unknown as T;
  }
  return (await resp.json()) as T;
}

/** POST a `FormData` (multipart) request, returning parsed JSON. */
export async function requestMultipart<T>(
  path: string,
  form: FormData,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const resp = await fetch(url, { method: "POST", body: form });
  if (!resp.ok) {
    throw await parseError(resp);
  }
  return (await resp.json()) as T;
}

export const get = <T>(path: string) => request<T>("GET", path);
export const post = <T>(path: string, body?: unknown) =>
  request<T>("POST", path, body);
export const del = <T>(path: string) => request<T>("DELETE", path);
