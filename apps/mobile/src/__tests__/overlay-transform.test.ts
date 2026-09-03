import { mapNormalizedBoundingBoxToPreview, mapNormalizedPointToPreview, mapNormalizedPolygonToPreview } from "../overlay/transform";

test("maps centre and corners for an exact aspect match", () => {
  const input = {
    sourceWidth: 400,
    sourceHeight: 800,
    previewWidth: 200,
    previewHeight: 400,
    resizeMode: "COVER" as const,
  };

  expect(mapNormalizedPointToPreview({ x: 0, y: 0 }, input)).toEqual({ x: 0, y: 0, visible: true });
  expect(mapNormalizedPointToPreview({ x: 0.5, y: 0.5 }, input)).toEqual({ x: 100, y: 200, visible: true });
  expect(mapNormalizedPointToPreview({ x: 1, y: 1 }, input)).toEqual({ x: 200, y: 400, visible: true });
});

test("accounts for horizontal crop in COVER mode", () => {
  const input = {
    sourceWidth: 400,
    sourceHeight: 300,
    previewWidth: 300,
    previewHeight: 600,
    resizeMode: "COVER" as const,
  };

  expect(mapNormalizedPointToPreview({ x: 0.5, y: 0.5 }, input)).toEqual({ x: 150, y: 300, visible: true });
  expect(mapNormalizedPointToPreview({ x: 0, y: 0.5 }, input)).toEqual({ x: -250, y: 300, visible: false });
  expect(mapNormalizedPointToPreview({ x: 1, y: 0.5 }, input)).toEqual({ x: 550, y: 300, visible: false });
});

test("accounts for letterboxing in CONTAIN mode", () => {
  const input = {
    sourceWidth: 400,
    sourceHeight: 300,
    previewWidth: 300,
    previewHeight: 600,
    resizeMode: "CONTAIN" as const,
  };

  expect(mapNormalizedPointToPreview({ x: 0, y: 0 }, input)).toEqual({ x: 0, y: 187.5, visible: true });
  expect(mapNormalizedPointToPreview({ x: 1, y: 1 }, input)).toEqual({ x: 300, y: 412.5, visible: true });
});

test("uses orientation-corrected dimensions after a 90 degree rotation", () => {
  const point = mapNormalizedPointToPreview(
    { x: 0.25, y: 0.75 },
    {
      sourceWidth: 300,
      sourceHeight: 400,
      previewWidth: 300,
      previewHeight: 400,
      resizeMode: "COVER",
    },
  );
  expect(point).toEqual({ x: 75, y: 300, visible: true });
});

test("rejects non-normalized coordinates", () => {
  expect(() =>
    mapNormalizedPointToPreview(
      { x: 1.1, y: 0.5 },
      { sourceWidth: 1, sourceHeight: 1, previewWidth: 1, previewHeight: 1, resizeMode: "COVER" },
    ),
  ).toThrow("normalized");
});

test("maps and clips a normalized detection box after COVER crop", () => {
  const result = mapNormalizedBoundingBoxToPreview(
    { x1: 0.2, y1: 0.25, x2: 0.8, y2: 0.75 },
    {
      sourceWidth: 400,
      sourceHeight: 300,
      previewWidth: 300,
      previewHeight: 600,
      resizeMode: "COVER",
    },
  );

  expect(result).toEqual({ left: 0, top: 150, width: 300, height: 300, visible: true });
});

test("does not render a detection box fully outside the cropped preview", () => {
  const result = mapNormalizedBoundingBoxToPreview(
    { x1: 0, y1: 0.1, x2: 0.1, y2: 0.2 },
    {
      sourceWidth: 400,
      sourceHeight: 300,
      previewWidth: 300,
      previewHeight: 600,
      resizeMode: "COVER",
    },
  );

  expect(result.visible).toBe(false);
  expect(result.width).toBe(0);
});

test("maps normalized surface polygons through the same COVER transform", () => {
  const result = mapNormalizedPolygonToPreview(
    [{ x: 0.25, y: 0.5 }, { x: 0.75, y: 0.5 }, { x: 0.5, y: 1 }],
    { sourceWidth: 200, sourceHeight: 400, previewWidth: 100, previewHeight: 200, resizeMode: "COVER" },
  );
  expect(result).toEqual({ points: "25,100 75,100 50,200", visible: true });
});
