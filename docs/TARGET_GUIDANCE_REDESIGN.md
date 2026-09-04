# Target Guidance Redesign — Remembered Landmarks + Turn-by-Turn

- Plan version: `target-guidance/2.0.0`
- Raised: 2026-09-04
- Status: **Accepted — §1–§11 implemented and green on the backend;
  native client update (§8) pending**
- Supersedes the Ask→Lock→Guide behaviour accepted in D-069/D-070/D-072 (the
  endpoints and telemetry channel stay; the resolver, the tracker, and the
  spoken output change).
- Split: **backend team implements on the main PC** from this spec; the Android
  client changes in §8 land in lockstep and are done in the app repo.

## 1. Why the current feature is being replaced

`POST /api/v1/vlm/locate` runs **one** Moondream2 `detect` on the Ask frame,
`_location_geometry` keeps **the largest returned box**, and the box centre is
turned into a clock-face string (`clock_direction`).

Field-reported failures:

- **Wrong instance.** On a cluttered hall Moondream2 returns several boxes for
  an open-vocabulary target ("towel"); the largest is often not the real one, so
  the guidance confidently points the wrong way. There is no confidence score to
  filter with (D-069: the model exposes none).
- **One shot.** A single frame, a single inference — no correction, no recovery.
- **Clock face is a poor eyes-free modality.** "Eleven o'clock" forces the user
  to map an abstract dial onto their body while walking. Users asked for plain
  "turn right … keep turning … stop, walk forward".
- **Nothing is remembered.** If the thing is not in the exact Ask frame the
  request just fails, even if the assistant saw it clearly two seconds earlier.

Verified during triage: `clock_direction` and the box→centre maths are correct on
clean inputs, and the Android capture orientation is correct (OCR reads fine
through the same path). The defects above are the design, not a coordinate bug.

## 2. New behaviour in one paragraph

As the user walks, the backend keeps a short, rolling memory of the labelled
things the **continuous detector** (YOLO11n, already running every frame) has
seen in roughly the last 45 seconds, each with the compass bearing it was last
seen at. "Find the towel" matches that memory and starts a **turn-by-turn
guidance loop**: the assistant says "turn right", "keep turning", then "you're
facing it, walk forward", correcting itself whenever the towel comes back into
view, and finishing with "you should be right in front of it". If the target was
never seen, one Moondream2 `detect` on the current frame is the fallback; if that
also fails, the assistant says so plainly. The VLM never enters the continuous
loop and no frame is stored (D-018, D-022 unchanged).

## 3. Accepted decisions

| Proposed | Decision | Consequence |
|---|---|---|
| **D-073** | Add a rolling, per-session **landmark memory** populated only from the continuous detector. | New in-process store; TTL-bounded (~45 s), capped (~24 entries), evicted on session end, never written to disk or logs. No new model. Amends nothing; extends D-035's "spatial evidence" set. |
| **D-074** | Replace clock-face target direction with a **turn-by-turn guidance state machine**. `clock_direction` is removed from the contract. | `TargetTrackingTelemetry` gains `bearing_degrees`, `range_hint`, `guidance_step`; `clock_direction` field deleted. `TargetTrackingState` values change to `IDLE, SEEKING, GUIDING, ARRIVED, LOST`. Client + backend land together. |
| **D-075** | The Android client sends the device **heading** (yaw azimuth) with every walk frame; the backend dead-reckons bearing to an out-of-view target from it, snapping to a live detection whenever the target re-enters frame. | New optional `heading_degrees` form field on `/walk/analyze`. Absent → guidance degrades to in-view-only. Drift is corrected on every re-acquisition; pure out-of-view guidance beyond `target_reacquire_timeout_seconds` falls back to "stop and scan slowly". |
| **D-076** | Moondream2 `detect` becomes the **fallback resolver only** — used when the target is not in landmark memory — never the primary path and never in the Walk loop. | `/vlm/locate` resolution order becomes memory → VLM → not-found. Keeps D-018/D-069 intact; removes the VLM from the common case. |
| **D-077** | Relative range is reported only as coarse image-derived bands (`NEAR/MID/FAR/UNKNOWN`), never a distance or time. | Extends D-021. Bands come from normalized box height and lower-edge position; "arrived" is a band + centred + dwell heuristic, not a measurement. |

