# Phase 3 controlled checks

- The real CUDA integration test reuses `../phase2/ultralytics-bus.jpg` to
  verify YOLO detections plus SegFormer road and sidewalk surface regions.
- `approaching-vehicle.json` is a deterministic two-frame normalized-box
  fixture used to verify stable tracking, growth-based approach state, relative
  proximity, and motion-vector output without claiming metric depth or exact
  time to collision.
- The physical gate requires a stationary, sighted test with the phone pointed
  at a controlled footpath/road transition. Confirm that the cyan sidewalk and
  orange road regions align approximately, track IDs remain stable across
  nearby captures, and corridor outlines use current—not old—frames.

Do not test in active traffic, do not walk blindfolded, and do not treat these
prototype outputs as crossing-safety guidance.
