# DRISHTI API Contracts

## 1. Contract authority

This document defines the intended local API contract before implementation. FastAPI/Pydantic models will be authoritative at runtime, and generated OpenAPI must remain consistent with this document. Mobile and dashboard TypeScript types must use the same field names and enum values.

Base path: `/api/v1`

## 2. General rules

- Runtime transport is HTTP over a trusted private LAN; no endpoint calls an external service.
- JSON field names use `snake_case`.
- All timestamps use RFC 3339 UTC with a trailing `Z`.
- Every response includes `schema_version` and `server_time`.
- IDs are opaque strings. Clients must not derive meaning from them.
- Walking `frame_id` values are non-negative integers, strictly increasing within one session.
- Optional values are represented as `null` or omitted only where the schema marks them optional.
- Errors use the stable envelope defined below.
- Incoming walking frames are processed in memory and are never persisted.
- Unknown enum values must be rejected until a contract version explicitly introduces them.

Initial contract version: `1.0.0`

## 3. Common types

```ts
type SchemaVersion = "1.0.0";
type Timestamp = string; // RFC 3339 UTC, for example 2026-09-03T12:00:00.000Z
type OpaqueId = string;

type ServiceStatus = "OK" | "DEGRADED" | "UNAVAILABLE";
type ModuleStatus = "READY" | "DEGRADED" | "UNAVAILABLE" | "LOADING";
type ComputeDevice = "CUDA" | "CPU" | "NONE";

type Direction = "LEFT" | "CENTRE" | "RIGHT" | "UNKNOWN";
type CorridorChoice = "LEFT" | "CENTRE" | "RIGHT" | "NONE";
type ProximityBand = "FAR" | "MEDIUM" | "NEAR" | "IMMEDIATE" | "UNKNOWN";
type ApproachState = "APPROACHING" | "RECEDING" | "STATIONARY" | "UNKNOWN";
type RiskLevel = "CLEAR" | "WATCH" | "WARN" | "HIGH" | "CRITICAL";
type DisplayColor = "GREEN" | "YELLOW" | "RED" | "GREY";

type GuidanceAction =
  | "CLEAR"
  | "CAUTION"
  | "MOVE_LEFT"
  | "MOVE_RIGHT"
  | "STOP"
  | "PAUSE_UNCLEAR";

type HapticPattern =
  | "NONE"
  | "CAUTION_SHORT"
  | "WARNING_DOUBLE"
  | "CRITICAL_RAPID"
  | "UNCLEAR_LONG";
```

All normalized scalar values are finite numbers in the inclusive range `[0.0, 1.0]`.

```ts
interface NormalizedPoint {
  x: number;
  y: number;
}

interface NormalizedBoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

type NormalizedPolygon = NormalizedPoint[];

interface MotionVector {
  dx: number; // normalized image-width change per second
  dy: number; // normalized image-height change per second
}
```

Bounding-box invariants:

- `0 <= x1 < x2 <= 1`
- `0 <= y1 < y2 <= 1`

Polygon invariants:

- At least three points
- Every coordinate is normalized
- Points are ordered clockwise
- Polygon is not self-intersecting
- Initial maximum is 64 vertices per polygon and 16 polygons per category

## 4. Coordinate-space contract

All returned boxes, points, vectors, and polygons use `ORIENTED_CAPTURE_NORMALIZED` space:

- Origin is the top-left of the orientation-corrected captured image.
- Positive `x` points right; positive `y` points down.
- Coordinates are normalized against the full oriented capture width and height before model letterboxing.
- Backend inference resize and letterboxing must be inverted before returning geometry.
- Rear-camera results are not mirrored.
- The mobile renderer applies exactly one transform from this coordinate space to the visible preview, including preview crop or letterboxing.

```ts
type CoordinateSpace = "ORIENTED_CAPTURE_NORMALIZED";
type PreviewResizeMode = "COVER" | "CONTAIN";

interface FrameGeometry {
  coordinate_space: CoordinateSpace;
  source_width: number;
  source_height: number;
  rotation_degrees: 0 | 90 | 180 | 270;
  mirrored: boolean;
}
```

Phase 1 must verify this contract with known corner and centre markers on the target phone.

## 5. Error envelope