**Recommendation: accept all five.** D-073 + D-074 are the core; D-075 is what
makes "turn until you're facing it" work when the target is momentarily out of
frame; D-076 keeps the unreliable open-vocab path off the critical route;
D-077 keeps the safety language honest.

Implementation note: the backend temporarily retains `clock_direction` as a
deprecated, non-authoritative compatibility field because the native Android
DTO is maintained separately and was explicitly left untouched in this pass.
No backend speech or guidance decision uses that field. It is removed when the
coordinated Android contract update lands.

## 4. Landmark memory (D-073)

New module `backend/app/perception/landmark_memory.py`.

```
Landmark:
  label: str                 # canonical detector label
  world_bearing_deg: float    # heading_deg + (center_x - 0.5) * hfov, wrapped to [-180,180)
  last_center_x: float        # 0..1, for re-acquire matching and audio pan
  last_box_h: float           # 0..1 normalized, feeds range_hint
  last_box_bottom: float      # 0..1, feeds range_hint
  first_seen_ms / last_seen_ms
  sightings: int
```

`LandmarkMemory` is per `session_id`, created in `start_walk_session`, dropped in
`end_walk_session` and on `LatestTelemetryHub.end_session`.

- **`observe(now_ms, heading_deg | None, detections)`** — called once per
  processed walk frame from `_process_accepted_frame`, after tracking. For each
  detection: `bearing = wrap180(heading_deg + (cx - 0.5) * hfov)` when heading is
  known, else store `world_bearing_deg = None` and only `last_center_x`. Upsert
  by label (nearest existing entry of that label within a small bearing gate is
  updated; otherwise a new entry, evicting the oldest when over
  `landmark_memory_max`). Then drop entries with
  `now_ms - last_seen_ms > landmark_memory_ttl_seconds * 1000`.
- **`resolve(target_name) -> Landmark | None`** — normalize (`lower`, collapse
  spaces, strip a leading article). Match against entry labels by: exact, then
  token-subset (`"blue towel"` → label `"towel"` if `"towel"` is a token), then a
  small synonym table (`sofa↔couch`, `fridge↔refrigerator`, `tv↔television`,
  `plant↔potted plant`, `bin↔… (no COCO class — miss)`). On multiple matches,
  return the most recently seen.

No confidence, no identity, no faces. `person` is retained as a landmark only if
you explicitly allow it in config (`landmark_allow_person`, default `false`) —
guiding a blind user toward a specific person is out of scope.

## 5. Guidance state machine (D-074, D-075, D-077)

New module `backend/app/guidance/target_guidance.py`. One `TargetGuidance` per
session holds the active `guided_target` (a copy of the resolved `Landmark` plus
a running `state`, `last_step`, `last_spoken_ms`, `arrived_since_ms`).

**Per frame** (`step(now_ms, heading_deg, detections, safety_overridden)`):

1. **Safety first (D-071).** `safety_overridden` → return telemetry with
   `speak=false`, `haptic_pattern=NONE`, `guidance_step` frozen, state unchanged,
   any pending arrival/lost announcement held.
2. **Re-acquire.** If a detection matches `guided_target.label` and is on-screen,
   set `target_center`, recompute `world_bearing_deg = wrap180(heading_deg +
   (cx-0.5)*hfov)` (drift correction), refresh `last_seen_ms`, and compute
   `range_hint` from that box (`§ range` below). Clear the "lost" timer.
3. **Bearing.** `bearing = wrap180(guided_target.world_bearing_deg - heading_deg)`
   when both are known; else `None`.
4. **Step selection** (thresholds are config):
   - `bearing is None` and no recent detection for `target_reacquire_timeout_seconds`
     → `state = LOST`, `guidance_step = REACQUIRE`, speech "I've lost it. Stop and
     scan around slowly." (spoken once).
   - `|bearing| > target_turn_threshold_degrees` → `TURN_LEFT` / `TURN_RIGHT`
     ("Turn left." / "Turn right.").
   - `target_face_tolerance_degrees < |bearing| ≤ turn threshold` →
     `KEEP_TURNING` ("Keep turning left/right.").
   - `|bearing| ≤ target_face_tolerance_degrees` and `range_hint != NEAR` →
     `FACE_AND_WALK` ("You're facing it. Walk forward.") → `state = GUIDING`.
   - facing and `range_hint` improved vs last frame → `WALKING` ("Keep going.",
     rate-limited).
   - facing and `range_hint == NEAR` sustained for `target_arrived_dwell_seconds`
     → `ARRIVED` ("You should be right in front of it."), `state = ARRIVED`; next
     frame returns to `IDLE`.
