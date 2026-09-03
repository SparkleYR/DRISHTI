# Phase 4 controlled checks

`decision-scenarios.json` freezes normalized detector inputs for deterministic
direction and STOP tests. Automated tests also cover alert persistence,
hysteresis, cooldown, deduplication, stale responses, and a critical approaching
motorcycle override.

For the physical gate, use ordinary sighted testing in a controlled room:

1. Place a chair in the centre and a bag to the left, leaving the right clear.
2. Capture at least two nearby frames in the same session.
3. Confirm `MOVE_RIGHT`, one green right corridor, red blocked geometry, a right
   arrow, `WARNING_DOUBLE`, and the matching speech text in the raw response.
4. Capture another unchanged frame and confirm `speak` becomes `false`.
5. Never test by walking blindfolded or entering a roadway.
