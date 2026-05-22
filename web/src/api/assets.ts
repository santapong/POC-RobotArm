/**
 * REST calls for the /api/assets router.
 */

import { requestMultipart } from "./client";
import type { AssetImportResponse } from "./types";

export async function importAsset(
  file: File,
  attachTo?: string,
  addToStation = true,
): Promise<AssetImportResponse> {
  const form = new FormData();
  form.append("file", file);
  if (attachTo !== undefined) {
    form.append("attach_to", attachTo);
  }
  form.append("add_to_station", String(addToStation));
  return requestMultipart<AssetImportResponse>("/assets/import", form);
}

/**
 * Build the URL for fetching a URDF or auxiliary file for a catalog robot.
 * Proxied through /api/assets/urdf/<robot>/<file:path> on the server.
 */
export function urdfUrl(catalogName: string, file: string): string {
  return `/api/assets/urdf/${catalogName}/${file}`;
}