5. **Speech cadence.** Speak only on `guidance_step` change or every
   `target_speech_interval_seconds` (~4 s); `dedupe` by phrase; always
   `QUEUE_ADD`, never a flush. `haptic_pattern` maps from the step:
   `TURN_LEFT/KEEP_TURNING-left → TARGET_LEFT_PULSE`, `TURN_RIGHT/…-right →
   TARGET_RIGHT_PULSE`, `FACE_AND_WALK/WALKING → TARGET_CENTRE_PULSE`,
   `ARRIVED → TARGET_CENTRE_PULSE` (client renders a distinct double-tap),
   `REACQUIRE → NONE`.

**Range bands (D-077):** from the last matched box only.
`NEAR` if `box_h ≥ 0.55` or `box_bottom ≥ 0.9`; `FAR` if `box_h ≤ 0.15`;
`MID` otherwise; `UNKNOWN` if never matched on-screen. No metres, ever.

**Heading maths:** `wrap180(a)` maps to `[-180, 180)`. `hfov` is
`settings.walk_camera_hfov_degrees` (default `67`, the OnePlus main camera). This
is deliberately approximate — it only has to be good enough for "turn right vs
keep turning vs facing it".

## 6. Endpoint changes

### `POST /api/v1/walk/analyze`

Add optional multipart field **`heading_degrees`** — float, the device azimuth at
capture (degrees; any real value, backend wraps). Absent is allowed. Everything
else unchanged. `_process_accepted_frame` passes it to `LandmarkMemory.observe`
and `TargetGuidance.step`.

`FrameAnalysisResponse.target_tracking` (`TargetTrackingTelemetry`) becomes:

```ts
type TargetTrackingState = "IDLE" | "SEEKING" | "GUIDING" | "ARRIVED" | "LOST";
type TargetGuidanceStep =
  | "NONE" | "TURN_LEFT" | "TURN_RIGHT" | "KEEP_TURNING"
  | "FACE_AND_WALK" | "WALKING" | "ARRIVED" | "REACQUIRE";
type TargetRangeHint = "NEAR" | "MID" | "FAR" | "UNKNOWN";

interface TargetTrackingTelemetry {
  tracking_state: TargetTrackingState;
  target_name: string | null;
  guidance_step: TargetGuidanceStep;          // NEW — replaces clock_direction
  bearing_degrees: number | null;             // NEW — signed, - = left, + = right, ~0 = facing
  range_hint: TargetRangeHint;                // NEW
  target_center: NormalizedPoint | null;      // unchanged (live box centre; null when out of view)
  confidence: number | null;                  // unchanged (still null)
  is_safety_overridden: boolean;              // unchanged
  speech: string;                             // unchanged mechanics; now turn-by-turn phrasing
  speak: boolean;                             // unchanged
  haptic_pattern: TargetHapticPattern;        // unchanged enum
  // clock_direction: REMOVED
}
```

`TargetTelemetryEvent` (the `/telemetry` WS) inherits the same change. The WS is
not otherwise touched.

### `POST /api/v1/vlm/locate`

Same request shape. New resolution order:

1. `LandmarkMemory.resolve(target_name)` — hit → seed `guided_target`,
   `tracking_state = GUIDING` if a live detection is already visible this session
   else `SEEKING`; `resolved_from = "MEMORY"`.
2. Miss → one Moondream2 `detect` on the supplied/most-recent frame (unchanged
   VRAM guard, single worker, timeout, immediate unload — and the release fix in
   4c93c48). Found → seed a landmark entry from that box + the frame's heading,
   `resolved_from = "VLM"`.
3. Still miss → `404 NOT_FOUND`, message "I haven't seen a `<target>` recently —
   face it and ask again."

