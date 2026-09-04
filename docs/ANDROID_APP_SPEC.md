# DRISHTI Native Android Application Specification

> **Status:** authoritative build spec for the production native client.
> Supersedes `android_plan.md` (kept for its accessibility rationale).
> Binding source-of-truth order: `docs/DECISIONS.md` → `docs/API_CONTRACTS.md`
> → `docs/IMPLEMENTATION_PLAN.md` → this document → `android_plan.md`.
> Any conflict with the frozen API contract is resolved in favour of the
> contract; propose a decision in `DECISIONS.md` before diverging.

---

## 1. Purpose and boundary

This is the real production client that D-026 defers "outside this workflow".
It replaces the disposable Expo harness in `apps/mobile` (which stays untouched).
The backend, its typed `/api/v1` contract, the CV pipeline, the risk engine, and
SQLite persistence are **frozen and complete (Phases 0–8, Phase 10 in review)**.
The app is a pure client of that contract: it owns camera capture, the single
capture→preview coordinate transform, stale-result rejection, speech, haptics,
spatial audio, gesture input, and Android lifecycle. It performs **no inference**
and makes **no cloud calls** — every request goes to the user-configured backend
on the private LAN.

### v1 scope (this build)

| In | Out (later pass) |
|---|---|
| Walk Mode: continuous `/walk/analyze` loop, overlay, spatial audio, haptics, tri-lingual TTS | On-device VLM; multi-turn VLM conversation |
| Explore Mode: on-demand OCR via `/explore` | WebSocket / high-FPS streaming transport |
| Scene Mode: on-demand VLM Q&A via `/api/v1/vlm/query` (spoken question → Moondream2 answer) | Turn-by-turn navigation, campus map rendering |
| Hazard reporting: `POST /hazards` + `/hazards/nearby` advisories | Emergency call/SMS/location dispatch |
| Local-only SOS (siren + banner + repeating TTS) | Standalone "Phantom Cane" sensor-fusion radar service |
| Gyro-assisted directional cue interpolation between backend responses | Accessibility-score dashboard views (facilities-only) |
| Screen-off `ForegroundService` execution | |

### Non-negotiable safety carries (from `AGENTS.md` / `DECISIONS.md` §3)

- Never say a road/crossing is safe. Never claim exact metric distance — only
  relative proximity bands.
- Weak/contradictory evidence → speak the `PAUSE_UNCLEAR` guidance, never invent
  direction.
- Colour is never the only signal: every state also has a word, an icon shape, a
  haptic pattern, and/or speech.
- No continuous frame storage. A hazard evidence JPEG leaves the device only
  after an explicit per-report consent gesture.
- No facial recognition, identity tracking, route-history logging, or analytics.
- The app is an assistive prototype; it never presents itself as a replacement
  for a cane, guide dog, mobility training, or human judgement.

---

## 2. Target + toolchain

| Item | Value |
|---|---|
| Module path | `apps/android/` (Gradle project `DRISHTI`, `:app`) |
| Package / applicationId | `com.drishti.app` |
| Language / UI | Kotlin, Jetpack Compose (Material 3) |
| minSdk / target / compile | 31 / 36 / 36 |
| Build | AGP 9, Gradle 9.1, Kotlin 2.3, KTS |
| Reference device | OnePlus CPH2767, Android 16 (API 36), 1272×2800 @ 560 dpi |
| Backend (dev) | `http://10.111.36.200:8000` on the LAN; **editable in-app**, persisted |

Key libraries: CameraX (`camera-core/camera2/lifecycle/view`), Retrofit +
OkHttp + `kotlinx-serialization-json`, `androidx.datastore:datastore-preferences`,
`androidx.lifecycle:lifecycle-service`, coroutines.

---

## 3. Backend contract the app consumes

All paths under `http://<base>/api/v1`. Field names are `snake_case`; every
response has `schema_version` (`"1.0.0"`) and `server_time` (RFC 3339 `Z`).
Error envelope: `{ error: { code, message, retryable, details? } }` with the
`ErrorCode` enum from `API_CONTRACTS.md` §5.

