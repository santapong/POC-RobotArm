/**
 * REST calls for the /api/programs router.
 */

import { get, post } from "./client";
import type {
  ProgramListEntry,
  ProgramModel,
  PostRequest,
  PostResponse,
  RunStart,
  RunRecord,
} from "./types";

export async function listPrograms(): Promise<ProgramListEntry[]> {
  return get<ProgramListEntry[]>("/programs");
}

export async function getProgram(id: string): Promise<ProgramModel> {
  return get<ProgramModel>(`/programs/${id}`);
}

export async function postProgram(
  id: string,
  req: PostRequest,
): Promise<PostResponse> {
  return post<PostResponse>(`/programs/${id}/post`, req);
}

export async function runProgram(
  id: string,
  req?: RunStart,
): Promise<{ run_id: string }> {
  return post<{ run_id: string }>(`/programs/${id}/run`, req ?? {});
}

export async function getRun(runId: string): Promise<RunRecord> {
  return get<RunRecord>(`/programs/runs/${runId}`);
}

export async function stopRun(runId: string): Promise<RunRecord> {
  return post<RunRecord>(`/programs/runs/${runId}/stop`);
}