Response: drop `clock_direction`; add `bearing_degrees: number | null`,
`range_hint: TargetRangeHint`, `resolved_from: "MEMORY" | "VLM"`. Keep `text` as
the one-shot spoken confirmation, now phrased as a turn instruction
("The towel is behind you on the right — turn around.") rather than a clock face.

## 7. Config (backend)

Add to `Settings`, all unvalidated engineering defaults in the D-039 tradition:

| Key | Default | Meaning |
|---|---|---|
| `walk_camera_hfov_degrees` | `67.0` | Horizontal FOV for bearing maths |
| `landmark_memory_ttl_seconds` | `45` | Drop landmarks unseen this long |
| `landmark_memory_max` | `24` | Hard cap; oldest evicted |
| `landmark_allow_person` | `false` | Never guide to a person unless enabled |
| `target_turn_threshold_degrees` | `25.0` | Above → "turn"; below → "keep turning" |
| `target_face_tolerance_degrees` | `10.0` | Within → "facing it" |
| `target_reacquire_timeout_seconds` | `8.0` | No sighting this long → `LOST` |
| `target_arrived_dwell_seconds` | `2.0` | NEAR + centred this long → `ARRIVED` |
| `target_speech_interval_seconds` | `4.0` | Min gap between unchanged-step lines |

Amendment A adds four more keys — see §11.7.

## 8. Android client changes (pending coordinated client pass)

The backend pass does not modify `apps/android`. Until this section lands, the
backend emits the deprecated optional `clock_direction` compatibility field in
addition to the new authoritative fields.

- **`GyroSteering`** — expose `currentHeadingDegrees(): Float` (the azimuth it
  already reads, `Math.toDegrees(currentYaw)`, normalized `0..360`).
- **`WalkController.analyze()` / `DrishtiApi.analyze`** — add
  `@Part("heading_degrees")` from `gyro.currentHeadingDegrees()` at capture time.
- **`net/Dto.kt`**
  - `TargetTrackingState` → `{ IDLE, SEEKING, GUIDING, ARRIVED, LOST }`.
  - New enums `TargetGuidanceStep`, `TargetRangeHint`.
  - `TargetTrackingTelemetry`: remove `clockDirection`; add `guidanceStep`,
    `bearingDegrees: Double?`, `rangeHint`.
  - `VlmLocateResponse`: remove `clockDirection`; add `bearingDegrees: Double?`,
    `rangeHint`, `resolvedFrom: String?`.
- **`WalkController.applyTargetTracking`** — unchanged mechanics (speak `speech`
  on `speak`, haptic from `hapticPattern`, pan from `targetCenter`). Add: on
  `ARRIVED` play a distinct double-tap and clear the pan; on `LOST` clear the pan.
- **`HapticEngine`** — add `TargetHapticPattern` handling for an `ARRIVED`
  double-tap (or a dedicated `playTargetArrived()`), keep the L/C/R rhythms.
- **`TargetLocator`** — still speaks `response.text` verbatim; no clock parsing.
- Remove every `clock` / `clockDirection` reference; `state_describing` banner
  and the Ask routing (`extractLocateTarget`) are unchanged.

Because kotlinx.serialization is configured with `ignoreUnknownKeys` +
`coerceInputValues` and every new field is optional, an interim mismatch
degrades safely rather than crashing — but the two sides should still merge in
one coordinated change.

## 9. What this explicitly does NOT do

- **No map, no localisation, no SLAM.** Guidance is relative to where the user is
  standing and which way they are facing *now*; it cannot walk them across a
  building to a room they last saw ten minutes ago.
- **No memory of things never seen.** "Prior memory" means the last ~45 s of the
  continuous detector's field of view (or one VLM fallback on the current frame).
- **No metric distance or "safe to proceed".** Range is three coarse bands from
  image cues; "arrived" is a heuristic. Safety guidance always preempts (D-071).
- **No new perception model.** Landmark memory rides entirely on the YOLO11n
  detector already in the loop.
- **Gyro dead-reckoning drifts.** Reliable while the target is periodically
  re-seen; past `target_reacquire_timeout_seconds` out of view it says "stop and
  scan", it does not pretend to still know the bearing.

## 10. Acceptance criteria

- Walk past a chair, look away, say "find the chair" within 45 s → assistant says
  "turn left/right", then "you're facing it, walk forward" as the user rotates
  back, then "you should be right in front of it" on approach. No clock numbers.
