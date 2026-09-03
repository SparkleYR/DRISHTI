# Walk Mode accuracy amendment

- Plan version: `walk-accuracy/1.0.0`
- Accepted decisions: D-063 through D-067
- Backend status: implemented; supplemental Phase 8 gate `IN_REVIEW`
- Android status: explicitly excluded from this implementation

## Implemented backend correction

Measured indoor replay showed that the former Cityscapes segmenter labelled
both tiled floor and a nearby blank wall as high-confidence `ROAD`. That made
safe polygons unreachable, inflated clear-floor corridor costs to the blocking
threshold, and allowed side guidance to be selected from small noisy cost
differences.

The backend now:

- loads the local ADE20K SegFormer-B0 snapshot and reports its dataset in health;
- accepts either safetensors or legacy PyTorch checkpoint files;
- token-normalizes the model label map and uses explicit ADE20K/Cityscapes
  surface tables without adding a `SurfaceKind` value;
- maps indoor floor-like classes to `WALKABLE` and removes the indoor default
  blocking cost from genuine `ROAD`;
- derives per-corridor relative visible-floor extent from the median contiguous
  floor run, never as metres;
- corroborates low free space with centre-wall evidence for dead-end stops;
- emits `STAIRS_OR_LEVEL_CHANGE_AHEAD` for meaningful centre level-change
  evidence;
- requires positive walkable, floor-extent, wall, cost-margin, and normal
  multi-frame persistence evidence before `MOVE_LEFT` or `MOVE_RIGHT`; and
- expands the audited indoor obstacle whitelist and severity configuration.

## Automated evidence

- Synthetic floor, wall, side-wall, stairs, occlusion, token-mapping, direction
  refusal, checkpoint-format, detector-label, API, and degradation tests pass.
- The real RTX 4060 offline test passes with YOLO11n and ADE20K SegFormer.
- The response schema remains version `1.0.0`; the new stairs value is a
  free-form reason code, not a new enum.
- No Walk Loop image is written by the implementation or tests.

## Remaining supplemental gate

1. Supply an explicitly approved external controlled-fixture directory through
   `DRISHTI_INDOOR_FIXTURE_DIR`; do not commit continuous walking frames.
2. Run `backend/tests/integration/test_indoor_frames.py -m real_indoor` over at
   least clear corridor, blank wall, wall-left/door, room corner, and stairs.
3. Confirm replay p95 remains at or below 250 ms and inspect outputs with
   `tools/probe_walk.sh` if needed.
4. Repeat the controlled live hall test with normal mobility safeguards.
5. Confirm an outdoor road/vehicle fixture still preserves the intended road
   and critical-vehicle behavior.
6. Obtain supplemental user approval before returning Phase 8 to `COMPLETE`.

Android overlay labels and localized stairs strings from the source proposal
remain unimplemented by explicit user direction. Existing clients retain schema
compatibility and fall back safely for unknown reason strings.
