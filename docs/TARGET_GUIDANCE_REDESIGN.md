# Target Guidance Redesign — Remembered Landmarks + Turn-by-Turn

- Plan version: `target-guidance/2.0.0`
- Raised: 2026-09-04
- Status: **Accepted — backend implementation in progress; native client update pending**
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
- Status: **Proposed — needs D-078 sign-off**

### Problem

`LandmarkMemoryStore.observe()` is fed `detections: list[DetectionResult]` — the
**risk-filtered `CANONICAL_LABELS` set** (19 classes: chair, door, bed, tv,
couch, refrigerator, sink, toilet, bench, desk, bag, suitcase, umbrella, potted
plant, bicycle, motorcycle, car, bus, person). Everything else YOLO11n detects is
discarded in `canonicalize_detections` before it can be remembered.

The things users actually ask an assistant to find — **bottle, cup, bowl, wine
glass, laptop, cell phone, keyboard, mouse, remote, book, clock, vase,
backpack, handbag, tie, scissors, teddy bear, toothbrush, hair drier,
microwave, oven, toaster, dining table** — are all standard COCO classes and are
all currently thrown away. For any of them the memory path is structurally
unavailable and resolution falls to the Moondream2 fallback, whose unreliability
on cluttered real scenes is the reason this redesign exists. Result: "find the
blue bottle" → memory miss → VLM miss → 404, every time.

### D-078 (proposed)

The landmark buffer is populated from the **complete COCO detector output**, not
the risk whitelist. The continuous risk engine and the AR overlay keep the
existing 19-class filtered set unchanged (`HALL_HAZARD_LABELS_V1`, D-053 hold).
One YOLO11n forward pass per frame; two label filterings of its raw output.

### Backend changes

1. **`app/perception/detector.py`**
   - `canonicalize_detections(..., allowed_labels: frozenset[str] | None = CANONICAL_LABELS)`.
     `None` → keep every finite, above-threshold box with its native COCO label
     (still lower-cased, still `LABEL_ALIASES`-normalized). Box normalization,
     clamping, and the `x1<x2 / y1<y2` guard are unchanged.
   - `UltralyticsDetector.detect()` returns the risk set as today **and** exposes
     the full set from the *same* `raw` list. Preferred shape: return a small
     dataclass `DetectionSet(risk: list[DetectionCandidate], all: list[DetectionCandidate])`
     from `detect()`, or add `detect_all()` that reuses a cached `raw` under the
     existing single-worker lock. No second GPU inference.
   - `UnavailableDetector` mirrors whichever shape is chosen.

2. **`app/api/walk.py` `_process_accepted_frame`**
   - Feed `landmark_memories.observe(...)` and the memory-backed re-acquire in
     `TargetGuidanceSessionStore.step(...)` the **full** candidate list
     (mapped to `DetectionResult` the same way the risk list is).
   - `detections` returned in `FrameAnalysisResponse` and everything the risk
     engine / overlay consume stay the **filtered** list. No contract change to
     `FrameAnalysisResponse`.

3. **`app/perception/landmark_memory.py` — resolver fuzziness (`resolve`)**
   - Normalize the query: lower, collapse spaces, drop a leading article and a
     leading colour word (`red|orange|yellow|green|blue|purple|pink|brown|black|
     white|grey|gray|silver|gold`).
   - Match order: exact label → query token ⊇ label token (`"blue bottle"` →
     `bottle`) → label token ⊇ query token → synonym table. Extend the synonym
     table for COCO: `phone↔cell phone`, `mobile↔cell phone`, `laptop↔laptop`,
     `tv↔tv↔television`, `plant↔potted plant`, `sofa↔couch`, `fridge↔refrigerator`,
     `bin↔(no class)`, `glass↔wine glass|cup`, `mug↔cup`, `remote control↔remote`,
     `bottle↔bottle` (covers "water bottle").
   - On multiple matches, most-recently-seen wins (unchanged).

4. **`app/config.py`** — optional `landmark_full_coco: bool = True` kill-switch;
   `landmark_memory_max` may want raising (`24 → 40`) since the candidate stream
   is wider. Keep the TTL.

5. **Not-found phrasing (`app/api/vlm.py`)** — when both memory and VLM miss,
   the 404 `text` should distinguish "not a thing I can recognise" from "I just
   don't see it right now", e.g.:
   `"I can't find a <target> nearby. I can only guide you to things I can recognise."`
   The Android client speaks this verbatim.

### Still out of scope after this amendment

Targets that are **not** COCO classes — *towel, bucket, charger, wallet, keys,
water (as a substance), door handle, light switch* — remain Moondream2-fallback
only, and an honest "I can't find a `<target>`" when the VLM misses. Closing that
tail needs either a wider detector or reliable open-vocab grounding, which is a
separate decision.

### Acceptance delta

- With a real bottle in the walk stream for ≥1 frame in the last 45 s, "find the
  blue bottle" resolves `from MEMORY`, not `VLM`, and guidance proceeds.
- `person` still excluded unless `landmark_allow_person`.
- Walk-loop p95 `total_ms` unchanged (no second inference).
- `FrameAnalysisResponse.detections` still carries only the 19-class set.
