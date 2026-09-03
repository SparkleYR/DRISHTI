export const SCHEMA_VERSION = "1.0.0" as const;

export type SchemaVersion = typeof SCHEMA_VERSION;
export type Timestamp = string;
export type OpaqueId = string;

export type ServiceStatus = "OK" | "DEGRADED" | "UNAVAILABLE";
export type ModuleStatus = "READY" | "DEGRADED" | "UNAVAILABLE" | "LOADING";
export type ComputeDevice = "CUDA" | "CPU" | "NONE";

export interface ModuleHealth {
  status: ModuleStatus;
  detail?: string | null;
}

export interface HealthResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  status: ServiceStatus;
  runtime_mode: "LOCAL_ONLY";
  service: {
    name: "drishti-backend";
    version: string;
  };
  compute: {
    selected_device: ComputeDevice;
    device_name?: string | null;
  };
  models: {
    detector: ModuleHealth;
    segmentation: ModuleHealth;
    tracker: ModuleHealth;
    depth: ModuleHealth;
    india_hazards: ModuleHealth;
    ocr: ModuleHealth;
    vlm: ModuleHealth;
  };
  database: ModuleHealth;
  walk_mode_available: boolean;
}

export type ErrorCode =
  | "INVALID_REQUEST"
  | "INVALID_CONTENT_TYPE"
  | "IMAGE_TOO_LARGE"
  | "IMAGE_DECODE_FAILED"
  | "SESSION_NOT_FOUND"
  | "SESSION_ENDED"
  | "FRAME_ID_NOT_MONOTONIC"
  | "FRAME_TOO_OLD"
  | "FRAME_SUPERSEDED"
  | "MODEL_NOT_READY"
  | "DATABASE_UNAVAILABLE"
  | "INVALID_STATUS_TRANSITION"
  | "CONFLICT"
  | "NOT_FOUND"
  | "INTERNAL_ERROR";

export interface ApiErrorResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  error: {
    code: ErrorCode;
    message: string;
    retryable: boolean;
    details?: Record<string, unknown> | null;
  };
}

export interface WalkSettings {
  speech_rate?: number;
  preferred_language?: string;
  haptics_enabled?: boolean;
  risk_sensitivity?: number;
}

export interface StartWalkSessionRequest {
  device_alias?: string;
  settings?: WalkSettings;
}

export interface StartWalkSessionResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  session_id: OpaqueId;
  started_at: Timestamp;
  recommended_capture_fps: number;
  max_image_width: number;
  max_image_bytes: number;
  max_result_age_ms: number;
}

export interface EndWalkSessionResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  session_id: OpaqueId;
  ended_at: Timestamp;
  status: "ENDED";
}

export type CoordinateSpace = "ORIENTED_CAPTURE_NORMALIZED";
export type PreviewResizeMode = "COVER" | "CONTAIN";

export interface NormalizedPoint {
  x: number;
  y: number;
}

export interface NormalizedBoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export type NormalizedPolygon = NormalizedPoint[];

export type Direction = "LEFT" | "CENTRE" | "RIGHT" | "UNKNOWN";
export type ProximityBand = "FAR" | "MEDIUM" | "NEAR" | "IMMEDIATE" | "UNKNOWN";
export type ApproachState = "APPROACHING" | "RECEDING" | "STATIONARY" | "UNKNOWN";
export type RiskLevel = "CLEAR" | "WATCH" | "WARN" | "HIGH" | "CRITICAL";
export type DisplayColor = "GREEN" | "YELLOW" | "RED" | "GREY";

export interface MotionVector {
  dx: number;
  dy: number;
}

export interface DetectionResult {
  track_id?: number | null;
  label: string;
  confidence: number;
  bbox: NormalizedBoundingBox;
  anchor: NormalizedPoint;
  direction: Direction;
  proximity: ProximityBand;
  proximity_score?: number | null;
  approach_state: ApproachState;
  approach_rate?: number | null;
  motion_vector?: MotionVector | null;
  path_overlap: number;
  risk_score: number;
  risk_level: RiskLevel;
  display_color: DisplayColor;
}

export type SurfaceKind = "WALKABLE" | "ROAD" | "NON_WALKABLE" | "UNKNOWN";

export interface SurfaceRegion {
  kind: SurfaceKind;
  confidence: number;
  polygon: NormalizedPolygon;
  source_frame_id: number;
}