```ts
type ErrorCode =
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
  | "REQUEST_TIMEOUT"
  | "DATABASE_UNAVAILABLE"
  | "INVALID_STATUS_TRANSITION"
  | "CONFLICT"
  | "NOT_FOUND"
  | "INTERNAL_ERROR";

interface ApiErrorResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  error: {
    code: ErrorCode;
    message: string;
    retryable: boolean;
    details?: Record<string, unknown>;
  };
}
```

The message is safe for display but must not expose stack traces, local secrets, raw image data, or precise user movement history.

## 6. Health

### `GET /api/v1/health`

```ts
interface ModuleHealth {
  status: ModuleStatus;
  detail?: string;
}

interface HealthResponse {
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
    device_name?: string;
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
```

Service health and model readiness are independent. In Phase 0 the service may be `OK`, the database `READY`, models `UNAVAILABLE`, and `walk_mode_available` false.

## 7. Walking sessions

### `POST /api/v1/walk/sessions`

```ts
interface WalkSettings {
  speech_rate?: number; // normalized preference, 0.0 to 1.0
  preferred_language?: string; // BCP 47 language tag
  haptics_enabled?: boolean;
  risk_sensitivity?: number; // normalized preference, 0.0 to 1.0
}

interface StartWalkSessionRequest {
  device_alias?: string; // anonymous local alias, not a personal identifier
  settings?: WalkSettings;
}

interface StartWalkSessionResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  session_id: OpaqueId;
  started_at: Timestamp;
  recommended_capture_fps: number;
  max_image_width: number;
  max_image_bytes: number;
  max_result_age_ms: number;
}
```

### `PATCH /api/v1/walk/sessions/{session_id}/end`

```ts
interface EndWalkSessionResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  session_id: OpaqueId;
  ended_at: Timestamp;
  status: "ENDED";
}
```

Ending an already ended session is idempotent and returns its original `ended_at`.

## 8. Frame analysis

### `POST /api/v1/walk/analyze`

Content type: `multipart/form-data`

Required parts:

| Part | Type | Rules |
|---|---|---|
| `frame` | JPEG image | Enforced MIME, byte-size, dimension, and decode limits |
| `session_id` | string | Must identify an active session |
| `frame_id` | integer | Strictly increasing per session |
| `captured_at` | timestamp | RFC 3339 UTC |
| `rotation_degrees` | integer | `0`, `90`, `180`, or `270` |

The non-file parts correspond to this typed metadata object:

```ts
interface FrameAnalysisMetadata {
  session_id: OpaqueId;
  frame_id: number;
  captured_at: Timestamp;
  rotation_degrees: 0 | 90 | 180 | 270;
}
```

```ts
interface DetectionResult {
  track_id?: number;
  label: string;
  confidence: number;
  bbox: NormalizedBoundingBox;
  anchor: NormalizedPoint;
  direction: Direction;
  proximity: ProximityBand;
  proximity_score?: number;
  approach_state: ApproachState;
  approach_rate?: number;
  motion_vector?: MotionVector;
  path_overlap: number;
  risk_score: number;
  risk_level: RiskLevel;
  display_color: DisplayColor;
}

type SurfaceKind = "WALKABLE" | "ROAD" | "NON_WALKABLE" | "UNKNOWN";

interface SurfaceRegion {
  kind: SurfaceKind;
  confidence: number;
  polygon: NormalizedPolygon;
  source_frame_id: number;
}

interface CorridorCosts {
  left_cost: number;
  centre_cost: number;
  right_cost: number;
}

interface OverlayContract {
  coordinate_space: CoordinateSpace;
  preferred_corridor: CorridorChoice;
  safe_polygons: NormalizedPolygon[];
  blocked_polygons: NormalizedPolygon[];
  uncertain_polygons: NormalizedPolygon[];
  direction_arrow: "LEFT" | "RIGHT" | "STOP" | "NONE";
  valid_until: Timestamp;
}

interface GuidanceContract {
  level: RiskLevel;
  action: GuidanceAction;
  speech: string;
  haptic_pattern: HapticPattern;
  speak: boolean;
  reason_code: string;
}

type TargetTrackingState =
  | "IDLE"
  | "LOCATING"
  | "LOCKED_TRACKING"
  | "TARGET_LOST";

type TargetHapticPattern =
  | "NONE"
  | "TARGET_LEFT_PULSE"
  | "TARGET_CENTRE_PULSE"
  | "TARGET_RIGHT_PULSE";

interface TargetTrackingTelemetry {
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

interface StageTimings {
  decode_ms: number;
  detection_ms?: number;
  segmentation_ms?: number;
  tracking_depth_ms?: number;
  spatial_ms?: number;
  risk_ms?: number;
  total_ms: number;
}

interface FrameAnalysisResponse {
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
```

