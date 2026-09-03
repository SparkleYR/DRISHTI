import type { FrameAnalysisResponse, TargetTrackingTelemetry } from "@drishti/contracts";
import { useEffect, useRef, useState } from "react";

import type { EdgeStreamSnapshot, VramSnapshot } from "../types";

const DEFAULT_STREAM_URL = "ws://localhost:8000/ws/stream";

interface StreamEnvelope {
  fps?: number;
  frame_analysis?: FrameAnalysisResponse;
  frame_base64?: string;
  vram_free_mib?: number;
  vram_total_mib?: number;
  vram_used_mib?: number;
}

function initialSnapshot(endpoint: string): EdgeStreamSnapshot {
  return {
    connection: "CONNECTING",
    endpoint,
    fps: null,
    frameAnalysis: null,
    frameUrl: null,
    lastEventAt: null,
    targetTracking: null,
    vram: null,
  };
}

export function useEdgeStream(): EdgeStreamSnapshot {
  const endpoint = import.meta.env.VITE_STREAM_WS_URL || DEFAULT_STREAM_URL;
  const [snapshot, setSnapshot] = useState<EdgeStreamSnapshot>(() => initialSnapshot(endpoint));
  const frameUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof WebSocket === "undefined") {
      setSnapshot((current) => ({ ...current, connection: "UNAVAILABLE" }));
      return;
    }

    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | undefined;

    const connect = () => {
      if (disposed) return;
      setSnapshot((current) => ({ ...current, connection: "CONNECTING" }));
      socket = new WebSocket(endpoint);
      socket.binaryType = "blob";

      socket.onopen = () => {
        setSnapshot((current) => ({ ...current, connection: "LIVE" }));
      };
      socket.onerror = () => {
        setSnapshot((current) => ({ ...current, connection: "UNAVAILABLE" }));
      };
      socket.onclose = () => {
        if (disposed) return;
        setSnapshot((current) => ({ ...current, connection: "UNAVAILABLE" }));
        reconnectTimer = setTimeout(connect, 5_000);
      };
      socket.onmessage = (event) => {
        if (event.data instanceof Blob) {
          if (frameUrlRef.current) URL.revokeObjectURL(frameUrlRef.current);
          frameUrlRef.current = URL.createObjectURL(event.data);
          setSnapshot((current) => ({
            ...current,
            connection: "LIVE",
            frameUrl: frameUrlRef.current,
            lastEventAt: new Date().toISOString(),
          }));
          return;
        }
        if (typeof event.data !== "string") return;
        try {
          const payload = JSON.parse(event.data) as StreamEnvelope | FrameAnalysisResponse | TargetTrackingTelemetry;
          if (!payload || typeof payload !== "object") return;
          const envelope = payload as StreamEnvelope;
          const frameAnalysis = "guidance" in payload
            ? payload as FrameAnalysisResponse
            : envelope.frame_analysis ?? null;
          const targetTracking = "tracking_state" in payload
            ? payload as TargetTrackingTelemetry
            : frameAnalysis?.target_tracking ?? null;
          const vram = readVram(envelope);
          const frameUrl = envelope.frame_base64
            ? `data:image/jpeg;base64,${envelope.frame_base64}`
            : null;
          setSnapshot((current) => ({
            ...current,
            connection: "LIVE",
            fps: finiteOrNull(envelope.fps) ?? current.fps,
            frameAnalysis: frameAnalysis ?? current.frameAnalysis,
            frameUrl: frameUrl ?? current.frameUrl,
            lastEventAt: new Date().toISOString(),
            targetTracking: targetTracking ?? current.targetTracking,
            vram: vram ?? current.vram,
          }));
        } catch {
          // Ignore non-JSON text messages; the connection remains observable.
        }
      };
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
      if (frameUrlRef.current) URL.revokeObjectURL(frameUrlRef.current);
    };
  }, [endpoint]);

  return snapshot;
}

function finiteOrNull(value: number | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readVram(payload: StreamEnvelope): VramSnapshot | null {
  const usedMib = finiteOrNull(payload.vram_used_mib);
  const freeMib = finiteOrNull(payload.vram_free_mib);
  const totalMib = finiteOrNull(payload.vram_total_mib);
  if (usedMib === null || freeMib === null || totalMib === null || totalMib <= 0) return null;
  return { usedMib, freeMib, totalMib };
}
