import type {
  DetectionResult,
  FrameGeometry,
  OverlayContract,
  SurfaceRegion,
} from "@drishti/contracts";
import { Fragment } from "react";
import Svg, { Circle, Line, Polygon } from "react-native-svg";

import {
  mapNormalizedPointToPreview,
  mapNormalizedPolygonToPreview,
  type PreviewTransformInput,
} from "./transform";


interface Props {
  detections: DetectionResult[];
  geometry: FrameGeometry;
  overlay: OverlayContract;
  previewWidth: number;
  previewHeight: number;
  surfaces: SurfaceRegion[];
}

const SURFACE_COLORS = {
  WALKABLE: "rgba(0, 210, 255, 0.24)",
  ROAD: "rgba(255, 145, 0, 0.24)",
  NON_WALKABLE: "rgba(150, 150, 150, 0.20)",
  UNKNOWN: "rgba(255, 212, 0, 0.10)",
} as const;

export const CORRIDOR_COLORS = {
  SAFE: { fill: "rgba(0, 210, 106, 0.28)", stroke: "#00d26a" },
  BLOCKED: { fill: "rgba(255, 52, 52, 0.30)", stroke: "#ff3434" },
  UNCERTAIN: { fill: "rgba(255, 212, 0, 0.22)", stroke: "#ffd400" },
} as const;

export function SpatialOverlay({
  detections,
  geometry,
  overlay,
  previewWidth,
  previewHeight,
  surfaces,
}: Props) {
  if (previewWidth <= 0 || previewHeight <= 0) return null;
  const transform: PreviewTransformInput = {
    sourceWidth: geometry.source_width,
    sourceHeight: geometry.source_height,
    previewWidth,
    previewHeight,
    resizeMode: "COVER",
  };

  return (
    <Svg pointerEvents="none" style={{ position: "absolute" }} width={previewWidth} height={previewHeight}>
      {surfaces.map((surface, index) => {
        const mapped = mapNormalizedPolygonToPreview(surface.polygon, transform);
        return mapped.visible ? (
          <Polygon
            key={`surface-${index}`}
            points={mapped.points}
            fill={SURFACE_COLORS[surface.kind]}
            stroke={SURFACE_COLORS[surface.kind]}
            strokeWidth={2}
          />
        ) : null;
      })}
      {overlay.safe_polygons.map((polygon, index) => (
        <PolygonShape key={`clear-${index}`} polygon={polygon} transform={transform} fill={CORRIDOR_COLORS.SAFE.fill} stroke={CORRIDOR_COLORS.SAFE.stroke} />
      ))}
      {overlay.blocked_polygons.map((polygon, index) => (
        <PolygonShape key={`occupied-${index}`} polygon={polygon} transform={transform} fill={CORRIDOR_COLORS.BLOCKED.fill} stroke={CORRIDOR_COLORS.BLOCKED.stroke} />
      ))}
      {overlay.uncertain_polygons.map((polygon, index) => (
        <PolygonShape key={`uncertain-${index}`} polygon={polygon} transform={transform} fill={CORRIDOR_COLORS.UNCERTAIN.fill} stroke={CORRIDOR_COLORS.UNCERTAIN.stroke} />
      ))}
      {detections.map((detection) => {
        const motion = motionVectorToPreview(detection, transform);
        if (!motion) return null;
        return (
          <Fragment key={`motion-${detection.track_id}`}>
            <Line {...motion} stroke="#ffffff" strokeWidth={3} />
            <Circle cx={motion.x2} cy={motion.y2} fill="#ffffff" r={5} />
          </Fragment>
        );
      })}
      <DirectionIndicator
        arrow={overlay.direction_arrow}
        previewHeight={previewHeight}
        previewWidth={previewWidth}
      />
    </Svg>
  );
}

function PolygonShape({
  polygon,
  transform,
  stroke,
  fill,
}: {
  polygon: { x: number; y: number }[];
  transform: PreviewTransformInput;
  stroke: string;
  fill: string;
}) {
  const mapped = mapNormalizedPolygonToPreview(polygon, transform);
  return mapped.visible ? (
    <Polygon points={mapped.points} fill={fill} stroke={stroke} strokeWidth={3} />
  ) : null;
}

type DirectionGeometry =
  | { kind: "ARROW"; color: string; x1: number; y1: number; x2: number; y2: number; head: string }
  | { kind: "STOP"; color: string; cx: number; cy: number; radius: number };

export function directionArrowGeometry(
  arrow: OverlayContract["direction_arrow"],
  width: number,
  height: number,
): DirectionGeometry | null {
  if (arrow === "NONE" || width <= 0 || height <= 0) return null;
  const cy = height * 0.24;
  if (arrow === "STOP") {
    return { kind: "STOP", color: "#ff3434", cx: width * 0.5, cy, radius: Math.min(width, height) * 0.07 };
  }
  const pointsLeft = arrow === "LEFT";
  const x1 = width * (pointsLeft ? 0.68 : 0.32);
  const x2 = width * (pointsLeft ? 0.28 : 0.72);
  const headSize = Math.min(width, height) * 0.045;
  return {
    kind: "ARROW",
    color: "#00d26a",
    x1,
    y1: cy,
    x2,
    y2: cy,
    head: `${x2},${cy} ${x2 + (pointsLeft ? headSize : -headSize)},${cy - headSize} ${x2 + (pointsLeft ? headSize : -headSize)},${cy + headSize}`,
  };
}

function DirectionIndicator({
  arrow,
  previewWidth,
  previewHeight,
}: {
  arrow: OverlayContract["direction_arrow"];
  previewWidth: number;
  previewHeight: number;
}) {
  const geometry = directionArrowGeometry(arrow, previewWidth, previewHeight);
  if (!geometry) return null;
  if (geometry.kind === "STOP") {
    return (
      <>
        <Circle cx={geometry.cx} cy={geometry.cy} fill="rgba(255, 52, 52, 0.24)" r={geometry.radius} stroke={geometry.color} strokeWidth={5} />
        <Line x1={geometry.cx - geometry.radius / 2} y1={geometry.cy - geometry.radius / 2} x2={geometry.cx + geometry.radius / 2} y2={geometry.cy + geometry.radius / 2} stroke={geometry.color} strokeWidth={6} />
        <Line x1={geometry.cx + geometry.radius / 2} y1={geometry.cy - geometry.radius / 2} x2={geometry.cx - geometry.radius / 2} y2={geometry.cy + geometry.radius / 2} stroke={geometry.color} strokeWidth={6} />
      </>
    );
  }
  return (
    <>
      <Line x1={geometry.x1} y1={geometry.y1} x2={geometry.x2} y2={geometry.y2} stroke={geometry.color} strokeLinecap="round" strokeWidth={8} />
      <Polygon fill={geometry.color} points={geometry.head} />
    </>
  );
}

export function motionVectorToPreview(
  detection: DetectionResult,
  transform: PreviewTransformInput,
): { x1: number; y1: number; x2: number; y2: number } | null {
  if (!detection.motion_vector) return null;
  const start = mapNormalizedPointToPreview(detection.anchor, transform);
  const end = mapNormalizedPointToPreview(
    {
      x: clamp(detection.anchor.x + detection.motion_vector.dx * 4),
      y: clamp(detection.anchor.y + detection.motion_vector.dy * 4),
    },
    transform,
  );
  return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}
