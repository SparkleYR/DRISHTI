# DRISHTI Walk Mode Accuracy Fix Plan

- Plan version: `walk-accuracy/1.0.0`
- Raised: 2026-09-04
- Status: **Proposed — requires decision sign-off before implementation**
- Supersedes nothing; amends the surface semantics accepted in D-036 and the
  frozen label sets in D-032 / D-053.

## 1. Why this document exists

Walk Mode gives wrong guidance indoors in four reproducible ways. This document
records the measured cause, the proposed fix, and the split of work across the
two machines involved, because **the backend and ML stack run on a different
system from the Android client**.

| System | Owns | Work in this plan |
|---|---|---|
| Backend laptop (`10.64.202.200:8000`, RTX 4060) | FastAPI backend, YOLO11n, SegFormer, Moondream2, SQLite, model weights | Workstream A (§6) |
| Android dev box (this repo checkout) | `apps/android/` Kotlin client, Gradle, adb to the OnePlus | Workstream B (§7) |

Both machines share this git repository. Everything in Workstream A is confined
to `backend/`, `models/` and `docs/`; everything in Workstream B is confined to
`apps/android/`. They can proceed in parallel and only meet at §8.

## 2. Reported symptoms

Four screenshots from a live indoor walk on 2026-09-03:

| # | What the camera saw | What DRISHTI said | Correct behaviour |
|---|---|---|---|
| 1 | Long clear corridor, open floor ahead | `PAUSED` — "Path ahead blocked, direction unclear" | `CLEAR`, safe corridor drawn |
| 2 | Closed door ~1.5 m ahead, wall to the left | `LEFT` — "Path ahead blocked, side is clearer" | `STOP` or `PAUSE_UNCLEAR`; never steer into the wall |
| 3 | Room corner, wardrobe left, door right | `STOP` — "Path blocked on every side" | `PAUSE_UNCLEAR`; short floor still visible |
| 4 | Blank painted wall filling the frame | `PAUSED` — "Walking surface is uncertain" | `STOP` — "Wall or dead end ahead" |

## 3. Measured evidence

The four frames were replayed through the live backend with `tools/probe_walk.sh`
(committed with this plan). Reproduce with:

```bash
DRISHTI_BASE=http://10.64.202.200:8000 tools/probe_walk.sh path/to/frames/*.jpg
```

Results (2026-09-04, backend reporting `detector READY`, `segmentation READY`,
`depth DEGRADED`):

| Frame | Corridor costs L / C / R | Detections | Surfaces returned by the segmenter |
|---|---|---|---|
| Corner (23:30:19) | 0.475 / **0.444** / 0.473 | **0** | `ROAD` conf 0.93 spanning the whole frame |
| Door ahead (23:30:41) | 0.662 / 0.706 / 0.635 | **0** | `ROAD` 0.92 (y 0.63→1.0), `NON_WALKABLE` 0.80 |
| **Blank wall (23:32:29)** | 0.452 / **0.456** / 0.452 | **0** | **`ROAD` conf 0.96 over the entire frame** + a 5 % `WALKABLE` sliver |
| Clear corridor (00:10:28) | 0.638 / 0.670 / 0.670 | **0** | `ROAD` 0.93 whole frame, `NON_WALKABLE` 0.85 |

Two facts dominate everything else:

- **`safe_polygons` was empty on every single frame.** Green is currently
  unreachable indoors.
- **A blank wall 40 cm from the lens and an open corridor produce the same
  signature**: `ROAD` at ≥0.93, zero detections, corridor costs within 0.02 of
  each other.

## 4. Root cause analysis

### RC-1 — The segmentation model is trained for the wrong world

`models/segmentation/segformer-b0-cityscapes` is SegFormer-B0 fine-tuned on
**Cityscapes**: 19 outdoor street classes (`road`, `sidewalk`, `building`,
`wall`, `car`, …). There is no `floor`, `door`, `ceiling` or `stairs` class.

