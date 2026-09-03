# Phase 8 controlled hall evidence

This directory defines the physical evidence still required for the Phase 8 gate.
Continuous walking frames must not be copied here. Use deliberately captured,
consented test images only.

Required scenes:

1. Clear hall: no wall/dead-end stop across five analyzed frames.
2. Frontal wall: stable `STOP` with `WALL_OR_DEAD_END_AHEAD` after persistence.
3. Side wall with an open forward corridor: no wall/dead-end reason.
4. Centre desk: `desk` box aligns and produces normal corridor/risk behavior.
5. Chair, backpack, and person arrangements: existing labels remain functional.
6. Hard negatives: chair/bench/shelf are not reported as `desk`; a doorway is not
   reported as a dead end.

Record for each scene: expected output, actual output, number of analyzed frames,
false wall stops, false desk detections, and whether the normalized overlay aligns.
Testing must be sighted and controlled; never use unsafe blindfolded walking.
