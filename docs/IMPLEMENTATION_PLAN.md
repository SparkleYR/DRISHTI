# DRISHTI Implementation Plan

## 1. Purpose

This is the dependency-ordered execution plan for DRISHTI. It is a control document, not authorization to implement every phase. Work advances one phase at a time and only after the active phase passes its review gate.

This workflow is backend-first. The production Android application will be implemented natively in Kotlin outside this workflow. The Expo project is retained only as a bare-bones physical test harness for local API responses, frame uploads, response freshness, and AR-coordinate alignment. Expo work must remain at the absolute minimum needed to verify the backend contract for the active phase.

## 2. Status vocabulary

| Status | Meaning |
|---|---|
| `NOT_STARTED` | No implementation work is authorized or underway. |
| `IN_PROGRESS` | This is the only active phase. Work remains subject to its scope and gate. |
| `BLOCKED` | Work cannot continue without an approved decision, prerequisite, asset, or external condition. |
| `IN_REVIEW` | Implementation is complete and evidence is awaiting review. |
| `COMPLETE` | Every required automated and manual acceptance check passed and the phase gate was approved. |
| `SKIPPED` | An optional phase was explicitly omitted; no implementation from it is present. |

## 3. Phase status

| Phase | Name | Scope | Status |
|---:|---|---|---|
| 0 | Contracts and Local Skeleton | Core MVP | `COMPLETE` |
| 1 | Camera-to-Backend Vertical Slice | Core MVP | `COMPLETE` |
| 2 | Object Detection and Basic Live Overlays | Core MVP | `COMPLETE` |
| 3 | Segmentation, Tracking, Proximity, and Corridor Analysis | Core MVP | `COMPLETE` |
| 4 | Risk Engine and Live AR Guidance | Core MVP | `COMPLETE` |
| 5 | Continuous Capture Hardening | Core MVP | `COMPLETE` |
| 6 | Hazard Reporting and Local Dashboard Loop | Core MVP | `COMPLETE` |
| 7 | Explore Mode and OCR | Optional expansion | `COMPLETE` |
| 8 | Indoor Campus Hazard Expansion | Optional expansion | `COMPLETE` |
| 9 | Optional Local Vision-Language Model | Optional expansion | `IN_REVIEW` |
| 10 | Recurring Hazards and Accessibility Scoring | Optional expansion | `IN_REVIEW` |
| 11 | Reliability and Product Hardening | Optional expansion | `NOT_STARTED` |

Phases 0 through 8 passed their automated and required physical checks, and their gates were approved. Phase 9 implementation, automated checks, and the real RTX 4060 model/core-model coexistence check are complete; user gate approval remains pending. Phase 10 implementation and automated checks are complete; its controlled hall demonstration and user gate approval remain pending.

## 4. Global gates

Every phase must satisfy all of the following before it can be marked `COMPLETE`:

- Its preceding required phase is `COMPLETE`; an explicitly `SKIPPED` optional phase does not block the next approved phase.
- Its declared automated tests pass.
- Its required device or controlled physical checks pass.
- No continuous walking frame is persisted.
- No runtime cloud dependency or external endpoint is introduced.
- Failure and uncertainty paths are tested.
- API changes remain typed, versioned, and documented.
- No later-phase feature was prematurely added.
- Review evidence is presented to the user and the phase gate is approved.

## 5. Explicit exclusions

The core hackathon MVP excludes:

- Cloud inference, cloud storage, hosted databases, public hosting, and runtime internet dependencies
- Exact metric distance from a monocular camera
- A claim that a road is safe to cross
- Turn-by-turn navigation
- Replacement of a white cane, guide dog, mobility training, or human judgment
- Recognition of every outdoor hazard
- Facial recognition or personal identity tracking
- Continuous video or walking-frame storage
- Multi-user production authentication
- RAG, LangChain, LangGraph, multi-agent orchestration, or an LLM/VLM in the Walk Loop
- Online map tiles
- Emergency call/SMS integration unless separately specified and approved
- Personal route-history collection
- Production Android application development; the final mobile application is a separate native Kotlin deliverable outside this workflow
- Polished UI, production navigation, branding, onboarding, accessibility interaction design, or other product-facing refinement in Expo
- Production mobile features in Expo, including final speech, haptic, camera lifecycle, and release-packaging behavior

Phases 7 through 11 are not authorized merely because they appear in this plan. They require separate approval after Phase 6 and the core loop are stable.

## 6. Mobile test-harness boundary