Indoors the model is fully out of distribution. Measured behaviour: it labels a
tiled hall floor **`road` at 0.93–0.96 confidence**, and it labels a **flat
painted wall `road` at 0.96 confidence** as well. It is confidently wrong, which
is worse than being uncertain — the confidence gate in `_semantic_label_ratio`
cannot filter it out.

D-053 re-scoped the product to an indoor campus hall, but the surface semantics
accepted in D-036 (`sidewalk`→`WALKABLE`, `road`→`ROAD`) were never revisited.

### RC-2 — The surface→cost mapping then converts that error into bad guidance

In `backend/app/spatial/corridor.py`:

```python
surface_cost = min(1.0, ratios[NON_WALKABLE]
                        + 0.45 * ratios[ROAD]
                        + 0.15 * ratios[UNKNOWN])
```

A clean indoor floor is ~100 % `ROAD`, so `surface_cost ≈ 0.45`, which is
**exactly** `risk_centre_block_threshold = 0.45`. A clear floor therefore sits
precisely on the blocked/not-blocked boundary, and per-frame segmentation noise
flips it. That is the `STOP` / `LEFT` / `PAUSE` flapping in frames 2 and 3.

Two more consequences from the same file:

- `uncertain_choices` fires when `UNKNOWN + ROAD ≥ 0.5`. A pure floor is
  `ROAD ≈ 1.0`, so **every indoor corridor is permanently "uncertain"** →
  `CENTRE_SURFACE_UNCERTAIN` → `PAUSE_UNCLEAR`. That is frames 1 and 4.
- `walkable_choices` requires `ratios[WALKABLE] ≥ 0.25`, and `WALKABLE` is
  sourced only from Cityscapes `sidewalk`. Indoors this is never satisfied, so
  **no safe polygon can ever be produced** — confirmed by the measurements.

### RC-3 — Wall and dead-end detection is dead code indoors

`corridor.wall_dead_end` requires confident SegFormer `wall` pixels above
threshold in all three corridors. The measured wall frame returned **zero**
`wall` pixels — the wall was classified `road`. `WALL_OR_DEAD_END_AHEAD` (D-054,
`HALL_HAZARD_LABELS_V1.md`) therefore cannot fire in the environment it was
written for. That is frame 4 exactly.

### RC-4 — The detector whitelist removes the only other evidence source

`CANONICAL_LABELS` in `backend/app/perception/detector.py` admits nine classes:
`person, chair, bag, desk, bicycle, motorcycle, car, bus, bench`. YOLO11n's other
71 COCO classes — `door`, `suitcase`, `umbrella`, `potted plant`, `couch`,
`refrigerator`, `tv` — are discarded before they reach the risk engine.

Measured: **0 detections across all six indoor frames.** With no objects and a
mis-trained segmenter, corridor cost is derived entirely from a wrong signal.
This is also why no bounding boxes appear on the phone screen.

### RC-5 — No depth, so "wall" and "open" are formally indistinguishable

`models.depth` has reported `DEGRADED` since Phase 3; monocular depth was never
implemented and `degraded_modules` always contains `depth`. The geometric
fallback in `spatial/proximity.py` only produces evidence from **detection
bounding boxes**. With zero detections there is no proximity evidence at all.

Nothing in the current pipeline can distinguish a wall at arm's length from a
20 m open corridor. This is the deepest gap and it is not fixable by tuning.

### RC-6 — Sideways guidance is emitted from noise

`_clearer_side` returns `LEFT`/`RIGHT` on a cost advantage of `decision_margin
= 0.10`. Measured left-vs-right spreads on real frames were 0.02–0.07, i.e.
comparable to frame-to-frame segmentation noise. In frame 2 that noise was
enough to tell a blind user to step **into a wall**.

This violates the project's own safety rule in `DECISIONS.md` §3: *"When evidence
is weak or alternatives are unclear, prefer `STOP` or `PAUSE_UNCLEAR` over
precise movement advice."*

## 5. Decisions required before implementation

These amend accepted decisions and need explicit approval per `DECISIONS.md` §1.
Proposed IDs continue the existing sequence.