export interface FrameGeometry {
  coordinate_space: CoordinateSpace;
  source_width: number;
  source_height: number;
  rotation_degrees: 0 | 90 | 180 | 270;
  mirrored: false;
}

export interface CorridorCosts {
  left_cost: number;
  centre_cost: number;
  right_cost: number;
}

export interface OverlayContract {
  coordinate_space: CoordinateSpace;
  preferred_corridor: "LEFT" | "CENTRE" | "RIGHT" | "NONE";
  safe_polygons: NormalizedPolygon[];
  blocked_polygons: NormalizedPolygon[];
  uncertain_polygons: NormalizedPolygon[];
  direction_arrow: "LEFT" | "RIGHT" | "STOP" | "NONE";
  valid_until: Timestamp;
}

export interface GuidanceContract {
  level: RiskLevel;
  action: "CLEAR" | "CAUTION" | "MOVE_LEFT" | "MOVE_RIGHT" | "STOP" | "PAUSE_UNCLEAR";
  speech: string;
  haptic_pattern: "NONE" | "CAUTION_SHORT" | "WARNING_DOUBLE" | "CRITICAL_RAPID" | "UNCLEAR_LONG";
  speak: boolean;
  reason_code: string;
}

export type TargetTrackingState =
  | "IDLE"
  | "LOCATING"
  | "LOCKED_TRACKING"
  | "TARGET_LOST";

export type TargetHapticPattern =
  | "NONE"
  | "TARGET_LEFT_PULSE"
  | "TARGET_CENTRE_PULSE"
  | "TARGET_RIGHT_PULSE";

export interface TargetTrackingTelemetry {
  tracking_state: TargetTrackingState;
  target_name: string | null;
  clock_direction: string | null;
  target_center: NormalizedPoint | null;
  confidence: number | null;
  is_safety_overridden: boolean;
  speech: string;
  speak: boolean;
  haptic_pattern: TargetHapticPattern;
}

export interface TargetTelemetryEvent extends TargetTrackingTelemetry {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  session_id: OpaqueId;
  frame_id: number;
}

export interface StageTimings {
  decode_ms: number;
  detection_ms?: number | null;
  segmentation_ms?: number | null;
  tracking_depth_ms?: number | null;
  spatial_ms?: number | null;
  risk_ms?: number | null;
  total_ms: number;
}

export interface FrameAnalysisResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  session_id: OpaqueId;
  frame_id: number;
  captured_at: Timestamp;
  received_at: Timestamp;
  processed_at: Timestamp;
  frame_age_ms: number;
  geometry: FrameGeometry;
  detections: DetectionResult[];
  surfaces: SurfaceRegion[];
  corridors: CorridorCosts;
  overlay: OverlayContract;
  guidance: GuidanceContract;
  target_tracking: TargetTrackingTelemetry;
  timings: StageTimings;
  degraded_modules: string[];
}

export type HazardSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type HazardStatus =
  | "NEW"
  | "VERIFIED"
  | "ASSIGNED"
  | "IN_PROGRESS"
  | "RESOLVED"
  | "REJECTED";

export interface VersionedMapCoordinate {
  map_id: string;
  map_version: string;
  x: number;
  y: number;
}

export interface GeoCoordinate {
  latitude: number;
  longitude: number;
  accuracy_m?: number | null;
}

export interface HazardRecord {
  id: OpaqueId;
  category: string;
  severity: HazardSeverity;
  status: HazardStatus;
  map_coordinate?: VersionedMapCoordinate | null;
  geo_coordinate?: GeoCoordinate | null;
  first_seen_at: Timestamp;
  last_seen_at: Timestamp;
  confidence: number;
  confirmation_count: number;
  temporary: boolean;
  assigned_to?: string | null;
  version: number;
  has_consented_evidence: boolean;
}

export interface HazardObservation {
  id: OpaqueId;
  hazard_id: OpaqueId;
  session_id?: OpaqueId | null;
  observed_at: Timestamp;
  confidence: number;
  risk_score?: number | null;
  direction: Direction;
}

export interface CreateHazardRequest {
  session_id?: OpaqueId | null;
  category: string;
  severity: HazardSeverity;
  confidence: number;
  risk_score?: number | null;
  direction?: Direction;
  observed_at: Timestamp;
  map_coordinate?: VersionedMapCoordinate | null;
  geo_coordinate?: GeoCoordinate | null;
  temporary: boolean;
  evidence_consent: boolean;
}