- Expo is not the production DRISHTI application and must not evolve into one.
- Add Expo code only when it is the smallest practical way to exercise an approved backend endpoint or physically validate frame transfer, freshness handling, or normalized overlay coordinates.
- Test controls may display raw or minimally formatted backend state. Do not add visual polish, production navigation, onboarding, animation, branding work, or speculative mobile abstractions.
- Production-grade camera lifecycle, speech, haptics, accessibility interaction, and Android release behavior belong to the separate native Kotlin application and are not deliverables of this workflow.
- Backend behavior must remain client-independent and conform to the frozen typed API contracts so the future Kotlin client can replace the Expo harness without backend redesign.
- Development effort in this workflow is prioritized toward FastAPI, the computer-vision pipeline, deterministic spatial/risk logic, and SQLite persistence.

## 7. Dependency-ordered phases

### Phase 0 — Contracts and Local Skeleton

**Goal:** Establish the smallest runnable local backend, database, dashboard health shell, and Expo connectivity harness without loading AI models.

**Deliverables:**

- Repository and npm workspace structure
- Bare-bones Expo test harness with a persisted local backend address and health check
- FastAPI application, typed health contract, configuration, and local logging
- SQLAlchemy/Alembic setup and local SQLite initialization
- React/Vite dashboard shell that reads backend health
- Shared API types and stable error envelope
- Local-only configuration and startup documentation

**Acceptance criteria:**

- Backend starts without importing or loading the AI pipeline.
- `/api/v1/health` returns typed service, model, compute, and database state.
- SQLite is initialized at `data/drishti.db` through migrations.
- Mobile saves and reloads the backend LAN URL.
- A physical Android phone running Expo Go reaches the backend on the private LAN.
- Dashboard displays healthy, degraded, and unreachable backend states.
- No cloud service, analytics SDK, hosted endpoint, or later-phase feature is present.

### Phase 1 — Camera-to-Backend Vertical Slice

**Goal:** Prove with the Expo harness that a real phone can send a selected image to the laptop and receive a fresh typed response, establishing the backend upload and coordinate contract for the future Kotlin client.

**Deliverables:**

- Minimal Expo camera permission and preview needed for the physical test
- Minimal transparent coordinate-test layer above the preview
- Controlled single-frame capture and JPEG compression
- Multipart upload with session ID, frame ID, and capture timestamp
- Size/type validation and safe OpenCV decode
- Echo response containing frame dimensions, frame ID, and stage timing
- Test-only preview-coordinate transform with known-point tests

**Acceptance criteria:**

- Five consecutive real-phone frames reach the laptop.
- Every response carries the matching session and frame ID.
- Malformed, unsupported, and oversized inputs return stable typed errors.
- No received frame is written to disk.
- Preview remains responsive during the test.
- Overlay corner and centre markers align after rotation, crop, and scaling.

### Phase 2 — Object Detection and Basic Live Overlays

**Goal:** Return reliable structured detections for the initial supported object set and use the Expo harness only to verify aligned boxes on a physical phone.

**Deliverables:**

- Pluggable detector interface
- One lightweight pretrained detector loaded once at startup
- Canonical label mapping and confidence/class filters
- Normalized typed bounding boxes
- Minimal test rendering of object boxes, labels, and initial yellow/red states
- Controlled image fixtures for chair, person, bag, bicycle/motorcycle, car, and bus where supported

**Acceptance criteria:**

- Detector is not reloaded per request.
- Supported demonstration objects are evaluated under expected lighting and camera angles.
- Unsupported or irrelevant classes are filtered.
- Detection JSON is stable and conforms to the contract.
- Boxes align with real objects on the phone preview.
- Model-unavailable state disables Walk Mode with a clear error.

### Phase 3 — Segmentation, Tracking, Proximity, and Corridor Analysis

**Goal:** Transform perception results into mobility-relevant spatial features.

**Deliverables:**

- Walkable, road, non-walkable, and unknown segmentation
- Session-scoped tracking with stable track IDs
- Bottom-centre anchors and perspective-aware walking trapezoid
- Path overlap and left/centre/right occupancy
- Relative proximity with optional depth and geometric fallback
- Approach-rate and motion-vector estimation
- Normalized safe, blocked, and uncertain polygons

**Acceptance criteria:**

- Nearby frames preserve a stable track ID for the same object.
- A centre object has greater path overlap than the same object at the edge.
- Growing boxes increase the approach estimate.
- The backend identifies a meaningfully clearer corridor.
- Depth failure falls back to geometric proximity without claiming metric distance.
- Segmentation produces a correctly aligned visible surface overlay.
- A controlled approaching-vehicle fixture produces an approach state and motion arrow.

