import type { CreateHazardRequest, FrameAnalysisResponse, FrameGeometry, ReadTextResponse, StartWalkSessionResponse } from "@drishti/contracts";
import { CameraView, useCameraPermissions } from "expo-camera";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, LayoutChangeEvent, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { analyzeFrame, createHazardReport, endWalkSession, fetchNearbyHazards, isConnectionFailure, readText, startWalkSession } from "../api/client";
import { DetectionOverlay } from "../overlay/DetectionOverlay";
import { SpatialOverlay } from "../overlay/SpatialOverlay";
import { mapNormalizedPointToPreview } from "../overlay/transform";
import { shouldApplyFrameResult } from "../state/frameFreshness";
import { adaptiveCaptureDelayMs, CaptureLoopGate } from "../state/captureLoop";
import { buildAnonymousHazardReport, HALL_DEMO_LOCATION } from "../state/hazardReport";

interface Props {
  backendUrl: string;
  onBack: () => void;
}

type PreviewSize = { width: number; height: number };

const WALK_TEST_CAPTURE_MAX_WIDTH = 640;
const WALK_TEST_JPEG_QUALITY = 0.5;

const TEST_POINTS = [
  { id: "TL", x: 0, y: 0 },
  { id: "TR", x: 1, y: 0 },
  { id: "C", x: 0.5, y: 0.5 },
  { id: "BL", x: 0, y: 1 },
  { id: "BR", x: 1, y: 1 },
] as const;