Before their owning phases, fields such as detections and surfaces return empty arrays and timing fields may be absent; field meanings do not change between phases.

The backend retains one replaceable JPEG for the newest successfully decoded
frame of each active Walk session. This bounded process-memory buffer exists
only so an explicit locate request can atomically copy the current snapshot. It
contains no history, is never persisted or logged, and is removed on session
end. A malformed, rejected, or superseded frame never replaces a successfully
decoded snapshot.

`target_tracking` is optional assistive metadata and never replaces
`guidance`. When `guidance.action` is anything other than `CLEAR`, the response
must set `is_safety_overridden=true`, `target_tracking.speak=false`, and
`target_tracking.haptic_pattern="NONE"`. Safety speech/haptics therefore remain
the only immediate mobility instruction.

### `WS /api/v1/walk/sessions/{session_id}/telemetry`

An active session may subscribe to the target telemetry produced by completed
Walk analyses. The WebSocket does not accept frames and never triggers detector,
segmenter, VLM, or tracker work. Each subscriber has a queue capacity of one;
a newer event replaces an unsent older event.

```ts
interface TargetTelemetryEvent extends TargetTrackingTelemetry {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  session_id: OpaqueId;
  frame_id: number;
}
```

Unknown sessions close with application code `4404`, ended sessions with
`4409`, and an active connection closes normally when its Walk session ends.

### Phase 8 indoor hall semantics

Phase 8 and its walk-accuracy amendment do not change the frame-analysis
response shape. The detector canonicalizes model labels `dining table` and
`table` to client-facing `desk`, while backpack and handbag remain `bag`.
Additional auditable indoor labels can appear through the existing free-form
`DetectionResult.label` field.

ADE20K semantic labels are token-normalized before mapping to the existing four
`SurfaceKind` values. Indoor floor, rug/carpet, path, sidewalk, and pavement are
`WALKABLE`; structural, furniture, person, vehicle, stairs, and level-change
classes are `NON_WALKABLE`; genuine road remains `ROAD`; unmatched labels are
`UNKNOWN`.

A wall is semantic surface evidence, not a fabricated bounding-box detection.
`WALL_OR_DEAD_END_AHEAD` returns `STOP` only when the centre visible-floor extent
is below the configured dead-end maximum, neither side has sufficient visible
floor extent, and confident centre-wall pixels corroborate the result. Visible
floor extent is a normalized image-space proportion in `[0,1]`, not distance or
a guarantee of safe clearance. A side wall alone cannot emit this reason.

Confident ADE20K `stairs`, `stairway`, `step`, or `escalator` evidence occupying
the configured centre share returns `STOP` with reason code
`STAIRS_OR_LEVEL_CHANGE_AHEAD`. Reason codes remain free-form strings, so this
adds no enum or response-schema member.

If segmentation is unavailable, `models.india_hazards` is `DEGRADED` and frame
responses include both `segmentation` and `india_hazards` in `degraded_modules`.
The generic detector remains the sole prerequisite for `walk_mode_available`.

### Frame freshness rules

The mobile client must discard a response without applying overlay, speech, or haptics if any condition is true:

1. `session_id` is not the currently active session.
2. The session has been paused or ended.
3. `frame_id <= latest_applied_frame_id`.
4. Current UTC time is later than `overlay.valid_until`.
5. Current time minus `captured_at` exceeds the session's `max_result_age_ms`.

The backend must reject a non-monotonic frame ID. When scheduling is introduced, a queued frame replaced by a newer frame returns `FRAME_SUPERSEDED`. Neither client nor server may reuse an older guidance result after an analysis failure.

## 9. Guidance invariants

Default mappings:

| Action | Speech | Haptic |
|---|---|---|
| `CLEAR` | Empty; normally silent | `NONE` |
| `CAUTION` | `Obstacle nearby.` | `CAUTION_SHORT` |
| `MOVE_LEFT` | `Path blocked. Move slightly left.` | `WARNING_DOUBLE` |
| `MOVE_RIGHT` | `Path blocked. Move slightly right.` | `WARNING_DOUBLE` |
| `STOP` | `Stop. Obstacle directly ahead.` | `CRITICAL_RAPID` |
| `PAUSE_UNCLEAR` | `Path unclear. Please pause.` | `UNCLEAR_LONG` |