- Same, but the chair was **never** in view → one VLM `detect`; if it is in the
  current frame, guidance proceeds; if not, "I haven't seen a chair recently."
- While guiding, a real obstacle triggers `STOP` → all target speech/haptics go
  silent that frame, `is_safety_overridden=true`; the turn cue resumes after.
- Turn a full 180° away from the target with it out of frame → within
  `target_reacquire_timeout_seconds` the assistant switches to "stop and scan
  slowly" rather than giving a stale bearing.
- `heading_degrees` omitted (older client) → guidance still works whenever the
  target is on-screen; degrades gracefully when it is not.
- No frame written to disk; landmark memory empty after `end` for a session.
- Walk-loop p95 `total_ms` unchanged (landmark `observe` is O(detections)).

---

## 11. Amendment A — landmark memory must see the full COCO label set

- Amendment version: `target-guidance/2.1.0`
- Raised: 2026-09-04 after `target_name=blue bottle` returned 404 in the field
- Revised: 2026-09-04 after a backend code audit against `main` (6a39561). The
  audit corrected three factual errors and one infeasible instruction in the
  first draft; §11.11 lists what changed and why.
- Status: **Accepted and implemented** — D-078 is recorded in
  `docs/DECISIONS.md`. Backend suite: 189 passed, 1 skipped (the skip is the
  external controlled-fixture gate, unchanged).
- Baseline: §1–§10 (`target-guidance/2.0.0`) were implemented and green on
  `main` (6a39561, 175 backend tests) before this amendment landed. §8 (the
  Android client pass) remains the only outstanding work in this document.

### 11.1 Problem

`LandmarkMemoryStore.observe()` is fed the `detections` list built in
`_process_accepted_frame` from `RiskAssessment`s — i.e. the **risk-filtered
`CANONICAL_LABELS` set** (19 classes: chair, door, bed, tv, couch, refrigerator,
sink, toilet, bench, desk, bag, suitcase, umbrella, potted plant, bicycle,
motorcycle, car, bus, person). Everything else YOLO11n detects is discarded in
`canonicalize_detections` before it can be remembered.

The things users actually ask an assistant to find — **bottle, cup, bowl, wine
glass, laptop, cell phone, keyboard, mouse, remote, book, clock, vase, tie,
scissors, teddy bear, toothbrush, hair drier, microwave, oven, toaster** — are
all standard COCO classes and are all currently thrown away. For any of them the
memory path is structurally unavailable and resolution falls to the Moondream2
fallback, whose unreliability on cluttered real scenes is the reason this
redesign exists. Result: "find the blue bottle" → memory miss → VLM miss → 404,
every time.

**Correction to the first draft.** `backpack`, `handbag`, and `dining table` are
*not* discarded — `LABEL_ALIASES` maps them to `bag`, `bag`, and `desk`, so they
are remembered under a coarser label. They fail for a different reason:
`labels_match("backpack", "bag")` is `False` (no shared token, no synonym
entry), so "find my backpack" misses a landmark that *is* in memory. §11.6
fixes that separately from the whitelist widening.

### 11.2 D-078 (proposed)

The landmark buffer is populated from the **complete COCO detector output**, not
the risk whitelist. The continuous risk engine, the tracker, the spatial stage,
and the AR overlay keep the existing 19-class filtered set unchanged
(`HALL_HAZARD_LABELS_V1`; D-053 and D-066 hold). One YOLO11n forward pass per
frame; two label filterings of its raw output.

A landmark becomes **resolvable** only after it clears a confidence floor and
has been seen in at least two processed frames (§11.5). At the default 2 fps
capture cadence that is ~1 s of visibility, so an object held in view for the
2–4 s a demo takes clears the gate with 3–4× margin, while a single-frame
detector flicker does not.

### 11.3 Backend changes — detector (`app/perception/detector.py`)

1. `canonicalize_detections(..., allowed_labels: frozenset[str] | None = CANONICAL_LABELS, apply_aliases: bool = True)`.
   - `allowed_labels=None` → keep every finite, above-threshold box with its
     **native COCO label**, lower-cased. Box normalization, clamping, and the
     `x1<x2 / y1<y2` guard are unchanged.
   - **`LABEL_ALIASES` must NOT be applied to the full set.** Aliasing collapses
     `backpack`/`handbag` into `bag` and `dining table`/`table` into `desk`,
     which throws away exactly the word the user is going to say. The full set
     keeps `backpack`, `handbag`, `dining table` verbatim; the risk set keeps its
     current aliased behaviour untouched.