### 3.1 `GET /health`
Poll on the connection screen and every ~10 s while disconnected. Drives the
"backend ready / degraded / unreachable" announcement. `walk_mode_available`
gates the Start control; `models.ocr.status` gates Explore; `database.status`
gates hazard reporting.

### 3.2 `POST /walk/sessions`  → start
Body: `{ device_alias?: "drishti-android", settings?: { speech_rate?, preferred_language?, haptics_enabled?, risk_sensitivity? } }` (all normalized 0–1 except language = BCP 47).
Response carries the **session budget**: `session_id`, `recommended_capture_fps`
(≈2.0), `max_image_width` (1280), `max_image_bytes` (5 MiB), `max_result_age_ms`
(3000). The app must obey every one of these.

### 3.3 `PATCH /walk/sessions/{id}/end`
Idempotent. Call on Stop, on app background beyond the grace window, and on
process death recovery.

### 3.4 `POST /walk/analyze`  (`multipart/form-data`)
Parts: `frame` (**`image/jpeg`**, ≤ `max_image_bytes`, width ≤ `max_image_width`),
`session_id`, `frame_id` (int, **strictly increasing per session**), `captured_at`
(RFC 3339 UTC `Z`), `rotation_degrees` (`0|90|180|270`).

Response `FrameAnalysisResponse` (see `API_CONTRACTS.md` §8 / `packages/contracts`):
`geometry{source_width,source_height,rotation_degrees,mirrored:false}`,
`detections[]`, `surfaces[]`, `corridors{left,centre,right_cost}`,
`overlay{preferred_corridor, safe/blocked/uncertain_polygons, direction_arrow, valid_until}`,
`guidance{level, action, speech, haptic_pattern, speak, reason_code}`,
`timings{...,total_ms}`, `degraded_modules[]`.

Backend-enforced rejections the client must handle without crashing:
`FRAME_TOO_OLD` (age > `max_result_age_ms`, also checked again after queueing),
`FRAME_ID_NOT_MONOTONIC`, `FRAME_SUPERSEDED` (a newer frame displaced this one in
the latest-frame-wins scheduler), `MODEL_NOT_READY`, `INVALID_CONTENT_TYPE`,
`IMAGE_TOO_LARGE`, `SESSION_NOT_FOUND` / `SESSION_ENDED`.

### 3.5 `POST /explore`  (`multipart/form-data`)
Parts: `frame` (`image/jpeg`, ≤ 8 MiB, width ≤ 2048), `mode` = `"READ_TEXT"`,
`preferred_language` = `"en"` (backend is English-only; non-`en*` → `INVALID_REQUEST`).
Response `ReadTextResponse`: `text`, `route_numbers[]`, `confidence` (0–1),
`confidence_qualification` `HIGH|LOW|NONE`, `message`, `no_text_found`, `timings`.
- `NONE` → "No text found."
- `LOW` → message prefixed `Possible text:` — speak it as *uncertain*.
- `HIGH` → message is the text.
`CONFLICT` (retryable) means the single OCR worker is busy — retry once after a
short delay, do not queue. `MODEL_NOT_READY` → Explore unavailable, Walk
unaffected.

### 3.6 Hazards
- `POST /hazards` — `application/json` `CreateHazardRequest`, or
  `multipart/form-data` with a `payload` JSON part + `evidence` JPEG part.
  Evidence bytes are rejected unless `evidence_consent:true`; consent with no
  image is valid and stores nothing. No identity fields. `201` →
  `{ hazard, merged_with_existing }`.
- `GET /hazards/nearby?map_id&map_version&map_x&map_y&radius` (normalized units)
  → `HazardListResponse` excluding `RESOLVED`/`REJECTED`.
- Status/merge/dashboard/accessibility endpoints are facilities-operator surface
  — **not used by the app**.

`DATABASE_UNAVAILABLE` from any hazard call must never affect Walk Mode.

