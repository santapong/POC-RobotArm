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
  saved_path: string;
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

// ---------------------------------------------------------------------------
// Vision models (Phase 2)
// ---------------------------------------------------------------------------

export interface CameraSpec {
  kind: "real" | "fake";
  source: number | string;
  name: string;
  width?: number;
  height?: number;
  fake_image_paths?: string[];
  fps?: number;
}

export interface CameraStatus {
  name: string;
  kind: "real" | "fake";
  width: number;
  height: number;
  has_intrinsics: boolean;
  has_extrinsics: boolean;
  live_detector: string | null;
}

export interface CameraIntrinsicsModel {
  fx: number;
  fy: number;
  cx: number;
  cy: number;
  width: number;
  height: number;
  dist_coeffs: number[];
}

export interface CameraExtrinsicsModel {
  R_cam_in_world: [[number, number, number], [number, number, number], [number, number, number]];
  t_cam_in_world: [number, number, number];
  reference_frame: string;
  mount: "eye_to_hand" | "eye_in_hand";
}

export interface DetectorSpec {
  kind: "yolo" | "color";
  name: string;
  config?: Record<string, unknown>;
}

export interface DetectorStatus {
  name: string;
  kind: "yolo" | "color";
  config: Record<string, unknown>;
  live_cameras: string[];
}

export interface DetectionModel {
  class_name: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
  mask: null;
  pose_in_camera: GraspPoseModel | null;
  pose_in_world: GraspPoseModel | null;
}

export interface GraspPoseModel {
  xyz_m: [number, number, number];
  quat_wxyz: [number, number, number, number];
  frame: string;
  approach_vector: [number, number, number];
}

export interface PosePairModel {
  R_gripper2base: [[number, number, number], [number, number, number], [number, number, number]];
  t_gripper2base: [number, number, number];
  R_target2cam: [[number, number, number], [number, number, number], [number, number, number]];
  t_target2cam: [number, number, number];
}

export interface HandEyeRequest {
  pose_pairs: PosePairModel[];
  method?: "tsai" | "park" | "horaud" | "andreff" | "daniilidis";
  mount?: "eye_to_hand" | "eye_in_hand";
  reference_frame?: string;
}

export interface RunDetectionRequest {
  camera: string;
  return_grasp?: boolean;
  plane_z_m?: number;
}

export interface RunDetectionResponse {
  camera: string;
  detector: string;
  detections: DetectionModel[];
  grasps: GraspPoseModel[];
  monotonic_s: number;
}

export interface LiveDetectionFrame {
  camera: string;
  detector: string;
  detections: DetectionModel[];
  grasps: GraspPoseModel[];
  monotonic_s: number;
}

export interface CharucoPoseResponse {
  R_target2cam: [[number, number, number], [number, number, number], [number, number, number]];
  t_target2cam: [number, number, number];
}

export interface GraspPreviewRequest {
  robot_id: string;
  grasp: GraspPoseModel;
  preview_mode?: "jog" | "ik_only";
}