2. `UltralyticsDetector.detect()` returns
   `DetectionSet(risk: list[DetectionCandidate], all: list[DetectionCandidate])`
   — both filterings of the **same** `raw` list, produced inside the existing
   single-worker lock. One return value, no cached `raw`, no second GPU
   inference.
   - The `detect_all()` alternative from the first draft is rejected: it needs
     `raw` cached across two calls behind one lock, which is a data race under
     latest-frame-wins scheduling, for no benefit.
3. Mirror the shape in the `Detector` Protocol and in `UnavailableDetector`.
4. `load_detector()`'s warm-up call (`detector.detect(np.zeros(...))`) still
   works unchanged — it discards the return value.

### 11.4 Backend changes — the observation path

**This is where the first draft was wrong.** It said to feed memory and guidance
"the full candidate list (mapped to `DetectionResult` the same way the risk list
is)". That is not achievable. `DetectionResult` is the wire-contract model and
requires `track_id`, `direction`, `proximity`, `proximity_score`,
`approach_state`, `risk_score`, `risk_level`, and `display_color` — all produced
by the tracker → `analyze_corridors` → `score_tracks` chain, which is
deliberately whitelist-scoped. Building them for 80 classes would either run the
whole risk pipeline over the full stream (a real behaviour and latency change to
safety code) or fabricate risk fields for objects that were never risk-assessed
— the thing D-069 refused to do for `confidence`.

Both consumers only ever read `label`, `confidence`, and the box:

- `LandmarkMemoryStore.observe()` reads `detection.label` and `detection.bbox.*`.
- `TargetGuidanceSessionStore.step()` → `_latest_match()` reads `item.label` and
  `item.confidence`, then `match.bbox.*`.

So:

1. **`app/perception/landmark_memory.py`** — `observe(...)` takes
   `list[DetectionCandidate]` (flat `x1/y1/x2/y2`) instead of
   `list[DetectionResult]`.
2. **`app/guidance/target_guidance.py`** — `step(...)` and `_latest_match(...)`
   take the same type. `target_guidance` already imports from
   `app.perception.landmark_memory`, so this adds no new module-dependency
   direction. (If the `perception`/`guidance` separation rule in `AGENTS.md` is
   read strictly, declare a small `Observation` dataclass in
   `landmark_memory.py` and map in `walk.py` instead — same result, one extra
   allocation per detection per frame.)
3. **`app/api/walk.py` `_process_accepted_frame`** — pass the detector's full
   list straight to `landmark_memories.observe(...)` and
   `target_sessions.step(...)`, **before and independent of** tracking, spatial,
   and risk. Pass the risk list to `tracking_sessions.update(...)` as today.
4. `detections` in `FrameAnalysisResponse`, the overlay, and everything the risk
   engine consumes stay the **filtered** list built from `RiskAssessment`s.
   **No wire-contract change.** `docs/API_CONTRACTS.md` needs no edit.

This is strictly cheaper than the first draft as well as correct: the full
stream skips the tracker, corridor, and scoring stages entirely.

### 11.5 Backend changes — memory quality gate (new)

Widening from 19 to 80 classes at `detector_confidence_threshold = 0.35` puts
the long tail of weak boxes into memory. `Landmark` carries no confidence and
`resolve()` returns the most-recently-seen match unconditionally, so a spurious
0.36 "bottle" would produce confident turn-by-turn guidance toward nothing. The
19-class whitelist was implicitly suppressing this; removing it removes the
suppression. Add:

1. `observe()` skips any candidate below `landmark_min_confidence`. Filtering at
   observe time keeps `Landmark` unchanged — no confidence field, nothing new to
   expose or persist.
2. `resolve()` ignores entries with `sightings < landmark_min_sightings`. If
   every match is below the gate, return `None` and fall through to the VLM —
   the safe failure.