### 3.7 Coordinate space — `ORIENTED_CAPTURE_NORMALIZED`
Origin = top-left of the orientation-corrected capture; `x` right, `y` down; all
geometry normalized to the full oriented capture (pre-letterbox); rear camera
**not** mirrored. The app applies **exactly one** transform from this space to
the on-screen preview, accounting for preview `COVER`/`CONTAIN` crop. Port the
verified math in `apps/mobile/src/overlay/transform.ts`. `rotation_degrees` sent
to the backend = the rotation needed to upright the JPEG the app encodes; if the
app encodes an already-upright JPEG it sends `0`.

---

## 4. Module architecture (`com.drishti.app`)

```
DrishtiApp                     Application; notification channel; AppContainer (manual DI)
MainActivity                   single activity; Compose host; volume-key intercept; keep-screen-on

net/
  Dto.kt                       @Serializable mirrors of packages/contracts (snake_case via @SerialName)
  DrishtiApi.kt                Retrofit interface: health, walk sessions, analyze, explore, hazards
  ApiModule.kt                 OkHttp (10s connect / 30s read for analyze), base-URL interceptor, JSON
  ApiResult.kt                 sealed Ok/ApiError(code,retryable,message)/Transport ; envelope parsing

settings/
  SettingsStore.kt             DataStore: baseUrl, spokenLang(EN|HI|TA), hapticsEnabled,
                               speechRate, spatialAudioEnabled, visualLayerEnabled, riskSensitivity,
                               emergencyContactLabel(optional, local only), hazardMapId/Version/X/Y

walk/
  WalkForegroundService        LifecycleService; owns CameraX + capture loop; persistent low-prio
                               notification; runs with screen off/locked; STOP action
  CameraFramePipeline          CameraX ImageAnalysis (YUV_420_888, keep-latest); ImageCapture for snapshots
  FrameEncoder                 YUV→NV21→JPEG (YuvImage), downscale to max_image_width, quality ~0.6,
                               rotation math → uprighted JPEG + rotation_degrees(0)
  CaptureLoop                  latest-frame-wins, ONE in-flight request, adaptive delay
                               (port apps/mobile/src/state/captureLoop.ts), capped backoff
  FrameFreshnessGate           the 5 discard rules (port frameFreshness.ts):
                               (1) not active session (2) paused/ended (3) frame_id ≤ last applied
                               (4) now > overlay.valid_until (5) now − captured_at > max_result_age_ms
  WalkController               state machine: IDLE→READY→WALKING→PAUSED→STOPPED / SOS
                               fan-out of each accepted response to feedback engines + UI

feedback/
  SpeechEngine                 TextToSpeech; EN/HI/TA voices; USAGE_ASSISTANCE_ACCESSIBILITY;
                               QUEUE_FLUSH on CRITICAL/STOP, QUEUE_ADD otherwise; rate from settings
  GuidanceStrings              (action, reason_code, lang) → localized string; NEVER speaks the
                               backend English `guidance.speech` verbatim for HI/TA
  HapticEngine                 VibratorManager; waveform dictionary keyed by HapticPattern;
                               cancel() before each new effect; respects hapticsEnabled + system
  SpatialAudioEngine           per-detection tone: stereo pan from bbox centre-x, pitch from
                               proximity band + risk_level, gain from risk; pooled AudioTrack/SoundPool;
                               silent when CLEAR
  GyroSteering                 TYPE_GAME_ROTATION_VECTOR; yaw delta since last accepted frame
                               re-points the active audio pan + directional haptic between responses;
                               decays to neutral after max_result_age_ms
  AudioFocusManager            requestAudioFocus(TRANSIENT_MAY_DUCK); duck media/TalkBack during
                               warnings; abandon when idle

explore/
  ExploreController            pause capture loop → ImageCapture hi-res → POST /explore →
                               speak text + spell route_numbers → resume loop; single-flight;
                               CONFLICT → one retry

hazard/
  HazardReporter               gesture → confirm (double-confirm gesture) → optional evidence
                               consent → POST /hazards (+evidence) → speak outcome
  NearbyAdvisor                every ~20 s while WALKING: GET /hazards/nearby(configured map point)
                               → speak only NEW additions, low priority, deduped

sos/
  SosController                full-screen SOS state; ToneGenerator/looping siren; repeating TTS;
                               no network; exit on triple-tap + confirm

ui/
  theme/                       pure #000000 bg; state colours YELLOW #FFEB00 / RED #FF3B30 /
                               GREEN #00E676 / GREY; display type 96–140sp; min touch target = full screen
  ReadyScreen                  "Double-tap anywhere to start walking." + backend status line
  WalkScreen                   AndroidView(PreviewView) + OverlayCanvas + StateBanner + edge-safe chips
  OverlayCanvas                Compose Canvas: detection boxes (colour = display_color, dashed for
                               uncertain), safe/blocked/uncertain polygons, direction arrow glyph
  StateBanner                  one giant word: READY / WALKING / CAUTION / LEFT / RIGHT / STOP /
                               PAUSED / SOS  + redundant icon shape
  BlankOverlay                 opaque black; toggled by two-finger double-tap; audio+haptics continue
  SettingsScreen              base URL, language, toggles, "test connection", emergency contact label
  ExploreResultCard            transient; shows OCR text/route numbers; re-speak button
  GestureLayer                 root pointerInput: see §6
  PreviewTransform             ORIENTED_CAPTURE_NORMALIZED → preview px (COVER/CONTAIN aware)

a11y/
  Semantics.kt                 every actionable node: contentDescription + role + customActions
                               mirroring the gestures, so TalkBack users get the same capabilities
```