export function CameraTestScreen({ backendUrl, onBack }: Props) {
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const sessionRef = useRef<StartWalkSessionResponse | null>(null);
  const frameIdRef = useRef(0);
  const latestAppliedFrameIdRef = useRef(-1);
  const captureGateRef = useRef(new CaptureLoopGate());
  const continuousRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [session, setSession] = useState<StartWalkSessionResponse | null>(null);
  const [result, setResult] = useState<FrameAnalysisResponse | null>(null);
  const [previewSize, setPreviewSize] = useState<PreviewSize>({ width: 0, height: 0 });
  const [successfulFrames, setSuccessfulFrames] = useState(0);
  const [status, setStatus] = useState("Starting local test session…");
  const [busy, setBusy] = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [pendingReport, setPendingReport] = useState<CreateHazardRequest | null>(null);
  const [hazardStatus, setHazardStatus] = useState("Nearby hazard sync starting…");
  const [nearbyCount, setNearbyCount] = useState(0);
  const [exploreResult, setExploreResult] = useState<ReadTextResponse | null>(null);

  useEffect(() => {
    let active = true;
    startWalkSession(backendUrl)
      .then((created) => {
        if (!active) {
          void endWalkSession(backendUrl, created.session_id);
          return;
        }
        sessionRef.current = created;
        setSession(created);
        latestAppliedFrameIdRef.current = -1;
        setStatus("Ready. Capture frames to test risk, guidance, and AR coordinates.");
      })
      .catch((error) => setStatus(error instanceof Error ? error.message : "Session start failed."));

    return () => {
      active = false;
      continuousRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      const current = sessionRef.current;
      sessionRef.current = null;
      if (current) void endWalkSession(backendUrl, current.session_id);
    };
  }, [backendUrl]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sync = async () => {
      try {
        const response = await fetchNearbyHazards(backendUrl, HALL_DEMO_LOCATION);
        if (!active) return;
        setNearbyCount(response.items.length);
        setHazardStatus(`Nearby active reports: ${response.items.length}`);
      } catch (error) {
        if (!active) return;
        setHazardStatus(error instanceof Error ? `Hazard sync unavailable: ${error.message}` : "Hazard sync unavailable.");
      } finally {
        if (active) timer = setTimeout(() => void sync(), 2_000);
      }
    };
    void sync();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [backendUrl]);

  const capture = async (fromContinuous = false) => {
    const currentSession = sessionRef.current;
    if (!cameraRef.current || !currentSession || !captureGateRef.current.tryBegin()) return;
    setBusy(true);
    setStatus("Capturing and uploading…");
    let latestResponse: FrameAnalysisResponse | null = null;
    let backendRequestStarted = false;
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: WALK_TEST_JPEG_QUALITY,
        skipProcessing: false,
      });
      if (!photo) throw new Error("The camera did not return an image.");
      const capturedAt = new Date().toISOString();
      let imageUri = photo.uri;
      const uploadWidth = Math.min(
        WALK_TEST_CAPTURE_MAX_WIDTH,
        currentSession.max_image_width,
      );
      if (photo.width > uploadWidth) {
        const context = ImageManipulator.manipulate(photo.uri);
        context.resize({ width: uploadWidth, height: null });
        const rendered = await context.renderAsync();
        const resized = await rendered.saveAsync({
          compress: WALK_TEST_JPEG_QUALITY,
          format: SaveFormat.JPEG,
        });
        imageUri = resized.uri;
      }

      const frameId = frameIdRef.current;
      frameIdRef.current += 1;
      backendRequestStarted = true;
      const response = await analyzeFrame({
        baseUrl: backendUrl,
        sessionId: currentSession.session_id,
        frameId,
        capturedAt,
        imageUri,
      });
      latestResponse = response;
      const recovery = captureGateRef.current.finishSuccess();
      if (response.session_id !== currentSession.session_id || response.frame_id !== frameId) {
        throw new Error("Backend response identifiers do not match the uploaded frame.");
      }
      if (!shouldApplyFrameResult(response, {
        activeSessionId: sessionRef.current?.session_id ?? null,
        latestAppliedFrameId: latestAppliedFrameIdRef.current,
        maxResultAgeMs: currentSession.max_result_age_ms,
        nowMs: Date.now(),
        sessionActive: sessionRef.current !== null,
      })) {
        setResult(null);
        setStatus("Guidance paused: stale result discarded.");
        return;
      }
      latestAppliedFrameIdRef.current = response.frame_id;
      setResult(response);
      setSuccessfulFrames((count) => count + 1);
      setStatus(recovery.connectionRestored ? "Local backend connection recovered." : "Fresh frame accepted.");
    } catch (error) {
      if (captureGateRef.current.inFlight) {
        if (backendRequestStarted && isConnectionFailure(error)) {
          const incident = captureGateRef.current.finishConnectionFailure();
          const reason = error instanceof Error ? error.message : "unknown upload error";
          setResult(null);
          setStatus(
            incident.announceConnectionLost
              ? `Connection lost: ${reason}. Guidance paused; retrying locally.`
              : `Retrying local backend connection: ${reason}`,
          );
        } else {
          captureGateRef.current.finishRequestFailure();
          setResult(null);
          setStatus(error instanceof Error ? error.message : "Frame upload failed.");
        }
      } else {
        setResult(null);
        setStatus(error instanceof Error ? error.message : "Frame upload failed.");
      }
    } finally {
      setBusy(false);
      if (continuousRef.current && fromContinuous && currentSession) {
        const delay = adaptiveCaptureDelayMs({
          consecutiveFailures: captureGateRef.current.consecutiveFailures,
          frameAgeMs: latestResponse?.frame_age_ms,
          maxResultAgeMs: currentSession.max_result_age_ms,
          recommendedFps: currentSession.recommended_capture_fps,
          totalProcessingMs: latestResponse?.timings.total_ms,
        });
        timerRef.current = setTimeout(() => void capture(true), delay);
      }
    }
  };

  const startContinuous = () => {
    if (continuousRef.current) return;
    continuousRef.current = true;
    setContinuous(true);
    setStatus("Continuous local test started.");
    void capture(true);
  };

  const stopContinuous = () => {
    continuousRef.current = false;
    setContinuous(false);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setStatus("Continuous local test stopped.");
  };

  const prepareReport = () => {
    if (!result || !sessionRef.current) return;
    setPendingReport(buildAnonymousHazardReport(result, sessionRef.current.session_id));
    setHazardStatus("Confirm the anonymous test report. No evidence image will be stored.");
  };

  const confirmReport = async () => {
    if (!pendingReport) return;
    try {
      const response = await createHazardReport(backendUrl, pendingReport);
      setPendingReport(null);
      setHazardStatus(`Anonymous report created: ${response.hazard.id}`);
    } catch (error) {
      setHazardStatus(error instanceof Error ? `Report failed: ${error.message}` : "Report failed.");
    }
  };

  const readSign = async () => {
    if (!cameraRef.current || busy || continuousRef.current) return;
    setBusy(true);
    setExploreResult(null);
    setStatus("Capturing one high-quality image for local OCR…");
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 1, skipProcessing: false });
      if (!photo) throw new Error("The camera did not return an Explore image.");
      let imageUri = photo.uri;
      if (photo.width > 1600) {
        const context = ImageManipulator.manipulate(photo.uri);
        context.resize({ width: 1600, height: null });
        const rendered = await context.renderAsync();
        const resized = await rendered.saveAsync({ compress: 0.9, format: SaveFormat.JPEG });
        imageUri = resized.uri;
      }
      const response = await readText(backendUrl, imageUri);
      setExploreResult(response);
      setStatus("Local one-shot OCR complete.");
    } catch (error) {
      setStatus(error instanceof Error ? `Explore failed: ${error.message}` : "Explore failed.");
    } finally {
      setBusy(false);
    }
  };

  if (!permission) return <ActivityIndicator accessibilityLabel="Checking camera permission" />;
  if (!permission.granted) {
    return (
      <View style={styles.permissionPanel}>
        <Text>Camera permission is required for the Phase 6 backend test.</Text>
        <Pressable onPress={requestPermission} style={styles.button}><Text>Allow camera</Text></Pressable>
        <Pressable onPress={onBack} style={styles.button}><Text>Back</Text></Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.preview} onLayout={(event) => setPreviewSize(readLayout(event))}>
        <CameraView ref={cameraRef} facing="back" style={StyleSheet.absoluteFill} />
        <CoordinateMarkers geometry={result?.geometry ?? null} previewSize={previewSize} />
        {result ? (
          <SpatialOverlay
            detections={result.detections}
            geometry={result.geometry}
            overlay={result.overlay}
            previewHeight={previewSize.height}
            previewWidth={previewSize.width}
            surfaces={result.surfaces}
          />
        ) : null}
        {result ? (
          <DetectionOverlay
            detections={result.detections}
            geometry={result.geometry}
            previewHeight={previewSize.height}
            previewWidth={previewSize.width}
          />
        ) : null}
      </View>
      <ScrollView style={styles.controls} contentContainerStyle={styles.controlsContent}>
        <Text>DRISHTI local backend test harness</Text>
        <Text>{status}</Text>
        <Text>Successful frames: {successfulFrames}/5</Text>
        {result ? (
          <Text>
            Frame {result.frame_id} · {result.detections.length} boxes · age {Math.round(result.frame_age_ms)} ms · detect {result.timings.detection_ms?.toFixed(1) ?? "n/a"} ms
          </Text>
        ) : null}
        <Text>{hazardStatus} · synced count {nearbyCount}</Text>
        {pendingReport ? (
          <View style={styles.reportConfirmation}>
            <Text>Confirm report: {pendingReport.category} · {pendingReport.severity}</Text>
            <Pressable onPress={() => void confirmReport()} style={styles.button}><Text>Confirm anonymous report</Text></Pressable>
            <Pressable onPress={() => setPendingReport(null)} style={styles.button}><Text>Cancel report</Text></Pressable>
          </View>
        ) : (
          <Pressable disabled={!result} onPress={prepareReport} style={styles.button}><Text>Prepare hazard report</Text></Pressable>
        )}
        <Pressable disabled={busy || continuous} onPress={() => void readSign()} style={styles.button}><Text>Read sign once</Text></Pressable>
        {exploreResult ? (
          <Text>
            OCR {exploreResult.confidence_qualification} ({Math.round(exploreResult.confidence * 100)}%): {exploreResult.message}{exploreResult.route_numbers.length ? ` · routes ${exploreResult.route_numbers.join(", ")}` : ""}
          </Text>
        ) : null}
        {result ? (
          <Text>
            Corridor {result.overlay.preferred_corridor} · L {result.corridors.left_cost.toFixed(2)} · C {result.corridors.centre_cost.toFixed(2)} · R {result.corridors.right_cost.toFixed(2)}
          </Text>
        ) : null}
        {result ? (
          <Text>
            {result.guidance.action} · {result.guidance.level} · {result.guidance.reason_code} · speech {result.guidance.speak ? "YES" : "NO"} · haptic {result.guidance.haptic_pattern}
          </Text>
        ) : null}
        <Pressable disabled={!session || busy || continuous} onPress={() => void capture(false)} style={styles.button}>
          <Text>{busy ? "Working…" : "Capture and upload one frame"}</Text>
        </Pressable>
        <Pressable disabled={!session || continuous} onPress={startContinuous} style={styles.button}>
          <Text>Start continuous test</Text>
        </Pressable>
        <Pressable disabled={!continuous} onPress={stopContinuous} style={styles.button}>
          <Text>Stop continuous test</Text>
        </Pressable>
        <Pressable onPress={onBack} style={styles.button}><Text>End test</Text></Pressable>
      </ScrollView>
    </View>
  );
}