3. **Heading-transition fix.** In `_remember`, when no bearing-gated candidate is
   found but a same-label entry with `world_bearing_deg is None` exists, adopt
   that entry (carrying its `sightings`) rather than creating a duplicate.
   Without this, the first frame that carries `heading_degrees` after a
   heading-less start resets the object to `sightings = 1`.

4. **Re-acquisition floor (added during implementation).** `step()`'s
   `_latest_match` had no confidence filter — harmless against the 19-class set,
   but it now sees the detector's whole low-confidence tail, so a weak false
   positive elsewhere in frame could pull guidance off the real target. It
   applies the same `landmark_min_confidence` floor. Covered by
   `test_target_tracking.py`.

`person` remains excluded unless `landmark_allow_person`.

**Closed in this pass.** The VLM path calls
`landmark_memories.remember(label=target_name, ...)` directly, which bypassed the
`person` filter that `observe()` applies, so `/vlm/locate?target_name=person`
could seed a landmark and start guidance toward a person, contrary to §4.
`/locate` now refuses a person target at the door with `404 NOT_FOUND` and
"I can't guide you to a person.", before either resolver runs.

`remember()` deliberately still bypasses the *sightings* gate: it seeds a new
entry at `landmark_min_sightings` so a VLM-confirmed box is resolvable
immediately. A confirmed detection is not detector flicker, and without this a
second ask for the same target would pay for the VLM again, contrary to D-076.

### 11.6 Backend changes — resolver fuzziness (`resolve` / `labels_match`)

Current behaviour already covers more than the first draft assumed:
`labels_match` is symmetric (`left ⊆ right or right ⊆ left`), so `"blue bottle"`
→ `bottle` and `"phone"` → `cell phone` already match by token subset. What is
actually missing:

1. **Leading-noise stripping** — drop leading articles, possessives
   (`my|our|your|his|her|their|some|that|this`), and colour words
   (`red|orange|yellow|green|blue|purple|pink|brown|black|white|grey|gray|
   silver|gold`) while more than one token remains. **Guard: never strip the
   last token.** `orange` is both a colour and a COCO class; stripping it from a
   bare `"orange"` query would leave an empty target that matches nothing — or,
   under the subset rule, risks matching everything.

   *Added during implementation:* the possessive class was not in the written
   plan and is required. Synonyms are looked up on the whole normalized phrase,
   so `"my phone"` missed `cell phone` on both the synonym table and the
   token-subset rule (`{my, phone}` is not a subset of `{cell, phone}`). The
   same defect broke `"my handbag"` → `bag`. Covered by
   `test_landmark_memory.py`.
2. **Synonym table for COCO** — add `bag ↔ backpack|handbag` and
   `desk ↔ dining table`, so the *aliased* risk-set labels stay reachable by the
   user's own word (§11.1), plus `mobile ↔ cell phone`, `glass ↔ wine glass`,
   `mug ↔ cup`, `remote control ↔ remote`, `television ↔ tv`,
   `fridge ↔ refrigerator`, `sofa ↔ couch`, `plant ↔ potted plant`. Words that
   map to no COCO class (`bin`, `towel`) are simply absent — a miss, not a table
   entry.
3. Most-recently-seen wins among surviving matches (unchanged), now applied
   after the §11.5 sightings gate.

### 11.7 Backend changes — config

`app/config.py`:

| Key | Default | Meaning |
|---|---|---|
| `landmark_full_coco` | `true` | Kill-switch back to the 19-class memory |
| `landmark_min_confidence` | `0.45` | Floor for entering landmark memory |
| `landmark_min_sightings` | `2` | Frames before an entry is resolvable (~1 s @ 2 fps) |
| `landmark_memory_max` | `24` → `40` | Wider candidate stream; the existing `le=128` bound already allows it |

TTL stays at 45 s. Note the churn tradeoff: `_trim` evicts by pure recency, so a
cluttered scene can push out the older landmark the user is about to ask for. 40
is a judgement call in the D-039 tradition, not a measured value.

### 11.8 Not-found phrasing (`app/api/vlm.py`)

When both memory and VLM miss, the 404 message should distinguish "not a thing I
can recognise" from "I just don't see it right now":

> `"I can't find a <target> nearby. I can only guide you to things I can recognise."`