Invariants:

- A `LEFT` or `RIGHT` arrow must match the action.
- `STOP` cannot expose a green preferred corridor.
- `PAUSE_UNCLEAR` must include yellow uncertainty and cannot advise movement.
- A critical action may bypass deduplication and cooldown.
- Unchanged non-critical guidance sets `speak` false during cooldown.

## 10. Hazards

```ts
type HazardSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
type HazardStatus =
  | "NEW"
  | "VERIFIED"
  | "ASSIGNED"
  | "IN_PROGRESS"
  | "RESOLVED"
  | "REJECTED";

interface VersionedMapCoordinate {
  map_id: string;
  map_version: string;
  x: number; // normalized 0.0 to 1.0
  y: number; // normalized 0.0 to 1.0
}

interface GeoCoordinate {
  latitude: number;  // -90 to 90
  longitude: number; // -180 to 180
  accuracy_m?: number;
}

interface HazardRecord {
  id: OpaqueId;
  category: string;
  severity: HazardSeverity;
  status: HazardStatus;
  map_coordinate?: VersionedMapCoordinate;
  geo_coordinate?: GeoCoordinate;
  first_seen_at: Timestamp;
  last_seen_at: Timestamp;
  confidence: number;
  confirmation_count: number;
  temporary: boolean;
  assigned_to?: string;
  version: number;
  has_consented_evidence: boolean;
}

interface HazardObservation {
  id: OpaqueId;
  hazard_id: OpaqueId;
  session_id?: OpaqueId;
  observed_at: Timestamp;
  confidence: number;
  risk_score?: number;
  direction: Direction;
}
```

### `POST /api/v1/hazards`

```ts
interface CreateHazardRequest {
  session_id?: OpaqueId;
  category: string;
  severity: HazardSeverity;
  confidence: number;
  risk_score?: number;
  direction?: Direction;
  observed_at: Timestamp;
  map_coordinate?: VersionedMapCoordinate;
  geo_coordinate?: GeoCoordinate;
  temporary: boolean;
  evidence_consent: boolean;
}

interface HazardResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  hazard: HazardRecord;
  merged_with_existing: boolean;
}
```

Without evidence, the endpoint accepts `application/json`. If Phase 6 enables evidence, it accepts `multipart/form-data` with a `payload` part containing `CreateHazardRequest` JSON and an `evidence` image part. Evidence bytes are rejected unless `evidence_consent` is true; consent without an evidence part is valid and stores no image. The request contains no user identity.

### `GET /api/v1/hazards`

Supported query parameters:

- `status`: repeated explicit `HazardStatus` values
- `active=true`: alias for `NEW`, `VERIFIED`, `ASSIGNED`, and `IN_PROGRESS`
- `category`
- `limit`
- `cursor`

```ts
interface HazardListResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  items: HazardRecord[];
  next_cursor?: string;
}
```

### `GET /api/v1/hazards/nearby`

The request must provide either `map_id`, `map_version`, `map_x`, `map_y`, and `radius`, or latitude, longitude, and `radius_m`. Map radius is measured in normalized map units. Coordinate systems must not be mixed in one distance calculation.

The response uses `HazardListResponse` and excludes `RESOLVED` and `REJECTED` records by default.

## 11. Dashboard operations

### `PATCH /api/v1/hazards/{hazard_id}/status`

```ts
interface UpdateHazardStatusRequest {
  expected_version: number;
  expected_status: HazardStatus;
  new_status: HazardStatus;
  operator_alias: string;
  assigned_to?: string;
  note?: string;
}

interface HazardStatusHistoryRecord {
  id: OpaqueId;
  hazard_id: OpaqueId;
  from_status: HazardStatus;
  to_status: HazardStatus;
  changed_at: Timestamp;
  operator_alias: string;
  note?: string;
}

interface UpdateHazardStatusResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  hazard: HazardRecord;
  transition: HazardStatusHistoryRecord;
}
```

Allowed transitions:

```text
NEW -> VERIFIED | REJECTED
VERIFIED -> ASSIGNED | RESOLVED | REJECTED
ASSIGNED -> IN_PROGRESS | RESOLVED
IN_PROGRESS -> RESOLVED
```

