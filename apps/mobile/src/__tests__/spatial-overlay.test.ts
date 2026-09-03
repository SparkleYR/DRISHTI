import type { DetectionResult } from "@drishti/contracts";

import { CORRIDOR_COLORS, directionArrowGeometry, motionVectorToPreview } from "../overlay/SpatialOverlay";


test("maps a tracked object's normalized motion vector", () => {
  const detection = {
    anchor: { x: 0.5, y: 0.5 },
    motion_vector: { dx: 0.05, dy: 0.025 },
  } as DetectionResult;
  expect(motionVectorToPreview(detection, {
    sourceWidth: 100,
    sourceHeight: 200,
    previewWidth: 100,
    previewHeight: 200,
    resizeMode: "COVER",
  })).toEqual({ x1: 50, y1: 100, x2: 70, y2: 120 });
});

test("does not draw motion before a track has history", () => {
  const detection = { anchor: { x: 0.5, y: 0.5 }, motion_vector: null } as DetectionResult;
  expect(motionVectorToPreview(detection, {
    sourceWidth: 1,
    sourceHeight: 1,
    previewWidth: 1,
    previewHeight: 1,
    resizeMode: "COVER",
  })).toBeNull();
});

test("maps contract directions to a stable visual indicator", () => {
  const left = directionArrowGeometry("LEFT", 100, 200);
  const right = directionArrowGeometry("RIGHT", 100, 200);
  const stop = directionArrowGeometry("STOP", 100, 200);

  expect(left?.kind).toBe("ARROW");
  expect(right?.kind).toBe("ARROW");
  if (left?.kind === "ARROW" && right?.kind === "ARROW") {
    expect(left.x2).toBeLessThan(left.x1);
    expect(right.x2).toBeGreaterThan(right.x1);
    expect(left.color).toBe("#00d26a");
  }
  expect(stop).toMatchObject({ kind: "STOP", color: "#ff3434" });
  expect(directionArrowGeometry("NONE", 100, 200)).toBeNull();
});

test("uses the contract green, red, and yellow corridor semantics", () => {
  expect(CORRIDOR_COLORS.SAFE.stroke).toBe("#00d26a");
  expect(CORRIDOR_COLORS.BLOCKED.stroke).toBe("#ff3434");
  expect(CORRIDOR_COLORS.UNCERTAIN.stroke).toBe("#ffd400");
});
