# DRISHTI Indoor Hall Hazard Specification

## Version

- Specification: `hall-hazards/1.0.0`
- Owning phase: Phase 8
- Intended setting: controlled indoor campus hall obstacle course
- Camera: handheld rear-facing pedestrian camera

## Scope

Phase 8 adds only `desk` and the derived `WALL_OR_DEAD_END_AHEAD` event. Existing
`person`, `chair`, and `bag` detections remain supported by the generic detector.
No label identifies nationality, identity, or a person by face.

| Output | Type | Minimum visible evidence | Default handling |
|---|---|---|---|
| `desk` | Object detection label | A visible table/desk body with a valid normalized box above the generic detector threshold | Static corridor obstruction; severity `0.80` |
| `WALL_OR_DEAD_END_AHEAD` | Derived spatial event | Confident SegFormer `wall` pixels meet the configured centre threshold and both side thresholds | Stable `STOP` after normal non-critical persistence |

The generic model labels `dining table` and `table` are canonicalized to `desk`.
Wall pixels remain `NON_WALKABLE` surface evidence; `wall` is not invented as a
bounding-box detection.

## Required evidence

### Desk

- Positive: desk/table occupying the centre walking corridor.
- Negative: clear hall with no desk or table.
- Hard negative: chair, bench, shelf, or wall edge that must not be returned as a desk.

### Wall or dead end

- Positive: frontal wall spanning left, centre, and right forward corridors.
- Negative: clear hall with visible forward floor.
- Hard negatives: side wall, doorway/open passage, partition at one side, and a
  low-confidence wall mask.

## Thresholds

Initial engineering thresholds are configuration values and require controlled
physical validation:

- Wall pixel confidence: `0.60`
- Centre-corridor wall coverage: `0.35`
- Left/right wall coverage: `0.20` each

The side threshold cannot exceed the centre threshold. A low-confidence or
one-sided wall cannot produce the wall/dead-end reason code.

## Unsupported and prohibited claims

- Pothole, open drain, waterlogging, floor cable, debris, low-hanging obstacle,
  and outdoor street hazards are not enabled in this phase.
- The system does not estimate exact wall distance.
- `WALL_OR_DEAD_END_AHEAD` is a conservative image-space observation, not proof
  that the entire real-world area has no exit.
- The prototype does not replace a cane, guide dog, mobility training, or human
  judgment.

## Degradation behavior

If segmentation is unavailable or fails, desk and other generic detections continue.
The response lists `segmentation` and `india_hazards` as degraded, and existing
uncertainty behavior applies. Walk Mode depends on the generic detector, not this
optional hall expansion.