export interface GraspPreviewResponse {
  joints_rad: number[];
  reachable: boolean;
  ik_residual_m: number;
  applied: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Planning models (Phase 3)
// ---------------------------------------------------------------------------

export type PlannerKindModel = "rrt" | "rrt_star" | "prm";
export type PlanStageModel =
  | "queued"
  | "ik"
  | "sampling"
  | "optimizing"
  | "parameterising"
  | "completed"
  | "failed"
  | "cancelled";
export type PlanStatusModel = "running" | "completed" | "failed" | "cancelled";

export interface PlannerConfigModel {
  kind: PlannerKindModel;
  timeout_s: number;
  smoothing_iterations: number;
  range_rad: number;
  clearance_m: number;
  qdd_max_rad_s2_default: number | null;
}

export interface OptimizerConfigModel {
  enabled: boolean;
  max_iterations: number;
  min_distance_m: number;
  spline_degree: 3 | 5;
}

export interface ParameteriserConfigModel {
  qd_scale: number;
  qdd_scale: number;
  grid_points: number;
}

export interface PlanRequestModel {
  robot_id: string;
  q_start: number[];
  goal_q: number[] | null;
  goal_pose_xyz_m: [number, number, number] | null;
  goal_pose_quat_wxyz: [number, number, number, number] | null;
  obstacles: string[];
  planner: PlannerConfigModel;
  optimizer: OptimizerConfigModel;
  parameteriser: ParameteriserConfigModel;
}

export interface TrajectorySampleModel {
  t_s: number;
  q_rad: number[];
  qd_rad_s: number[];
  qdd_rad_s2: number[];
}

export interface TimedTrajectoryModel {
  robot_id: string;
  dt_s: number;
  samples: TrajectorySampleModel[];
  duration_s: number;
}

export interface PlanRunRecord {
  plan_id: string;
  status: PlanStatusModel;
  stage: PlanStageModel;
  request: PlanRequestModel;
  created_at: number;
  finished_at: number | null;
  elapsed_s: number | null;
  sampler_path_length: number;
  optimizer_iterations: number;
  parameteriser_grid_points: number;
  cache_hit: boolean;
  error_code: string | null;
  error_message: string | null;
  singularity_hint: number[];
  trajectory: TimedTrajectoryModel | null;
}

export interface PlanCreateResponse {
  plan_id: string;
  status: PlanStatusModel;
}

export interface PlanExecuteRequest {
  dt_s: number;
}

export interface PlanExecuteResponse {
  run_id: string;
}

export interface PlanProgressFrame {
  plan_id: string;
  stage: PlanStageModel;
  percent: number;
  eta_s: number | null;
  monotonic_s: number;
}

// ---------------------------------------------------------------------------
// I/O models (Phase 4)
// ---------------------------------------------------------------------------

export type SignalKindModel = "digital_in" | "digital_out" | "analog_in" | "analog_out";

export type ConnectionProtocolModel = "modbus_tcp" | "modbus_rtu" | "opcua" | "mqtt";

export type ConnectionStatusKind =
  | "disconnected"
  | "connecting"
  | "open"
  | "error"
  | "closing";

export interface ModbusTcpConfigModel {
  protocol: "modbus_tcp";
  host: string;
  port: number;
  unit_id: number;
  timeout_s: number;
}

export interface ModbusRtuConfigModel {
  protocol: "modbus_rtu";
  device: string;
  baudrate: number;
  parity: "N" | "E" | "O";
  stopbits: 1 | 2;
  bytesize: 7 | 8;
  unit_id: number;
  timeout_s: number;
}

export interface OpcUaConfigModel {
  protocol: "opcua";
  url: string;
  namespace: number;
  username: string | null;
  password: string | null;
}

export interface MqttConfigModel {
  protocol: "mqtt";
  host: string;
  port: number;
  client_id: string;
  username: string | null;
  password: string | null;
  keepalive_s: number;
  qos: 0 | 1 | 2;
}

export type ConnectionConfigModel =
  | ModbusTcpConfigModel
  | ModbusRtuConfigModel
  | OpcUaConfigModel
  | MqttConfigModel;

export interface SignalSpecModel {
  name: string;
  kind: SignalKindModel;
  address: string;
  scale: number;
  offset: number;
  poll_interval_s: number | null;
}

export interface IoConnectionStatusModel {
  name: string;
  config: ConnectionConfigModel;
  status: ConnectionStatusKind;
  last_error: string | null;
  connected_at: number | null;
  signals: SignalSpecModel[];
}

export type IoValueModel = boolean | number;

export interface IoValueSnapshotModel {
  connection: string;
  signal: string;
  kind: SignalKindModel;
  value: IoValueModel;
  monotonic_s: number;
}

export type IoEventTypeModel =
  | "connection_changed"
  | "value_changed"
  | "write_ack"
  | "error";

export interface IoEventModel {
  type: IoEventTypeModel;
  connection: string;
  signal: string | null;
  value: IoValueModel | null;
  status: ConnectionStatusKind | null;
  error_code: string | null;
  error_message: string | null;
  monotonic_s: number;
}

export interface WriteSignalRequest {
  value: IoValueModel;
}

export interface IoConnectionCreateRequest {
  name: string;
  config: ConnectionConfigModel;
  signals: SignalSpecModel[];
}

export interface WriteSignalResponse {
  connection: string;
  signal: string;
  value: IoValueModel;
  monotonic_s: number;
}
