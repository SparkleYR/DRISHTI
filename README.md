# DRISHTI

DRISHTI is a local-only accessibility prototype composed of a FastAPI service with SQLite, a laptop-hosted AccessOps dashboard, and a minimal Expo physical-test harness. The final production mobile application will be implemented natively in Kotlin outside this workflow.

## Current scope

Phases 0 through 7 are complete. Phase 8 has been reopened for supplemental
review after its indoor accuracy correction; implementation and automated CUDA
checks pass, while controlled-frame replay and the repeated hall check remain.
Phase 9 local VLM integration and Phase 10 recurring-hazard/accessibility work
remain implemented and in review. The repository currently provides:

- Local backend configuration, structured logging, health reporting, and SQLite/Alembic initialization
- An in-memory walking-session API and a typed multipart JPEG analysis endpoint with YOLO11n detections
- Safe in-memory OpenCV decode, orientation correction, upload limits, frame-ID checks, and freshness checks
- A bare-bones Expo harness that can generate non-overlapping continuous test traffic, adapts its delay, rejects stale responses, reports one connection-loss state per incident, and renders normalized guidance geometry
- A normalized capture-to-preview coordinate transform with visible test markers and crop-aware boxes
- Session-scoped object tracking, motion/approach evidence, and geometric relative proximity
- Perspective-aware corridor occupancy and normalized surface/corridor polygons
- Local CUDA ADE20K semantic segmentation for indoor floor, structural,
  furniture, road, and unknown surface evidence
- Local SQLite hazard, observation, status-history, and consented-evidence persistence
- Anonymous report, active/nearby query, optimistic transition, merge, and dashboard-summary APIs
- A polling AccessOps dashboard with an overview, verification queue, workflow actions, and normalized local map plane
- Minimal Expo report confirmation and nearby-active synchronization controls
- A one-shot, CPU-only Tesseract 5 Explore endpoint with typed text,
  route-number, confidence, and no-text results
- A minimal Expo **Read sign once** control for physically checking the Explore
  contract without turning Expo into a production client
- Typed, on-demand local Moondream2 query and target-localization APIs with
  file/base64 or active-session snapshot input, a non-queueing worker, timeout,
  CUDA free-memory guard, and immediate unload
- Session-scoped Ask -> Lock -> Guide tracking with clock-face direction,
  target-loss handling, strict safety-guidance preemption, and latest-only
  WebSocket telemetry
- Indoor obstacle mapping, relative visible-floor extent, stairs/level-change
  stops, and corroborated wall/dead-end awareness using the existing typed
  corridor, overlay, and risk contracts
- Deterministic same-category, same-map duplicate consolidation with preserved
  observations and configurable normalized distance/time thresholds
- Category-aware temporary-hazard expiry, including short-lived person reports
  and locally recorded automatic resolution history
- A versioned normalized Hall Obstacle Course with per-segment and overall
  advisory accessibility scores
- Judge-readable score explanations covering severity, verification status,
  recurrence, confidence, freshness, spatial influence, and exact deductions
- Idempotent local hall seed data for demonstrating recurrence and resolution
- Shared TypeScript health, walking, hazard, dashboard, geometry, overlay, and error contracts

Monocular depth, production mobile behavior in Expo, unvalidated outdoor India-specific detection, and online maps remain intentionally absent. The campus image is not yet supplied, so the dashboard uses versioned normalized coordinates on a neutral local reference plane. Accessibility scores and VLM answers are advisory descriptions, not navigation instructions or safety certifications. DRISHTI never claims exact distance or that a scene or crossing is safe.

## Prerequisites

- Python 3.12
- Node.js 24 or newer
- npm 11 or newer
- An Android phone with Expo Go for the physical LAN acceptance check
- An NVIDIA RTX 4060-compatible driver for the approved CUDA path
- Tesseract 5 with English language data, available at the configured
  `DRISHTI_TESSERACT_COMMAND` path

Development may use standard package mirrors. Normal application runtime must not require internet access.

## Install

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r backend\requirements-cuda.txt
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt -r backend\requirements-dev.txt
npm install
Copy-Item .env.example .env
```

`.env` is local and ignored. Review it before starting the backend.

Download the official `yolo11n.pt` development asset to
`models\detector\yolo11n.pt` and verify its digest against
`models\detector\README.md`. Normal backend startup is offline and will report
the detector unavailable instead of downloading missing weights.

Download the approved files from `nvidia/segformer-b0-finetuned-ade-512-512`
into `models\segmentation\segformer-b0-ade20k`, then verify the safetensors
digest against `models\segmentation\README.md`. The prior Cityscapes snapshot is
retained only for controlled fallback comparisons. SegFormer loads local files
only, with Hugging Face offline mode and telemetry disabled.

Phase 7 uses the ignored local runtime at
`.tools\Tesseract-OCR\tesseract.exe` by default. It must contain
`tessdata\eng.traineddata`. The backend validates both at startup and degrades
only Explore Mode if OCR is unavailable.

Phase 9 uses the Apache-2.0 `vikhyatk/moondream2` release pinned to
`2025-06-21`. Download it during development into
`models\vlm\moondream2`, and download `moondream/starmie-v1`'s
`tokenizer.json` into `models\vlm\starmie-v1`. Backend runtime uses
`local_files_only`, a repository-local trusted-code cache, and offline
environment flags; it never downloads model files. The VLM is loaded only for
an explicit snapshot request and is unloaded before the response is returned.
Target tracking starts only after unload and uses CPU OpenCV state; Moondream2
is never added to continuous Walk processing.

## Initialize SQLite

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

This creates the local database at `data/drishti.db`. Only the FastAPI service may access it.

## Run the backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Local health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

For Expo Go, enter `http://<laptop-private-ip>:8000` in the mobile settings screen. Permit port 8000 only on the Windows private-network firewall profile.

