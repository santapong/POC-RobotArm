/**
 * REST calls for the /api/robots router.
 */

import { get, post } from "./client";
import type { RobotCatalogEntry, JogRequest, RobotStateResponse } from "./types";

export async function getCatalog(): Promise<RobotCatalogEntry[]> {
  return get<RobotCatalogEntry[]>("/robots/catalog");
}

export async function jog(
  robotId: string,
  req: JogRequest,
): Promise<RobotStateResponse> {
  return post<RobotStateResponse>(`/station/robots/${robotId}/jog`, req);
}

export async function getRobotState(
  robotId: string,
): Promise<RobotStateResponse> {
  return get<RobotStateResponse>(`/station/robots/${robotId}/state`);
}