### Phase 4 — Risk Engine and Live AR Guidance

**Goal:** Produce one stable mobility action in the backend and verify its typed guidance and AR coordinates through the Expo harness. Production visual, speech, and haptic delivery belongs to the future Kotlin application.

**Deliverables:**

- Configurable normalized scoring and class severities
- Explicit safety overrides
- Direction selection with a decision margin
- Alert state machine, persistence, hysteresis, cooldown, and deduplication
- `CLEAR`, `CAUTION`, `MOVE_LEFT`, `MOVE_RIGHT`, `STOP`, and `PAUSE_UNCLEAR`
- Minimal Expo stale-result rejection needed to validate frame freshness
- Minimal test rendering of safe corridor, blocked regions, uncertainty, and direction arrow for coordinate validation
- Typed speech and haptic guidance fields for the future Kotlin client, validated by contract tests rather than production Expo behavior

**Acceptance criteria:**

- Centre obstacle produces an actionable warning.
- Side-only low-risk objects do not trigger unnecessary speech.
- Centre blocked/right clear produces `MOVE_RIGHT`.
- Centre blocked/left clear produces `MOVE_LEFT`.
- Both sides blocked produces `STOP`.
- Weak or contradictory evidence produces `PAUSE_UNCLEAR`, not invented guidance.
- Repeated unchanged conditions do not speak every frame.
- A critical override bypasses cooldown and interrupts lower-priority guidance.
- Corridor state, direction arrow, and typed speech/haptic guidance fields agree in the backend response and contract tests.
- The complete chair-centre/right-clear vertical slice succeeds repeatedly.

### Phase 5 — Continuous Capture Hardening

**Goal:** Keep backend guidance recent and responsive without producing a stale-frame backlog, using the Expo harness only to generate and observe real-device traffic.

**Deliverables:**

- Minimal test capture scheduler in Expo
- One in-flight request per Expo test session
- Backend latest-frame-wins queue with one replaceable waiting frame
- Stage-level latency and result-age metrics
- Adaptive capture rate
- Minimal connection-loss and retry behavior required to test backend recovery
- Guidance pause when responses exceed the freshness limit

**Acceptance criteria:**

- The request queue never grows without bound.
- Superseded frames are dropped and reported deterministically.
- Guidance corresponds to recent frames within the configured age limit.
- A temporary network interruption does not crash either application.
- The connection-loss state is emitted at most once per incident for the future Kotlin client; the Expo harness may show it as raw test state.
- Capture and guidance recover after connectivity returns.

### Phase 6 — Hazard Reporting and Local Dashboard Loop

**Goal:** Complete the local institutional `Report -> Verify -> Resolve -> Sync` backend and dashboard workflow, using only minimal Expo controls to exercise phone-facing endpoints.

**Deliverables:**

- Minimal Expo report-confirmation control for endpoint testing
- Hazard, observation, and status-history persistence
- Versioned local map coordinates; campus image added when supplied
- Dashboard overview and verification queue
- Verify, reject, assign, start, resolve, and merge operations
- Poll-based status synchronization
- Nearby active-hazard results for mobile
- Resolved-event suppression

**Acceptance criteria:**

- A confirmed phone report appears on the dashboard.
- No user identity is included by default.
- Optional evidence is stored only after explicit confirmation.
- An operator can verify, reject, assign, start, and resolve a report through valid transitions.
- Every status transition records time, previous state, new state, and operator alias.
- Invalid transitions and stale concurrent updates are rejected.
- Resolution disappears from active mobile results after synchronization.
- Database or dashboard failure does not break Walk Mode.
- The complete loop works without internet access.

### Phase 7 — Explore Mode and OCR

**Goal:** Let the user deliberately inspect visible text without affecting Walk Mode.

**Deliverables:** One-shot test capture, local backend OCR, typed Read Sign response, route-number extraction, and confidence handling. Production capture UX and speech belong to the future Kotlin client.

**Acceptance criteria:** A prepared sign and route number are read in controlled lighting; low-confidence text is qualified; no image leaves the LAN; OCR cannot block Walk Mode.

### Phase 8 — Indoor Campus Hazard Expansion

**Goal:** Strengthen the handheld-camera Walk Loop for the available indoor Indian campus hall demonstration without claiming support for outdoor hazards that cannot be physically validated.

**Deliverables:**