All other transitions return `INVALID_STATUS_TRANSITION`. A mismatched `expected_version` or `expected_status` returns `CONFLICT`.

### `POST /api/v1/hazards/{hazard_id}/merge`

```ts
interface MergeHazardRequest {
  duplicate_hazard_id: OpaqueId;
  expected_primary_version: number;
  expected_duplicate_version: number;
  operator_alias: string;
  note?: string;
}

interface MergeHazardResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  primary_hazard: HazardRecord;
  merged_hazard_id: OpaqueId;
}
```

Merge must preserve observations and status-history provenance in one transaction.

### `GET /api/v1/dashboard/summary`

```ts
interface DashboardSummaryResponse {
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
  median_resolution_minutes?: number;
}
```

The Phase 6 dashboard polls hazard and summary endpoints every 1–3 seconds. WebSocket or server-sent-event transport is out of scope until polling is stable.

### `GET /api/v1/dashboard/accessibility`

Phase 10 adds an advisory, explainable score for versioned local routes. This
endpoint first expires temporary hazards that have exceeded their configured
category-specific reconfirmation window. It never changes or replaces the live
Walk Loop guidance contract.

```ts
type AccessibilityBand =
  | "HIGH_ACCESS"
  | "MODERATE_ACCESS"
  | "LOW_ACCESS"
  | "SEVERELY_OBSTRUCTED";

interface RouteSegmentRecord {
  id: OpaqueId;
  segment_key: string;
  name: string;
  sequence: number;
  start: VersionedMapCoordinate;
  end: VersionedMapCoordinate;
  corridor_radius: number;
}

interface AccessibilityFactor {
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

interface SegmentAccessibilityScore {
  segment: RouteSegmentRecord;
  score: number;
  band: AccessibilityBand;
  factors: AccessibilityFactor[];
}

interface RouteAccessibilityScore {
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

interface DashboardAccessibilityResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  advisory_only: true;
  disclaimer: string;
  expired_temporary_count: number;
  routes: RouteAccessibilityScore[];
}
```

`expired_temporary_count` is the cumulative number of locally recorded
`system-expiry` resolutions in the current database, not merely the number
expired by one polling request.

Score `100` means that no active report currently reduces the route's advisory
score; it is not a guarantee that the route is obstacle-free. Each penalty is
the deterministic product of severity points, verification-status factor,
recurrence factor, confidence factor, temporary freshness, and distance-based
segment influence, capped at 60 points per hazard per segment. `RESOLVED`,
`REJECTED`, expired, and merged records are excluded. The current hall route is
the normalized `hackathon-demo-hall` map version `1`, specification version
`1.0.0`; coordinates are configured reference data, not GPS or camera-derived
localization.

## 12. Persistence ownership and failure behavior

- Only FastAPI reads or writes SQLite.
- Walking-session processing remains operational if SQLite is unavailable; session state required for current inference may remain in memory.
- Hazard and dashboard endpoints return `DATABASE_UNAVAILABLE` when persistence is unavailable.
- The health response reports the database degradation.
- A failed frame analysis never returns unrelated previous guidance.
- An unavailable optional module is listed in `degraded_modules` and cannot crash the core detector.

## 13. Explore Mode and OCR

Explore processing is user-triggered and isolated from the continuous Walk Loop.
It runs locally on a separately bounded CPU worker and never stores the submitted
image. Phase 7 implements only `READ_TEXT`; `DESCRIBE_FOCUSED` and `QUESTION`
remain outside the active contract.

### `POST /api/v1/explore`

Content type: `multipart/form-data`

| Part | Type | Rules |
|---|---|---|
| `frame` | JPEG image | Enforced MIME, byte-size, dimension, and decode limits; processed in memory only |
| `mode` | string | Must be `READ_TEXT` in Phase 7 |
| `preferred_language` | string | Optional English BCP 47 tag; defaults to `en` |

```ts
type ExploreMode = "READ_TEXT";
type OcrConfidenceQualification = "HIGH" | "LOW" | "NONE";

interface ExploreTimings {
  decode_ms: number;
  ocr_ms: number;
  total_ms: number;
}

interface ReadTextResponse {
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
```

Invariants:

- `confidence` is finite and normalized to `[0.0, 1.0]`.
- `NONE` requires `no_text_found=true`, empty `text`, empty route numbers,
  confidence `0.0`, and message `No text found.`
