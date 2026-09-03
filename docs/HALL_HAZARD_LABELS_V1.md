# DRISHTI Indoor Hall Hazard Specification

## Version

- Specification: `hall-hazards/2.0.0`
- Owning phase: Phase 8 supplemental accuracy review
- Intended setting: controlled indoor campus hall obstacle course
- Camera: handheld rear-facing pedestrian camera

## Scope

The active semantic vocabulary is ADE20K. It supplies indoor floor, wall, door,
stairs, furniture, and structural classes while preserving the four-value
`SurfaceKind` wire contract. Matching splits comma-separated labels into
lowercase trimmed tokens so checkpoint label aliases cannot silently disable a
mapping.

| Output | Type | Minimum visible evidence | Default handling |
|---|---|---|---|
| `desk` | Object label | YOLO table/desk body above the generic threshold | Static corridor obstruction; severity `0.80` |
| Indoor object labels | Object labels | Audited YOLO class above threshold | Configured deterministic class severity |
| `WALL_OR_DEAD_END_AHEAD` | Derived event | Low centre floor extent, low floor extent on both sides, and confident centre-wall corroboration | Stable `STOP` after normal persistence |
| `STAIRS_OR_LEVEL_CHANGE_AHEAD` | Derived event | Confident stairs/stairway/step/escalator evidence above the centre ratio threshold | Stable `STOP` after normal persistence |

`dining table` and `table` canonicalize to `desk`; backpack and handbag
canonicalize to `bag`. Current YOLO11n COCO weights do not contain a native
door class, so the forward-compatible `door` canonical label must not be
advertised as a currently demonstrated detection.

## Surface semantics

- `WALKABLE`: floor/flooring, rug/carpet, path, sidewalk, and pavement.
- `ROAD`: genuine road/route only. The indoor default blocking coefficient is
  zero; roadway remains distinct evidence rather than invented floor.
- `NON_WALKABLE`: wall/building/ceiling, doors/windows, cabinets/wardrobes,
  columns, furniture, railings/fences/poles, people, vehicles, and stairs or
  other supported level-change surfaces.
- `UNKNOWN`: any label not present in the selected dataset-aware table.

A corridor is uncertain when it has neither the minimum positive walkable share
nor a meaningful non-walkable share. Unknown content is not treated as proof of
clearance.

## Relative free-space evidence

For each corridor column, analysis starts at the corridor base and measures the
contiguous upward run of `WALKABLE` pixels. The median normalized run is the
`floor_extent` for that corridor. Median aggregation resists a narrow chair or
bag leg. The extent is image-space evidence in `[0,1]`; it is not metric depth,
clearance, or a guarantee that movement is safe.

Directional guidance requires all of the following for the proposed side:

- floor extent at least `direction_min_free_extent`;
- walkable ratio at least the walkable gate;
- wall ratio below the configured side ceiling;
- cost advantage at least `decision_margin`; and
- the same proposed side for `alert_persistence_frames` consecutive frames.

If any condition is absent, the result is `PAUSE_UNCLEAR` with
`CENTRE_BLOCKED_DIRECTION_UNCLEAR`.

## Initial engineering defaults

These are unvalidated until the supplemental controlled-frame and live hall
checks pass:

- Wall pixel confidence: `0.60`
- Centre wall corroboration ratio: `0.35`
- Visible-floor dead-end maximum: `0.12`
- Side-open visible-floor minimum: `0.30`
- Directional visible-floor minimum: `0.35`
- Centre stairs/level-change ratio: `0.08`
- Road cost weight: `0.0`
- Unknown cost weight: `0.10`
- Centre/side block thresholds: `0.40`
- Direction cost margin: `0.15`

## Required controlled evidence

- Clear hall: `CLEAR` or `CAUTION`, with at least one safe polygon.
- Frontal blank wall: `STOP` / `WALL_OR_DEAD_END_AHEAD`.
- Side wall with visible open floor: never a false dead-end stop.
- Door ahead with wall left: never `MOVE_LEFT`.
- Room corner with some visible floor: `PAUSE_UNCLEAR`, not an unsupported turn.
- Stairs ahead: `STOP` / `STAIRS_OR_LEVEL_CHANGE_AHEAD`.
- Narrow obstacle leg: must not collapse median floor extent by itself.

Approved real fixtures are loaded from an external directory. Continuous walk
frames must not be committed or persisted.

## Unsupported and prohibited claims

- Potholes, drains, waterlogging, floor cable, debris, low-hanging obstacle, and
  other unvalidated outdoor hazards remain unsupported.
- Floor extent is not wall distance, time-to-collision, route clearance, or a
  guarantee that a direction is safe.
- The prototype does not replace a cane, guide dog, mobility training, or human
  judgment.

## Degradation behavior

If segmentation is unavailable, generic detections continue and the response
lists `segmentation` and `india_hazards` as degraded. Walk Mode depends on the
generic detector, not this optional hall semantic expansion.