- Versioned hall label specification for the enabled demonstration set
- Canonical `dining table`/`table` to `desk` mapping in the existing generic detector
- Wall/dead-end evidence derived from the already approved local SegFormer wall label and corridor geometry
- Configurable wall-confidence and corridor-coverage thresholds
- Deterministic `WALL_OR_DEAD_END_AHEAD` risk rule using the frozen guidance and overlay contract
- Health and degradation reporting that does not make the optional hall expansion a prerequisite for generic Walk Mode
- Controlled positive, negative, and hard-negative fixtures; no walking-frame persistence

**Acceptance criteria:**

- Person, chair, bag, and desk detections use the existing normalized detection, tracking, overlay, and risk contracts.
- A sufficiently confident wall spanning left, centre, and right forward corridors produces a stable `STOP` decision with reason `WALL_OR_DEAD_END_AHEAD`.
- A side wall or low-confidence wall mask does not produce a false dead-end stop.
- An unavailable segmentation model leaves the generic detector and Walk Mode operational and reports the hall expansion as degraded.
- Clear-hall and ordinary obstacle fixtures measure false stops explicitly.
- No outdoor class, floor-cable class, or unsupported custom label is advertised.
- The complete pipeline runs locally and never stores submitted walking frames.
- Controlled physical tests cover a clear hall, a wall ahead, a side wall, and desk/chair/bag/person obstacle arrangements without unsafe blindfolded walking.

### Phase 9 — Optional Local Vision-Language Model

**Goal:** Answer narrow, on-demand scene questions locally without affecting real-time safety processing.

**Deliverables:** Local Moondream2 model files, typed `POST /api/v1/vlm/query` multipart contract with JPEG-file or base64 input, one non-queueing worker, timeout, CUDA free-memory guard, lazy per-request loading, and immediate unload/cache release. The Android application consumes the contract separately; Expo receives no Phase 9 product work.

**Acceptance criteria:** The endpoint returns an accurate natural-language answer for a controlled image and prompt; file and base64 payloads validate against the typed contract; runtime inference uses local files and CUDA only; submitted snapshots are never persisted; timeout and concurrent-request behavior are safe; insufficient VRAM degrades only the VLM request; the core detector and Walk Mode remain available before, during, and after VLM work without CUDA OOM. Phase 9 remains `IN_REVIEW` until the real-model CUDA check and user gate approval pass.

### Phase 10 — Recurring Hazards and Accessibility Scoring

**Goal:** Convert repeated observations from the indoor Hall Obstacle Course into transparent local accessibility intelligence without treating an advisory route score as live mobility guidance.

**Deliverables:** Deterministic same-category/same-map duplicate merging, recurrence counts, category-aware temporary-hazard expiry, a versioned normalized Hall Obstacle Course route/segment model, explainable segment and route scores, judge-readable dashboard analytics, and repeatable local seed data. Person observations expire faster than movable furniture. Resolved, rejected, merged, and expired hazards cannot reduce active scores.

**Acceptance criteria:** The nearest eligible duplicate is selected deterministically; different maps, map versions, categories, or distant reports do not merge; recurrence counts preserve every observation; resolved hazards do not reduce active scores; every deduction exposes severity, status, confidence, recurrence, freshness, spatial influence, and penalty; temporary hazards expire or require reconfirmation; the dashboard clearly states that the score is not a navigation or safety instruction; seeded hall data demonstrates score improvement after resolution; Walk Mode remains independent of database and analytics availability.

### Phase 11 — Reliability and Product Hardening

**Goal:** Make the approved local backend, inference pipeline, persistence, dashboard, and Expo verification harness reproducible and resilient.

**Deliverables:** Expanded automated coverage, structured local logs, model warm-up, explicit CPU/unsupported behavior, database backup/export, attribution, safety/privacy documentation, and repeatable PowerShell startup commands.

**Acceptance criteria:** A fresh local setup follows documented steps; approved workflows pass; failures produce accessible behavior; normal operation needs no external URL; three consecutive end-to-end runs succeed.

## 8. Core MVP completion gate

The core hackathon MVP is complete only after Phases 0 through 6 are individually `COMPLETE` and the following combined run succeeds three consecutive times:

```text
Expo test preview -> local frame transfer -> detection -> segmentation/tracking
-> spatial/risk decision -> verified typed guidance and AR coordinates
-> test report -> dashboard verification/resolution -> endpoint sync
```

This gate validates the backend and its physical mobile-facing contracts. It does not certify a production mobile experience; native Kotlin implementation and production mobile validation occur outside this workflow.

Only then may an optional expansion phase be proposed.