| Proposed | Decision | Rationale | Consequence if accepted |
|---|---|---|---|
| **D-063** | Replace the Cityscapes segmenter with SegFormer-B0 fine-tuned on **ADE20K** for the indoor hall scope. | ADE20K's 150 classes include `floor`, `wall`, `ceiling`, `door`, `stairs`, `stairway`, `cabinet`, `table`, `chair` — the vocabulary D-053 actually needs. Same model family, same loader, comparable latency. | Amends D-034 and D-036. New dev-time weight download on the backend laptop. Non-commercial research terms carry over and still require review before any distribution. |
| **D-064** | Re-map surface semantics: floor-like classes become `WALKABLE`; `ROAD` is reserved for genuine outdoor roadway and stops contributing a 0.45 blocking cost indoors; `UNKNOWN` no longer forces a corridor "uncertain" on its own. | RC-2. The current mapping makes "clear" unreachable and "uncertain" unavoidable indoors. | Amends D-036. No wire-format change: `SurfaceKind` keeps its four values. |
| **D-065** | Add **free-space geometry** derived from the floor mask as a first-class evidence source, expressed only as a relative extent in [0,1]. | RC-5. Restores the ability to distinguish a near wall from an open corridor without adding a depth model to the 0.5 s loop. | Extends D-021's relative-only rule to a new signal. Never expressed in metres. `depth` stays `DEGRADED`; a real depth model remains a separate future decision. |
| **D-066** | Expand the canonical detector label set with indoor classes and give each a severity weight. | RC-4. Zero detections indoors leaves the risk engine blind and the overlay empty. | Amends D-032 and the Phase 8 scope in D-053 / `HALL_HAZARD_LABELS_V1.md`. |
| **D-067** | Require positive evidence and multi-frame persistence before any `MOVE_LEFT` / `MOVE_RIGHT`; otherwise emit `PAUSE_UNCLEAR`. | RC-6 and `DECISIONS.md` §3. | More pauses, materially fewer wrong turns. Amends the D-039 decision margin. |

**Recommendation: accept all five.** D-063 and D-064 together fix symptoms 1, 2
and 3 at the source; D-065 is the only proposal that fixes symptom 4; D-066
restores object evidence and the on-screen boxes; D-067 closes the safety hole
that sent a user toward a wall.

If only one can be taken, take **D-063 + D-064** — but note that symptom 4 (the
wall) will remain unfixed, because a wall and a floor are the same class to the
Cityscapes model and to any threshold placed on it.

## 6. Workstream A — backend and ML (backend laptop)

All paths relative to the repository root. Nothing here touches `apps/android/`.

### A1. Obtain the ADE20K weights (dev-time only)

Target: `models/segmentation/segformer-b0-ade20k/` containing `config.json`,
`preprocessor_config.json` and the weight file.

- Upstream: `nvidia/segformer-b0-finetuned-ade-512-512`.
- Download only at development time, as with every other model. Runtime keeps
  `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` and `local_files_only=True`.
- `.gitignore` already excludes `models/**/*.bin` and `models/**/*.safetensors`;
  add a `MODEL_CARD.md` beside the weights as the existing Cityscapes directory
  does.
- Keep `segformer-b0-cityscapes/` in place until the ADE20K path is validated.

> **Verify the label map from the downloaded `config.json`, not from this
> document.** Read `id2label` directly. ADE20K label strings are comma-separated
> synonym lists (`"floor, flooring"`, `"door, double door"`), so the existing
> exact-match logic (`label == "sidewalk"`) will silently match nothing. Matching
> must split on `,` and compare the trimmed tokens.

### A2. `backend/app/perception/segmenter.py`

- `load_segmenter` currently requires `pytorch_model.bin` by name. Accept
  `model.safetensors` as well — the ADE20K checkpoint ships as safetensors.
- Point `settings.segmentation_model_path` at the new directory (§A6).
- Update the `detail` string; it is surfaced verbatim in `/health` and should say
  which dataset is loaded, so `/health` never claims the wrong world again.
- The rest of `SegFormerSegmenter` is dataset-agnostic and needs no change.

### A3. `backend/app/spatial/surfaces.py` — surface semantics (D-064)

