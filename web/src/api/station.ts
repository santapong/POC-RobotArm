/**
 * REST calls for the /api/station router.
 */

import { get, post, del, requestMultipart } from "./client";
import type {
  StationModel,
  SaveStationResponse,
  SpawnRobotRequest,
  SpawnRobotResponse,
} from "./types";

export async function getStation(): Promise<StationModel> {
  return get<StationModel>("/station");
}

export async function newStation(): Promise<StationModel> {
  return post<StationModel>("/station/new");
}

export async function loadStation(file: File): Promise<StationModel> {
  const form = new FormData();
  form.append("file", file);
  return requestMultipart<StationModel>("/station/load", form);
}

export async function saveStation(): Promise<SaveStationResponse> {
  return post<SaveStationResponse>("/station/save");
}

export async function spawnRobot(
  req: SpawnRobotRequest,
): Promise<SpawnRobotResponse> {
  return post<SpawnRobotResponse>("/station/robots", req);
}

export async function deleteRobot(id: string): Promise<StationModel> {
  return del<StationModel>(`/station/robots/${id}`);
}