- `LOW` requires `no_text_found=false` and a message prefixed with
  `Possible text:` so uncertain OCR is never presented as certain.
- `HIGH` requires `no_text_found=false` and returns the extracted text as the
  message.
- Unsupported languages return `INVALID_REQUEST`.
- An unavailable OCR runtime returns `MODEL_NOT_READY` without affecting Walk
  Mode readiness.
- If the single OCR worker is already active, another Explore request returns a
  retryable `CONFLICT`; requests do not accumulate in a queue.

## 14. Local VLM snapshot query

The VLM endpoint is user-triggered and is never called by the continuous Walk
Loop. It loads Moondream2 from local files on CUDA for one request, releases the
model and CUDA cache afterward, and never stores the submitted image.

### `POST /api/v1/vlm/query`

Content type: `multipart/form-data`

| Part | Type | Rules |
|---|---|---|
| `prompt` | string | Required, trimmed, 1–500 characters |
| `frame` | JPEG image | Optional; exactly one of `frame` or `image_base64` is required |
| `image_base64` | string | Optional raw base64 or `data:image/jpeg;base64,...`; exactly one image input is required |

```ts
interface VLMTimings {
  decode_ms: number;
  load_ms: number;
  inference_ms: number;
  unload_ms: number;
  total_ms: number;
}

interface VLMQueryResponse {
  schema_version: SchemaVersion;
  server_time: Timestamp;
  model: "moondream2";
  text: string;
  timings: VLMTimings;
}
```

Invariants:

- Inference uses the local CUDA model directory only; runtime downloads and
  cloud calls are prohibited.
- Only one VLM request may execute. A second request receives retryable
  `CONFLICT`; requests never accumulate.
- A timed-out request receives retryable `REQUEST_TIMEOUT`; its worker remains
  reserved until the underlying inference finishes and releases CUDA memory.
- Missing model files, unavailable CUDA, insufficient safe free VRAM, CUDA OOM,
  or model failure return retryable `MODEL_NOT_READY` without disabling Walk
  Mode.
- The response contains generated text only; it is descriptive assistance, not
  a mobility-safety decision.

### `POST /api/v1/vlm/locate`

This endpoint is user-triggered. It performs one Moondream2 detection pass,
unloads the VLM and releases CUDA cache, and only then initializes the CPU
tracker. It is never called by continuous Walk processing.

Query parameters:

| Parameter | Type | Rules |
|---|---|---|
| `target_name` | string | Required, trimmed, 1–120 characters |
| `session_id` | string | Optional active Walk session; required to use current-frame memory or enable tracking |

Multipart parts:

| Part | Type | Rules |
|---|---|---|
| `frame` | JPEG image | Optional explicit snapshot |
| `image_base64` | string | Optional raw base64 or `data:image/jpeg;base64,...` |

Exactly one image source is selected. An explicit request provides one of
`frame` or `image_base64`. If neither is supplied, `session_id` selects an
atomic copy of that session's latest decoded frame. An explicit snapshot may
also include `session_id` to initialize tracking against that session. Without
an active session, localization can succeed but `tracking_allowed` is `false`.

```ts
interface VLMTargetBox {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

interface VLMLocatedTarget {
  label: string;
  confidence: number | null;
  box: VLMTargetBox;
  point: NormalizedPoint;
}

interface VLMLocateResponse {
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
```

Moondream2's local `detect` API supplies normalized boxes but no calibrated
probability. `target.confidence` is therefore `null`; the backend must not
invent a score. If several boxes are returned, the largest valid box is chosen,
with centre proximity as the deterministic tie-breaker. `point` is that box's
centre. A missing target returns `NOT_FOUND`.

For an active session, successful tracker initialization changes state from
`LOCATING` to `LOCKED_TRACKING`. OpenCV MIL updates the normalized box on each
Walk frame, while a target appearance histogram supplies normalized tracking
confidence. Failed updates or confidence below the configured threshold change
state to `TARGET_LOST` and schedule `Target lost. Stop and scan again.` This
announcement remains pending while safety guidance is active. Tracker state,
histograms, and frame snapshots are process-local and deleted on session end.

The locator shares every `/query` worker, timeout, offline-runtime, VRAM guard,
non-queueing, error-isolation, and immediate-unload invariant above.