### DI
Manual `AppContainer` held by `DrishtiApp`; `WalkForegroundService` and
`MainActivity` read from it. No Hilt for v1.

---

## 5. Walk Mode runtime loop

1. **Start** (ReadyScreen double-tap): request `CAMERA` permission if needed →
   `POST /walk/sessions` with `{ device_alias, settings:{ preferred_language,
   haptics_enabled, speech_rate, risk_sensitivity } }` → store session budget →
   start `WalkForegroundService` → CameraX binds `Preview` + `ImageAnalysis`
   (+ `ImageCapture` for snapshots).
2. **Per analysis frame** (`ImageAnalysis.Analyzer`, keep-latest):
   - If a request is already in flight → drop this frame (latest-frame-wins on
     the client too).
   - Else encode: YUV→JPEG, downscale so width ≤ `max_image_width`, ensure bytes
     ≤ `max_image_bytes` (drop quality, then skip frame if still too big).
   - `frame_id = ++counter`; `captured_at = Instant.now()` (UTC).
   - `POST /walk/analyze`; `total` client timeout 30 s but expected < 1 s.
3. **On response**: run `FrameFreshnessGate`. If it fails any of the 5 rules →
   discard silently (no overlay/speech/haptics). If it passes →
   `latestAppliedFrameId = frame_id`; fan out:
   - **UI**: overlay polygons/boxes/arrow via the one transform; `StateBanner`
     from `guidance.action`.
   - **Speech**: if `guidance.speak` → `SpeechEngine.say(GuidanceStrings(action,
     reason_code, lang), flush = level ∈ {HIGH, CRITICAL} || action == STOP)`.
     (For HI/TA we ignore `guidance.speech` and use our table; for EN the table
     matches the contract wording.)
   - **Haptics**: `HapticEngine.play(guidance.haptic_pattern)`.
   - **Spatial audio**: `SpatialAudioEngine.update(detections)` — pan/pitch/gain
     per detection; nothing if list empty or all `GREY`.
   - **Gyro**: record device yaw at accept time as the cue's reference bearing.
4. **Between responses**: `GyroSteering` shifts the current audio pan and the
   directional-haptic bias by the yaw delta, so a hazard "stays" to the user's
   left as they turn; the cue fades to neutral once the frame is older than
   `max_result_age_ms`.
5. **On transport failure**: announce "Connection lost" **once per incident**
   (mirror `CaptureLoopGate`), keep retrying with capped backoff, pause overlay +
   speech, announce "Connection restored" on recovery.
