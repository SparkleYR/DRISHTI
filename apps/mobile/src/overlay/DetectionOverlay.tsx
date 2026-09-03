import type { DetectionResult, FrameGeometry } from "@drishti/contracts";
import { StyleSheet, Text, View } from "react-native";

import { mapNormalizedBoundingBoxToPreview } from "./transform";


interface Props {
  detections: DetectionResult[];
  geometry: FrameGeometry;
  previewWidth: number;
  previewHeight: number;
}

const COLORS = {
  GREEN: "#00d26a",
  YELLOW: "#ffd400",
  RED: "#ff3434",
  GREY: "#a9a9a9",
} as const;

export function detectionOverlayColor(color: DetectionResult["display_color"]): string {
  return COLORS[color];
}

export function DetectionOverlay({ detections, geometry, previewWidth, previewHeight }: Props) {
  if (previewWidth <= 0 || previewHeight <= 0) return null;

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {detections.map((detection, index) => {
        const box = mapNormalizedBoundingBoxToPreview(detection.bbox, {
          sourceWidth: geometry.source_width,
          sourceHeight: geometry.source_height,
          previewWidth,
          previewHeight,
          resizeMode: "COVER",
        });
        if (!box.visible) return null;
        const color = detectionOverlayColor(detection.display_color);
        return (
          <View
            key={`${detection.label}-${index}`}
            style={[
              styles.box,
              {
                borderColor: color,
                height: box.height,
                left: box.left,
                top: box.top,
                width: box.width,
              },
            ]}
          >
            <Text style={[styles.label, { backgroundColor: color }]}>
              {detection.label} {Math.round(detection.confidence * 100)}%
            </Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderWidth: 3, position: "absolute" },
  label: { alignSelf: "flex-start", color: "#000000", fontSize: 12, fontWeight: "700", padding: 3 },
});