Replace the single `NON_WALKABLE_LABELS` frozenset and the `semantic_kind_map`
if-chain with an explicit, dataset-aware mapping:

- `WALKABLE` — `floor`, `rug`/`carpet`, `path`, plus outdoor `sidewalk`/`pavement`.
- `ROAD` — `road`/`route` only. Keep it distinct so outdoor behaviour is
  unchanged, but stop treating it as a partial blocker for the indoor scope.
- `NON_WALKABLE` — `wall`, `building`, `ceiling`, `door`, `windowpane`,
  `cabinet`, `wardrobe`, `column`/`pillar`, `table`, `desk`, `chair`, `sofa`,
  `shelf`, `bookcase`, `railing`, `bannister`, `fence`, `pole`, `person`, and
  every vehicle class.
- `UNKNOWN` — everything else.

Add a separate **hazard-surface** set — `stairs`, `stairway`, `step`,
`escalator` — mapped to `NON_WALKABLE` for cost purposes but tracked separately
so §A5 can raise a dedicated reason code. Descending stairs is a fall risk for
the target user and currently has no handling anywhere in the pipeline.

Matching must be token-based (see the warning in §A1). Keep the mapping in one
module-level table so the Cityscapes and ADE20K vocabularies can coexist.

### A4. `backend/app/spatial/corridor.py` — cost, uncertainty and free space

**Cost (D-064).** Make the `ROAD` and `UNKNOWN` coefficients configurable rather
than the literals `0.45` and `0.15`, and set the indoor defaults so that a
corridor of clean floor scores near zero. Today a clear floor scores exactly the
block threshold; that must become structurally impossible.

**Walkability (D-064).** `walkable_choices` should key off the `WALKABLE` ratio
under the new mapping. With a real `floor` class the existing `≥ 0.25` gate
becomes meaningful; re-measure before changing the constant.

**Uncertainty (D-064).** `uncertain_choices` must no longer be driven by
`ROAD + UNKNOWN ≥ 0.5`. A corridor is uncertain when it has neither positive
walkable evidence nor positive blocking evidence — i.e. genuinely low
information — not merely because the class is one the old vocabulary lacked.

**Free space (D-065).** Add a per-corridor `floor_extent ∈ [0,1]`:

1. Build the corridor mask and the `WALKABLE` mask.
2. For each pixel column inside the corridor, starting at the corridor's bottom
   edge, measure the contiguous run of walkable pixels upward.
3. `column_extent = run_length / corridor_column_height`.
4. `floor_extent = median(column_extent)` across the corridor's columns.

The median makes it robust to a single bag or chair leg. The value is a
proportion of the visible corridor, never a distance — this is what keeps D-021
intact. Return `CorridorCosts`-shaped `floor_extents` alongside the existing
`wall_ratios`.

### A5. `backend/app/risk/rules.py` — decision logic

Ordering, highest precedence first:

1. **Critical approaching vehicle** — unchanged.
2. **Wall / dead end (D-065)** — replace the pure wall-ratio test. Fire
   `WALL_OR_DEAD_END_AHEAD` when the centre `floor_extent` is below
   `freespace_dead_end_max` **and** both sides are below their own threshold,
   with a confident `wall` ratio in the centre as corroboration rather than as
   the sole trigger. This is what makes symptom 4 work.
3. **Stairs / level change (new)** — emit a new reason code
   `STAIRS_OR_LEVEL_CHANGE_AHEAD` at `STOP` when hazard-surface pixels occupy a
   meaningful share of the centre corridor. Reason codes are free-form strings on
   the wire and the Android client already has an `else` fallback, so this is
   **not** a breaking contract change.
4. **All corridors blocked** — unchanged rule, but now fed correct costs.
5. **Centre blocked (D-067)** — emit `MOVE_LEFT` / `MOVE_RIGHT` only when *all*
   hold for the target corridor:
   - `floor_extent ≥ direction_min_free_extent`,
   - positive `WALKABLE` ratio above the walkable gate,
   - `wall_ratio` below a small ceiling,
   - cost advantage `≥ decision_margin`, raised from 0.10,
   - and the same side has been proposed for `alert_persistence_frames`
     consecutive frames.

   Otherwise `PAUSE_UNCLEAR` with `CENTRE_BLOCKED_DIRECTION_UNCLEAR`.