6. **Adaptive rate**: delay from `adaptiveCaptureDelayMs` using `total_ms`,
   `frame_age_ms`, `recommended_capture_fps`, `consecutiveFailures`.
7. **Stop**: `PATCH …/end`, unbind camera, stop service, abandon audio focus,
   return to ReadyScreen with a spoken confirmation.

### Degradation
`degraded_modules` containing `segmentation`/`india_hazards` → suppress
surface-polygon rendering, keep detections + guidance; announce "Surface
detection degraded" once. `MODEL_NOT_READY` → pause loop, announce, retry health.

---

## 6. Zero-look interaction

Root-level `pointerInput` gesture map (also exposed as TalkBack custom actions):

| Gesture | Action |
|---|---|
| Double-tap anywhere | ReadyScreen: start Walk. WalkScreen: Stop Walk (with 1-word spoken confirm). |
| Single-tap | Repeat last spoken guidance / status. |
| Long-press ≥ 1.5 s | **Scene Mode** — spoken question → VLM answer (`/vlm/query`). |
| Two-finger swipe right | Explore (OCR) snapshot. |
| Two-finger double-tap | Toggle `BlankOverlay` (screen black; audio/haptics stay live). |
| Triple-tap | Cancel current alert / re-centre state; in SOS → begin exit (confirm with double-tap). |
| Swipe up with two fingers | Begin Hazard report (then double-tap = confirm, long-press = add evidence w/ consent). |
| **Volume Up** (key intercept) | **Scene Mode** — spoken question → VLM answer. |
| **Volume Down** (key intercept) | Trigger **local SOS**. |

Volume keys are consumed in `MainActivity.onKeyDown`/`onKeyUp` (both press
directions) so the OS volume UI never appears; in-app "louder/quieter" lives in
Settings sliders. All gestures give an immediate haptic ack (`HapticEngine.ack()`)
before their spoken result.

### SOS (local only)
Full-screen red `SOS`, looping siren via `ToneGenerator`/short audio asset at max
in-app volume, and a repeating TTS line (localized) e.g. "Emergency. I need
help." No network, no SMS, no call. Optional local `emergencyContactLabel` string
is only displayed on screen for a bystander. Exit = triple-tap then double-tap.

### Scene Mode (on-demand VLM)
The deliberately-slow counterpart to the ~2 fps Walk loop. Long-press or
**Volume Up** while walking → `WalkController.triggerDescribe()`:

1. `mode = DESCRIBING`; `spatial.clear()`; haptic ack. The Walk loop is paused
   for the duration (same as Explore/`READING`).
2. `SpeechEngine` speaks "What would you like to know about the scene?", then
   `VoicePrompt` (`android.speech.SpeechRecognizer`, `RECORD_AUDIO`, language =
   the chosen spoken language) captures one utterance (overall cap 14 s).
   - No speech / recognizer unavailable → speak the miss line and fall back to
     the canned prompt "Describe what is directly in front of me, briefly."
   - Permission denied → speak `vlm_mic_denied`, still fall back to the prompt.
3. Speak "Working on it. Hold still.", take one `ImageCapture` still bounded to
   1280 px / q85.
4. `POST /api/v1/vlm/query` (multipart: `frame` JPEG + `prompt`). The OkHttp read
   timeout for this one path is widened to 70 s (`VlmTimeoutInterceptor`) to
   cover Moondream2's per-request load; backend's own cap is 45 s.
5. `409 CONFLICT` → one retry after 1.5 s. `REQUEST_TIMEOUT` / `MODEL_NOT_READY`
   / transport → localized spoken failure, no card.
6. On success: speak the answer verbatim (English, from the model) and show a
   white `SceneCard` (question + answer + round-trip seconds) for 35 s.