## Run the dashboard

```powershell
npm run dev --workspace apps/dashboard
```

Open `http://localhost:3000`.

## Run the Expo test harness

```powershell
npm run start --workspace apps/mobile -- --lan
```

Scan the Expo Go QR code while the phone and laptop are connected to the same private network.

In the harness:

1. Save and check `http://<current-laptop-private-ip>:8000`.
2. Open the camera test and grant camera permission.
3. Capture a fresh controlled frame, select **Prepare hazard report**, inspect the raw category/severity, then select **Confirm anonymous report**.
4. Open the dashboard and confirm the report appears within two seconds.
5. Exercise **Verify**, **Assign**, **Start**, and **Resolve** using the local operator fields.
6. Confirm the Expo nearby-active count returns to zero after resolution synchronization.
7. The continuous capture controls remain available for confirming that dashboard or database endpoint failures do not stop Walk Mode.
8. Point the camera at a prepared high-contrast English sign containing a route
   token such as `BUS 42A CENTRAL`, tap **Read sign once**, and inspect the raw
   confidence, message, and route-number response.
9. For the Phase 8 supplemental gate, test a clear hall, a frontal wall, a side
   wall with an open forward path, stairs, and controlled indoor obstacles.
   Confirm a safe polygon is reachable on clear floor, a frontal wall stabilizes
   to `WALL_OR_DEAD_END_AHEAD`, stairs stabilize to
   `STAIRS_OR_LEVEL_CHANGE_AHEAD`, and no movement points into a wall.

The laptop private address may change when Wi-Fi or hotspot connections change. Port `8081` belongs to Expo; the backend uses port `8000`.

## Prepare the Phase 10 hall demonstration

Apply the migration before restarting the backend:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

Optional seed data adds six observations that deterministically consolidate
into a recurring chair, recurring backpack, and desk obstruction. It is
idempotent: a second run makes no changes.

```powershell
.\.venv\Scripts\python.exe backend\scripts\seed_phase10_demo.py
```

The Expo harness now uses the `hackathon-demo-hall` map version `1` centre
coordinate so confirmed physical reports affect the Hall Obstacle Course
analytics. The coordinate is a declared demonstration reference; it is not
camera-derived indoor localization.

Follow [docs/PHASE10_DEMO.md](docs/PHASE10_DEMO.md) for the controlled judge
walkthrough and manual acceptance checks.

## Query the local VLM

Send one JPEG snapshot and prompt as multipart form data:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/vlm/query -F "prompt=What large vehicle is visible?" -F "frame=@test-media/phase2/ultralytics-bus.jpg;type=image/jpeg"
```

The Android client may alternatively send `image_base64`. Do not invoke this
endpoint from the continuous camera loop.

Locate a target in an explicit snapshot:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/vlm/locate?target_name=bus" -F "frame=@test-media/phase2/ultralytics-bus.jpg;type=image/jpeg"
```

Include an active Walk `session_id` to initialize tracking. If the request omits
both image parts, the backend atomically copies that session's latest decoded
frame. Target metadata is then included in each Walk response and is also
available from `ws://127.0.0.1:8000/api/v1/walk/sessions/{session_id}/telemetry`.
Safety `guidance` always takes precedence over target speech and haptics.

## Verify Phase 10

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_phase10_accessibility.py
.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_real_ocr.py -m real_ocr
npm run typecheck
npm test
npm run build --workspace apps/dashboard
npm run config:check --workspace apps/mobile
npm run export:android --workspace apps/mobile
```

The existing real-model test uses local YOLO11n and ADE20K SegFormer weights
with the controlled street fixture while outbound HTTP is denied. The optional
`real_indoor` test reads explicitly approved controlled frames from the external
`DRISHTI_INDOOR_FIXTURE_DIR`; continuous walk frames are never committed. The real-OCR test sends an
in-memory prepared sign through the actual Explore API while outbound HTTP is
also denied. Phase 7 OCR runs in one independently bounded CPU worker; it cannot
queue behind or disable Walk inference.

Phase boundaries and acceptance gates are defined in `docs/IMPLEMENTATION_PLAN.md`. API behavior is frozen in `docs/API_CONTRACTS.md`.
