/**
 * TypeScript interfaces mirroring every Pydantic response model from the server.
 *
 * Field names are snake_case to match the wire format exactly, so JSON
 * round-trips require no transformation.
 */

// ---------------------------------------------------------------------------
// Station models
// ---------------------------------------------------------------------------

export interface FrameModel {
  name: string;
  xyz_m: [number, number, number];
  quat_wxyz: [number, number, number, number];
  parent: string | null;
}

export interface RobotEntryModel {
  name: string;
  robot_catalog_name: string;
  base_frame: string;
}

export interface ToolEntryModel {
  name: string;
  parent_frame: string;
  mesh_path: string | null;
  tcp_xyz_m: [number, number, number];
  tcp_quat_wxyz: [number, number, number, number];
}

export interface WorkpieceEntryModel {
  name: string;
  parent_frame: string;
  mesh_path: string | null;
}

export interface FixtureEntryModel {
  name: string;
  parent_frame: string;
  mesh_path: string | null;
}

export interface IOSignalModel {
  name: string;
  kind: "DI" | "DO" | "AI" | "AO";
  default_value: number | boolean;
}

export interface StationModel {
  name: string;
  frames: FrameModel[];
  robots: RobotEntryModel[];
  tools: ToolEntryModel[];
  workpieces: WorkpieceEntryModel[];
  fixtures: FixtureEntryModel[];
  io_signals: IOSignalModel[];
}

// ---------------------------------------------------------------------------
// Motion models
// ---------------------------------------------------------------------------

export interface ToolDataModel {
  name: string;
  mass_kg: number;
  tcp_xyz_m: [number, number, number];
  tcp_quat_wxyz: [number, number, number, number];
}

export interface WObjDataModel {
  name: string;
  base_xyz_m: [number, number, number];
  base_quat_wxyz: [number, number, number, number];
}

export interface SpeedDataModel {
  tcp_mm_s: number;
}

export interface ZoneDataModel {
  kind: string;
  radius_mm: number;
}

export interface JointTargetModel {
  kind: "joint";
  values_rad: number[];
}

export interface PoseTargetModel {
  kind: "pose";
  xyz_m: [number, number, number];
  quat_wxyz: [number, number, number, number];
}

export interface MoveModel {
  kind: "MOVE_J" | "MOVE_L" | "MOVE_C" | "MOVE_ABS_J";
  target: PoseTargetModel | JointTargetModel;
  speed: SpeedDataModel;
  zone: ZoneDataModel;
  tool: ToolDataModel;
  wobj: WObjDataModel;
  circ_via: PoseTargetModel | null;
}

export interface ProcedureModel {
  name: string;
  params: string[];
  body: MoveModel[];
}

export interface ProgramModel {
  name: string;
  modules_metadata: Record<string, string>;
  tools: ToolDataModel[];
  wobjs: WObjDataModel[];
  procedures: ProcedureModel[];
}

// ---------------------------------------------------------------------------
// Catalog models
// ---------------------------------------------------------------------------

export interface RobotCatalogEntry {
  name: string;
  dof: number;
  vendor: string;
  urdf_url: string;
  ee_link_name: string | null;
  home_q: number[];
  description: string;
  qd_max_rad_s: number[] | null;
  qdd_max_rad_s2: number[] | null;
}

// ---------------------------------------------------------------------------
// Runtime models
// ---------------------------------------------------------------------------

export interface RunStateFrame {
  run_id: string;
  index: number;
  total: number;
  active: boolean;
}

export interface TelemetryFrame {
  robot_id: string;
  joints_rad: number[];
  tcp_xyz_m: [number, number, number];
  tcp_quat_wxyz: [number, number, number, number];
  run_state: RunStateFrame | null;
  monotonic_s: number;
}

export interface RobotStateResponse {
  catalog_name: string;
  dof: number;
  joints_rad: number[];
  tcp_xyz_m: [number, number, number];
  tcp_quat_wxyz: [number, number, number, number];
  moving: boolean;
  error: string | null;
}

export interface JogRequest {
  joint_index?: number;
  value_rad?: number;
  values_rad?: number[];
}

export interface PostRequest {
  vendor: "rapid" | "krl" | "urscript";
}

export interface PostResponse {
  vendor: string;
  source: string;
  file_extension: string;
}

export interface RunStart {
  procedure_name?: string;
  dt_s?: number;
}

export interface RunRecord {
  run_id: string;
  program_id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: number;
  finished_at: number | null;
  violation_count: number;
  error: string | null;
}

export interface AssetImportResponse {
  asset_id: string;
  kind: "mesh" | "dxf";
  filename: string;
  summary: string;
  station_entity: FixtureEntryModel | null;
}

// ---------------------------------------------------------------------------
// Error models
// ---------------------------------------------------------------------------

export interface ErrorResponse {
  detail: string;
  code: string;
  hint: string | null;
  violations: Record<string, unknown>[] | null;
}

// ---------------------------------------------------------------------------
// Event payloads (from /ws/events)
// ---------------------------------------------------------------------------

export type WsEventType =
  | "robot_spawned"
  | "robot_removed"
  | "program_emitted"
  | "import_completed"
  | "run_started"
  | "run_completed"
  | "run_failed"
  | "error";

export interface WsEvent {
  type: WsEventType;
  payload: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Spawn request
// ---------------------------------------------------------------------------

export interface SpawnRobotRequest {
  catalog_name: string;
  base_xyz_m?: [number, number, number];
  base_quat_wxyz?: [number, number, number, number];
}

export interface SpawnRobotResponse {
  id: string;
  station: StationModel;
}

// ---------------------------------------------------------------------------
// Program list entry
// ---------------------------------------------------------------------------

export interface ProgramListEntry {
  id: string;
  name: string;
}

// ---------------------------------------------------------------------------
// Save station response
// ---------------------------------------------------------------------------

export interface SaveStationResponse {
  json: Record<string, unknown>;
}