7. Restore `mode = WALKING` **only after the answer has finished speaking**.
   Every scripted line in this flow uses `SpeechEngine.speakBlocking` (suspends
   on the `UtteranceProgressListener` until that utterance's `onDone`); the
   Walk loop's first guidance line on resume is `QUEUE_FLUSH`, so a non-blocking
   answer would be cut off mid-sentence and replaced with "STOP, path blocked".
   `WalkController.applyResponse` also early-returns whenever
   `mode != WALKING`, so a walk response that was already in flight when Scene
   Mode started cannot speak or vibrate over it. Explore/OCR uses the same
   `speakBlocking` discipline for its readout.

The submitted image is never persisted client- or server-side. Scene Mode never
runs automatically and cannot influence guidance/haptics/overlay.

---

## 7. Feedback dictionaries

### 7.1 Haptic waveform dictionary (`VibrationEffect.createWaveform`)
| `HapticPattern` | Pattern (timings ms / amplitude) |
|---|---|
| `NONE` | — |
| `CAUTION_SHORT` | one 40 ms pulse @ 140 |
| `WARNING_DOUBLE` | 0,60,80,60 @ 200 — biased L/R by nudging the leading gap when action is MOVE_LEFT/RIGHT |
| `CRITICAL_RAPID` | (0,50,50)×6 @ 255, `cancel()` first, may repeat while STOP holds |
| `UNCLEAR_LONG` | 0,400 @ 90 (soft, long) |
| ack | one 15 ms pulse @ 120 |

### 7.2 Spatial audio mapping
- **Pan** (`AudioTrack.setStereoVolume` / `setVolume` per channel or `Spatializer`
  when available): `L = clamp(1 − (cx))`, `R = clamp(cx)` where `cx` = bbox
  centre-x ∈ [0,1]; centre → both ≈ 1.0. Then shifted by `GyroSteering` yaw.
- **Pitch**: base 320 Hz; `FAR→+0`, `MEDIUM→+120`, `NEAR→+280`, `IMMEDIATE→+520`;
  `APPROACHING` adds +80. `UNKNOWN` proximity → base.
- **Gain / cadence**: `WATCH` quiet single blip; `WARN` repeating ~2 Hz;
  `HIGH`/`CRITICAL` fast ~6 Hz + max gain. `CLEAR`/`GREY` → silence.
- At most the 2 highest-risk detections sound simultaneously.

### 7.3 Localized guidance strings (EN / HI / TA)
Keyed by `action`, refined by `reason_code` for `WALL_OR_DEAD_END_AHEAD`,
`APPROACHING_VEHICLE_CENTRE`, `ALL_CORRIDORS_BLOCKED`, `CENTRE_SURFACE_UNCERTAIN`.
EN strings match `API_CONTRACTS.md` §9 defaults. Stored in `res/values`,
`values-hi`, `values-ta` **and** an in-code map for the service (which has no
`Context` UI resources issue — it does; service uses `getString`). Route numbers
in Explore are spoken digit-by-digit with the localized "route"/"bus" prefix.

---

## 8. Accessibility (TalkBack coexistence)

- App drives its own speech + haptics so it is fully usable with TalkBack **off**.
- Every actionable Compose node still carries `contentDescription`, a `role`, and
  `customActions` duplicating the gesture set, so a TalkBack user swipes to a
  control and double-taps as normal.
- `SpeechEngine` uses `AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY` and
  requests transient-may-duck focus so DRISHTI speech and TalkBack do not talk
  over each other; `CRITICAL`/`STOP` flushes.
- Respect system: `Settings.Global` haptic toggle, font scale (banner uses `sp`),
  reduce-motion (disable non-essential overlay animation), and the system TTS
  engine + rate as the default.
- No colour-only signals (see §1).

---

## 9. Lifecycle & permissions

- Permissions: `CAMERA` (runtime), `POST_NOTIFICATIONS` (runtime, API 33+),
  `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_CAMERA`, `VIBRATE`, `INTERNET`,
  `ACCESS_NETWORK_STATE`, `WAKE_LOCK`. No location, SMS, phone, storage.
- `WalkForegroundService`: `foregroundServiceType="camera"`, persistent
  low-importance notification with a Stop action; partial wake lock while
  WALKING; survives screen-off and lock.
- Backgrounding the app keeps the service running (screen-off walking is the
  point). Process death: on relaunch, detect an orphan `session_id`, `PATCH
  …/end` it, return to ReadyScreen.
- `MainActivity`: `FLAG_KEEP_SCREEN_ON` while WALKING and not blanked;
  `setShowWhenLocked`-style behaviour not needed (service does the work).

---

## 10. Build status (v1, 2026-09-03)

All ten build-order steps are implemented and the app runs end-to-end on the
OnePlus CPH2767 against the live backend at `http://10.111.36.200:8000`.

| # | Area | State |
|---|---|---|
| 1 | Skeleton: gradle (AGP 9, Temurin 21 pinned), manifest, black theme, `AppContainer`, `SettingsStore`, `DrishtiApp`, `MainActivity`, Compose Ready/Walk/Settings | done, on device |
| 2 | Net: `Dto.kt` (full contract), `DrishtiApi`, `ApiModule` (runtime base-URL rewrite), `ApiResult`/envelope; Settings "test connection" | done; `/health` + all calls verified 200 |
| 3 | Camera + encode: `CameraFramePipeline` (Service-bound CameraX, main-thread bind), `FrameEncoder` (YUV→upright JPEG, size-bounded), `PreviewTransform` | done; preview surface to confirm against a lit scene |
| 4 | Walk loop: `CapturePacing` + `CaptureLoopGate`, `FrameFreshnessGate`, `WalkController`, `WalkForegroundService` (FGS camera + wake lock), `OverlayCanvas`, `StateBanner` | done; ~2 fps loop, 150–450 ms round-trips, freshness discards on mode change verified |
| 5 | Feedback: `SpeechEngine` (TTS, USAGE_ASSISTANCE_ACCESSIBILITY, flush on STOP/CRITICAL), `GuidanceStrings` (EN/HI/TA tables), `HapticEngine` (waveform dictionary), `SpatialAudioEngine` (synth AudioTrack) + `SonarMapping`, `AudioFocusManager` (duck), `GyroSteering` (rotation-vector yaw) | done; audio not yet ear-verified |
| 6 | Gestures (`walkGestures`: 1-finger taps/long-press + multi-finger recogniser), volume-key intercepts in `MainActivity`, blank-screen toggle, TalkBack semantics/onClick | done; volume-up Explore verified via keyevent |
| 7 | Explore: `ExploreController` (pause loop → hi-res still → `/explore` → speak → resume; CONFLICT retry) | done; verified 200 in ~2.4 s, loop auto-resumed |
| 8 | Hazard: `HazardReporter` (JSON + opt-in evidence multipart), `NearbyAdvisor` (20 s poll → spoken advisories) | done; nearby poll verified 200 |
| 9 | SOS: `SosController` (local siren + repeating TTS + red full-screen), triple-tap+confirm exit | wired; not fired on device (noise) |
| 10 | Device bring-up loop (install / screenshot / logcat) | active |

JVM unit tests (`:app:testDebugUnitTest`, 20 passing): `PreviewTransform`,
`FrameFreshnessGate` (all 5 rules), `CapturePacing` + `CaptureLoopGate`,
`SonarMapping`.

Known follow-ups: confirm the `PreviewView` renders the camera image against a
lit scene; ear-check spatial audio / haptic dictionary / tri-lingual TTS; native
review of the HI/TA strings; overlay corner-alignment check with printed markers;
screen-off service-survival check; `ExploreResultCard` visual (spoken result
already works).

## 11. Verification hooks (later testing pass)

- JVM unit tests: `PreviewTransform`, `FrameFreshnessGate`, `adaptiveCaptureDelay`,
  `GuidanceStrings` coverage of every `action`, haptic dictionary completeness,
  spatial-audio pan/pitch math.
- Device checks via ADB: `/health` reachability, session start/analyze round-trip
  latency, overlay corner alignment with printed markers, freshness discard on
  forced stale `captured_at`, volume-key intercept (no OS volume UI), screen-off
  service survival, OCR of a prepared sign, hazard POST visible on the dashboard.
- Never perform blindfolded walking tests; use controlled scenes.
