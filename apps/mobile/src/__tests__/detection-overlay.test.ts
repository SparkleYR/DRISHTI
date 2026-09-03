import { detectionOverlayColor } from "../overlay/DetectionOverlay";


test("uses the contract display colors for Phase 2 boxes", () => {
  expect(detectionOverlayColor("YELLOW")).toBe("#ffd400");
  expect(detectionOverlayColor("RED")).toBe("#ff3434");
});