export interface HazardResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  hazard: HazardRecord;
  merged_with_existing: boolean;
}

export interface HazardListResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  items: HazardRecord[];
  next_cursor?: string | null;
}

export interface UpdateHazardStatusRequest {
  expected_version: number;
  expected_status: HazardStatus;
  new_status: HazardStatus;
  operator_alias: string;
  assigned_to?: string | null;
  note?: string | null;
}

export interface HazardStatusHistoryRecord {
  id: OpaqueId;
  hazard_id: OpaqueId;
  from_status: HazardStatus;
  to_status: HazardStatus;
  changed_at: Timestamp;
  operator_alias: string;
  note?: string | null;
}

export interface UpdateHazardStatusResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  hazard: HazardRecord;
  transition: HazardStatusHistoryRecord;
}

export interface MergeHazardRequest {
  duplicate_hazard_id: OpaqueId;
  expected_primary_version: number;
  expected_duplicate_version: number;
  operator_alias: string;
  note?: string | null;
}

export interface MergeHazardResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  primary_hazard: HazardRecord;
  merged_hazard_id: OpaqueId;
}

export interface DashboardSummaryResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  counts: {
    new: number;
    verified: number;
    assigned: number;
    in_progress: number;
    resolved: number;
    rejected: number;
  };
  active_verified_hazards: number;
  awaiting_review: number;
  recently_resolved: HazardRecord[];
  median_resolution_minutes?: number | null;
}

export type AccessibilityBand =
  | "HIGH_ACCESS"
  | "MODERATE_ACCESS"
  | "LOW_ACCESS"
  | "SEVERELY_OBSTRUCTED";

export interface RouteSegmentRecord {
  id: OpaqueId;
  segment_key: string;
  name: string;
  sequence: number;
  start: VersionedMapCoordinate;
  end: VersionedMapCoordinate;
  corridor_radius: number;
}

export interface AccessibilityFactor {
  hazard_id: OpaqueId;
  category: string;
  severity: HazardSeverity;
  status: HazardStatus;
  confirmation_count: number;
  confidence: number;
  temporary: boolean;
  age_seconds: number;
  distance_to_segment: number;
  severity_points: number;
  status_factor: number;
  recurrence_factor: number;
  confidence_factor: number;
  freshness_factor: number;
  spatial_factor: number;
  penalty_points: number;
  explanation: string;
}

export interface SegmentAccessibilityScore {
  segment: RouteSegmentRecord;
  score: number;
  band: AccessibilityBand;
  factors: AccessibilityFactor[];
}

export interface RouteAccessibilityScore {
  route_id: OpaqueId;
  route_key: string;
  route_name: string;
  description: string;
  map_id: string;
  map_version: string;
  specification_version: string;
  score: number;
  band: AccessibilityBand;
  active_hazard_count: number;
  recurring_hazard_count: number;
  segments: SegmentAccessibilityScore[];
}

export interface DashboardAccessibilityResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  advisory_only: true;
  disclaimer: string;
  expired_temporary_count: number;
  routes: RouteAccessibilityScore[];
}

export type ExploreMode = "READ_TEXT";
export type OcrConfidenceQualification = "HIGH" | "LOW" | "NONE";

export interface ExploreTimings {
  decode_ms: number;
  ocr_ms: number;
  total_ms: number;
}

export interface ReadTextResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  mode: "READ_TEXT";
  language: "eng";
  text: string;
  route_numbers: string[];
  confidence: number;
  confidence_qualification: OcrConfidenceQualification;
  message: string;
  no_text_found: boolean;
  timings: ExploreTimings;
}

export interface VLMTimings {
  decode_ms: number;
  load_ms: number;
  inference_ms: number;
  unload_ms: number;
  total_ms: number;
}

export interface VLMQueryResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  model: "moondream2";
  text: string;
  timings: VLMTimings;
}

export interface VLMTargetBox {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface VLMLocatedTarget {
  label: string;
  confidence: number | null;
  box: VLMTargetBox;
  point: NormalizedPoint;
}

export interface VLMLocateResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  model: "moondream2";
  text: string;
  target: VLMLocatedTarget;
  clock_direction: string;
  tracking_allowed: boolean;
  source_frame_id: number | null;
  timings: VLMTimings;
}
