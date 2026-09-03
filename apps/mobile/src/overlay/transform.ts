import type { NormalizedBoundingBox, NormalizedPoint, PreviewResizeMode } from "@drishti/contracts";

export interface PreviewTransformInput {
  sourceWidth: number;
  sourceHeight: number;
  previewWidth: number;
  previewHeight: number;
  resizeMode: PreviewResizeMode;
}

export interface PreviewPoint {
  x: number;
  y: number;
  visible: boolean;
}

export interface PreviewBox {
  left: number;
  top: number;
  width: number;
  height: number;
  visible: boolean;
}

export interface PreviewPolygon {
  points: string;
  visible: boolean;
}

export function mapNormalizedPointToPreview(
  point: NormalizedPoint,
  input: PreviewTransformInput,
): PreviewPoint {
  const values = [
    point.x,
    point.y,
    input.sourceWidth,
    input.sourceHeight,
    input.previewWidth,
    input.previewHeight,
  ];
  if (values.some((value) => !Number.isFinite(value))) {
    throw new Error("Preview transform values must be finite.");
  }
  if (point.x < 0 || point.x > 1 || point.y < 0 || point.y > 1) {
    throw new Error("Overlay coordinates must be normalized.");
  }
  if (
    input.sourceWidth <= 0 ||
    input.sourceHeight <= 0 ||
    input.previewWidth <= 0 ||
    input.previewHeight <= 0
  ) {
    throw new Error("Preview and source dimensions must be positive.");
  }

  const scaleX = input.previewWidth / input.sourceWidth;
  const scaleY = input.previewHeight / input.sourceHeight;
  const scale = input.resizeMode === "COVER" ? Math.max(scaleX, scaleY) : Math.min(scaleX, scaleY);
  const renderedWidth = input.sourceWidth * scale;
  const renderedHeight = input.sourceHeight * scale;
  const offsetX = (input.previewWidth - renderedWidth) / 2;
  const offsetY = (input.previewHeight - renderedHeight) / 2;
  const x = offsetX + point.x * renderedWidth;
  const y = offsetY + point.y * renderedHeight;

  return {
    x,
    y,
    visible: x >= 0 && x <= input.previewWidth && y >= 0 && y <= input.previewHeight,
  };
}

export function mapNormalizedBoundingBoxToPreview(
  box: NormalizedBoundingBox,
  input: PreviewTransformInput,
): PreviewBox {
  if (box.x1 >= box.x2 || box.y1 >= box.y2) {
    throw new Error("Overlay bounding-box minimums must be below maximums.");
  }
  const topLeft = mapNormalizedPointToPreview({ x: box.x1, y: box.y1 }, input);
  const bottomRight = mapNormalizedPointToPreview({ x: box.x2, y: box.y2 }, input);
  const left = Math.max(0, topLeft.x);
  const top = Math.max(0, topLeft.y);
  const right = Math.min(input.previewWidth, bottomRight.x);
  const bottom = Math.min(input.previewHeight, bottomRight.y);
  const visible = right > left && bottom > top;

  return {
    left,
    top,
    width: visible ? right - left : 0,
    height: visible ? bottom - top : 0,
    visible,
  };
}

export function mapNormalizedPolygonToPreview(
  polygon: NormalizedPoint[],
  input: PreviewTransformInput,
): PreviewPolygon {
  if (polygon.length < 3) {
    throw new Error("Overlay polygons require at least three points.");
  }
  const points = polygon.map((point) => mapNormalizedPointToPreview(point, input));
  return {
    points: points.map((point) => `${point.x},${point.y}`).join(" "),
    visible: points.some((point) => point.visible),
  };
}