function CoordinateMarkers({ geometry, previewSize }: { geometry: FrameGeometry | null; previewSize: PreviewSize }) {
  if (!geometry || previewSize.width === 0 || previewSize.height === 0) return null;
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {TEST_POINTS.map((point) => {
        const mapped = mapNormalizedPointToPreview(point, {
          sourceWidth: geometry.source_width,
          sourceHeight: geometry.source_height,
          previewWidth: previewSize.width,
          previewHeight: previewSize.height,
          resizeMode: "COVER",
        });
        if (!mapped.visible) return null;
        return (
          <View
            key={point.id}
            style={[styles.marker, { left: mapped.x - 10, top: mapped.y - 10 }]}
          >
            <Text style={styles.markerText}>{point.id}</Text>
          </View>
        );
      })}
    </View>
  );
}

function readLayout(event: LayoutChangeEvent): PreviewSize {
  return {
    width: event.nativeEvent.layout.width,
    height: event.nativeEvent.layout.height,
  };
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#101010" },
  preview: { flex: 1, overflow: "hidden" },
  controls: { backgroundColor: "#eeeeee", maxHeight: "52%" },
  controlsContent: { gap: 8, padding: 12 },
  reportConfirmation: { gap: 8 },
  permissionPanel: { flex: 1, gap: 12, justifyContent: "center", padding: 24 },
  button: { alignItems: "center", backgroundColor: "#cccccc", minHeight: 44, justifyContent: "center", padding: 8 },
  marker: { alignItems: "center", backgroundColor: "#ff00ff", borderRadius: 10, height: 20, justifyContent: "center", position: "absolute", width: 20 },
  markerText: { color: "#000000", fontSize: 8, fontWeight: "700" },
});