6. **Centre surface uncertain** — unchanged rule, now reachable only when the
   evidence really is thin.

### A6. `backend/app/config.py`

Add, with conservative defaults, and document each as an unvalidated engineering
default in the D-039 tradition:

- `segmentation_model_path` → the ADE20K directory.
- `segmentation_label_set: Literal["ADE20K", "CITYSCAPES"]` so the mapping table
  is selected explicitly rather than inferred.
- `surface_cost_road_weight`, `surface_cost_unknown_weight`.
- `freespace_dead_end_max`, `freespace_side_open_min`.
- `direction_min_free_extent`.
- `stairs_centre_ratio_threshold`.
- Raise `decision_margin`.
- Re-tune `risk_centre_block_threshold` / `risk_side_block_threshold` against the
  corrected cost distribution — the current 0.45 was chosen against inflated
  costs and will be wrong once `ROAD` stops inflating them.

Extend the `validate_thresholds` model validator to cover the new ordering
constraints, matching the existing style.

### A7. `backend/app/perception/detector.py` (D-066)

Extend `CANONICAL_LABELS` with the indoor COCO classes that matter for hall
mobility — `door`, `suitcase`, `backpack`, `handbag`, `umbrella`,
`potted plant`, `couch`, `bed`, `tv`, `refrigerator`, `sink`, `toilet` — and
add matching entries to `risk_class_severities`. Unlisted labels already default to `0.5` in
`scoring.py`, so severity gaps degrade safely.

Keep the whitelist rather than passing all 80 classes: a whitelist keeps the
overlay legible and the risk score meaningful, and it keeps the label set
auditable, which `HALL_HAZARD_LABELS_V1.md` depends on.

### A8. Backend tests

- `backend/tests/unit/test_spatial.py` — synthetic `class_map` fixtures for:
  clear indoor floor, frontal wall, one-sided wall (must **not** be a dead end),
  stairs ahead, and a floor partially occluded by an obstacle.
- `backend/tests/unit/test_risk.py` — `MOVE_*` is refused when the target
  corridor lacks free space; `PAUSE_UNCLEAR` is returned instead.
- New `backend/tests/integration/test_indoor_frames.py` — golden-frame
  regression over ~20 real indoor JPEGs captured on the OnePlus and stored under
  `backend/tests/fixtures/indoor/`, asserting the expected action per frame.
  This is the only test that would have caught the original bug.

### A9. Documentation to update on this machine

- `docs/DECISIONS.md` — append D-063…D-067 once approved.
- `docs/HALL_HAZARD_LABELS_V1.md` — bump to `hall-hazards/2.0.0`; document the
  ADE20K vocabulary, the free-space evidence, the stairs event, and the revised
  wall/dead-end trigger.
- `docs/API_CONTRACTS.md` — record the new reason codes
  (`STAIRS_OR_LEVEL_CHANGE_AHEAD`) and confirm no schema change.
- `models/segmentation/segformer-b0-ade20k/MODEL_CARD.md` — new.

## 7. Workstream B — Android client (this dev box)

### B1. Detection labels on the overlay

`apps/android/app/src/main/java/com/drishti/app/ui/OverlayCanvas.kt` already
draws a coloured rectangle per detection but no text. Add a compact label chip:

- `rememberTextMeasurer()` in the composable, passed into the `Canvas` lambda;
  `DrawScope.drawText` for rendering.
- Content `"$label ${(confidence * 100).roundToInt()}%"`, matching the Expo
  harness in `apps/mobile/src/overlay/DetectionOverlay.tsx`.
- Small type (~9–10 sp), squared filled chip in the box's `display_color` with
  black text, anchored to the box's top-left and clamped inside the canvas so it
  never renders off-screen for boxes at the frame edge.
- Keep the box stroke square (no rounded corners) as it is today.
- Boxes stay behind the corridor polygons in draw order so the guidance overlay
  remains the dominant visual.