**Correction to the first draft:** the Android client does *not* speak this
verbatim. `TargetLocator.locateOnce` discards the backend message on `NOT_FOUND`
and speaks the local `R.string.locate_not_found` instead. This change is
therefore backend-only and inaudible until the coordinated §8 Android pass;
adopting the backend wording there (`ApiResult.Failure.message` is already
available at that call site) is deferred to that pass, not scoped here.

### 11.9 Tests and documents to update

Not optional — `AGENTS.md` requires tests in the same pass as the behaviour, and
decisions recorded before implementation.

- `backend/tests/conftest.py::ReadyTestDetector` — return a `DetectionSet`. Give
  it an `all_detections` attribute defaulting to `detections` so the seven
  integration tests that assign `detector.detections = [...]` keep working
  unchanged.
- `backend/tests/unit/test_detector.py` — add cases for `allowed_labels=None`
  (native labels kept, aliases *not* applied, threshold still enforced) beside
  the existing whitelist cases.
- New unit coverage in `test_target_tracking.py`, or a new
  `test_landmark_memory.py`: confidence floor rejects a 0.36 box; the sightings
  gate blocks a one-frame object and admits a two-frame one; the
  heading-transition case preserves `sightings`; a bare `"orange"` still
  resolves to the fruit; `"blue bottle"` → `bottle`; `"backpack"` → the aliased
  `bag` landmark; `person` still excluded.
- Integration: a walk frame carrying a `bottle` for two frames, then
  `/vlm/locate?target_name=blue bottle` → `resolved_from == "MEMORY"` with the
  VLM engine never invoked; and `FrameAnalysisResponse.detections` in the same
  test still containing only whitelist labels.
- `docs/DECISIONS.md` — record D-078 (amends D-066; D-053 holds) with the
  confidence and sightings gates as part of the decision, since they are what
  keeps the wider stream honest.
- `docs/API_CONTRACTS.md` — no change required; say so explicitly in the PR so
  the reviewer does not go looking.

### 11.10 Still out of scope after this amendment

Targets that are **not** COCO classes — *towel, bucket, charger, wallet, keys,
water (as a substance), door handle, light switch* — remain Moondream2-fallback
only, and an honest "I can't find a `<target>`" when the VLM misses. Closing that
tail needs either a wider detector or reliable open-vocab grounding, which is a
separate decision.

### 11.11 Acceptance delta

- With a real bottle in the walk stream for ≥2 processed frames in the last 45 s,
  "find the blue bottle" resolves `from MEMORY`, not `VLM`, and guidance
  proceeds.
- A label that appears in exactly one frame does **not** become a guidance
  target; the request falls through to the VLM.
- "find my backpack" resolves against the aliased `bag` landmark.
- A bare `"orange"` query still resolves to the COCO `orange` class.
- `person` still excluded unless `landmark_allow_person`.
- Walk-loop p95 `total_ms` unchanged — no second inference, and the full stream
  skips tracking, spatial, and risk.
- `FrameAnalysisResponse.detections` still carries only the 19-class set, and
  overlay/risk behaviour is unchanged from `main` for the same input.

### 11.12 What the audit changed in the first draft

| First draft said | Reality on `main` | Now says |
|---|---|---|
| backpack, handbag, dining table are thrown away | `LABEL_ALIASES` keeps them as `bag`/`desk`; they fail because `labels_match` cannot connect the user's word to the alias | §11.1 correction + synonym entries in §11.6 |
| Map the full candidate list to `DetectionResult` | `DetectionResult` needs tracker/spatial/risk fields that only exist for whitelist labels | §11.4 — memory and guidance take `DetectionCandidate`; only label, confidence, box are read |
| `allowed_labels=None` keeps `LABEL_ALIASES` normalization | Aliasing is what destroys the user's word | §11.3 — aliases off for the full set |
| The Android client speaks the 404 text verbatim | `TargetLocator` substitutes a local string and drops the backend message | §11.8 — backend-only; client change deferred to §8 |
| (silent) | Widening to 80 classes at conf 0.35 removes the whitelist's implicit junk suppression | §11.5 — confidence floor + sightings gate |
| (silent) | Heading-transition creates a duplicate entry and resets `sightings` | §11.5.3 |
| (silent) | The VLM `remember()` path bypasses the `person` filter | §11.5, flagged for a scope call |
| (silent) | No test, DECISIONS, or contract-note plan | §11.9 |
