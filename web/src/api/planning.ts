/**
 * REST client functions for the /api/planning/* endpoints.
 *
 * All functions mirror the FastAPI planning router exactly.
 * JSON calls use `get` and `post` from the shared client.
 */

import { get, post } from "./client";
import type {
  PlanCreateResponse,
  PlanExecuteRequest,
  PlanExecuteResponse,
  PlanRequestModel,
  PlanRunRecord,
  TimedTrajectoryModel,
} from "./types";

// ---------------------------------------------------------------------------
// Plan CRUD
// ---------------------------------------------------------------------------

/**
 * Submit a new planning request. Returns immediately with a plan_id and
 * status="running". Poll or subscribe via WS for progress.
 */
export function createPlan(req: PlanRequestModel): Promise<PlanCreateResponse> {
  return post<PlanCreateResponse>("/planning/plans", req);
}

/** List all plan records in the current session. */
export function listPlans(): Promise<PlanRunRecord[]> {
  return get<PlanRunRecord[]>("/planning/plans");
}

/** Fetch a single plan record by ID. Throws ApiError 404 if unknown. */
export function getPlan(planId: string): Promise<PlanRunRecord> {
  return get<PlanRunRecord>(`/planning/plans/${encodeURIComponent(planId)}`);
}

/** Request cancellation of a running plan. Returns the updated record. */
export function cancelPlan(planId: string): Promise<PlanRunRecord> {
  return post<PlanRunRecord>(`/planning/plans/${encodeURIComponent(planId)}/cancel`);
}

/**
 * Fetch the computed trajectory for a completed plan.
 * Throws ApiError 409 PLAN_NOT_COMPLETED if the plan is still running.
 */
export function getPlanTrajectory(planId: string): Promise<TimedTrajectoryModel> {
  return get<TimedTrajectoryModel>(
    `/planning/plans/${encodeURIComponent(planId)}/trajectory`,
  );
}

/**
 * Execute a completed plan on the simulator. Returns a run_id that can be
 * tracked via the programs run-state WS channel.
 */
export function executePlan(
  planId: string,
  req: PlanExecuteRequest,
): Promise<PlanExecuteResponse> {
  return post<PlanExecuteResponse>(
    `/planning/plans/${encodeURIComponent(planId)}/execute`,
    req,
  );
}