This is client-only and can ship before Workstream A. It will show nothing until
D-066 lands, because the backend currently returns zero detections indoors — that
is expected and is itself a useful diagnostic.

### B2. New reason strings

Add `reason_stairs` to `values/strings.xml`, `values-hi/strings.xml` and
`values-ta/strings.xml`, and map `STAIRS_OR_LEVEL_CHANGE_AHEAD` in
`GuidanceStrings.reasonText`. Until Workstream A ships the code, the existing
`else` branch keeps the app correct.

### B3. Contract compatibility check

`net/Dto.kt` declares `enum class SurfaceKind { WALKABLE, ROAD, NON_WALKABLE, UNKNOWN }`
and `SurfaceRegion.kind` has no default value. A new server-side enum member
would fail deserialization. **This plan deliberately adds no `SurfaceKind`
value** — stairs are carried as a reason code instead. If that changes, the
Android enum must ship first.

### B4. Optional diagnostics

Append the centre corridor's `floor_extent` to the existing on-screen diagnostic
line (currently `WALKING 116 ms • voice ready`) behind the debug flag. It makes
the new evidence visible during hall testing without a laptop.

## 8. Sequencing and joint validation

1. **Now, in parallel:** B1–B3 on the dev box; A1 (weight download) on the
   backend laptop. Neither blocks the other.
2. **Gate 1 — approval.** §5 decisions signed off and appended to
   `DECISIONS.md`. Nothing in A2–A7 starts before this.
3. **Backend implementation:** A2 → A3 → A4 → A5 → A6, then A7, then A8.
4. **Gate 2 — offline replay.** Re-run `tools/probe_walk.sh` over the same four
   frames plus the new fixture set. Acceptance criteria in §9.
5. **Gate 3 — live hall walk.** Rebuild and install the Android client, walk the
   same corridor and the same wall, confirm by ear and on screen.
6. **Gate 4 — regression.** Confirm the outdoor path still behaves: the
   Cityscapes-era vehicle and road rules must not have silently changed meaning
   under the new mapping.

## 9. Acceptance criteria

Measured with `tools/probe_walk.sh` on the captured frames:

| Frame | Required action | Required evidence |
|---|---|---|
| Clear corridor | `CLEAR` or `CAUTION` | ≥1 `safe_polygon`; centre `floor_extent` high |
| Blank wall ahead | `STOP` / `WALL_OR_DEAD_END_AHEAD` | centre `floor_extent` below the dead-end threshold |
| Door ahead, wall left | `STOP` or `PAUSE_UNCLEAR` | **no** `MOVE_LEFT`; no safe polygon over the wall |
| Room corner | `PAUSE_UNCLEAR` | not `ALL_CORRIDORS_BLOCKED` while floor is visible |
| Stairs ahead | `STOP` / `STAIRS_OR_LEVEL_CHANGE_AHEAD` | hazard-surface ratio above threshold |

Plus, across the whole fixture set:

- At least one frame produces a non-empty `safe_polygons` — proving "clear" is
  reachable indoors at all, which is not true today.
- No frame produces `MOVE_LEFT` or `MOVE_RIGHT` toward a corridor whose
  `floor_extent` is below `direction_min_free_extent`.
- p95 `total_ms` stays within the current live budget (measured 113–242 ms) so
  the ~2 fps loop is unaffected.

## 10. Explicitly out of scope

- **Monocular depth.** Still `DEGRADED`. §A4's free-space geometry is the
  approved substitute; a real depth model competes with Moondream2 for VRAM and
  needs its own decision and latency budget.
- **Camera pitch.** The corridor trapezoid assumes a fixed phone pose. Tilting
  the phone down invalidates `corridor_horizon_y = 0.38`. Fixing this properly
  means sending device pitch with each frame — an API contract change. Recorded
  here as the next most valuable improvement after this plan lands.
- **Training or fine-tuning any model.** Every change here uses published
  weights unchanged.
- **Outdoor hazards.** Potholes, drains, waterlogging remain out of scope per
  D-053.
