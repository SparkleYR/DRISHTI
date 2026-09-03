import type { DetectionResult, FrameAnalysisResponse } from "@drishti/contracts";
import { EyeOff, Radio, ShieldAlert, ShieldCheck, Video } from "lucide-react";

import type { EdgeStreamSnapshot } from "../types";
import { Metric, SectionCard, StatusBadge } from "./ui";

export function LiveWalkMonitor({ edge }: { edge: EdgeStreamSnapshot }) {
  const frame = edge.frameAnalysis;
  const risk = riskState(frame);
  const inferenceMs = frame
    ? (frame.timings.detection_ms ?? 0) + (frame.timings.segmentation_ms ?? 0)
    : null;
  return (
    <SectionCard
      className="min-w-0 lg:col-span-2"
      description="Latest edge frame and deterministic mobility-risk output. Frames are displayed only when an approved stream supplies them."
      eyebrow="Module A"
      icon={Video}
      id="live-walk"
      title="Live Walk Loop & Stream Monitor"
      trailing={<RiskBadge state={risk} />}
    >
      <div className="grid gap-5 p-5 sm:p-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(250px,.75fr)]">
        <div>
          <div className="relative aspect-video overflow-hidden rounded-sm border border-slate-300 bg-[#f8f4ea]" aria-label="Live walking frame monitor">
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#ded7ca_1px,transparent_1px),linear-gradient(to_bottom,#ded7ca_1px,transparent_1px)] bg-[size:10%_10%] opacity-55" aria-hidden="true" />
            {edge.frameUrl ? <img className="absolute inset-0 size-full object-contain" src={edge.frameUrl} alt="Latest live walking frame" /> : (
              <div className="absolute inset-0 grid place-items-center p-6 text-center">
                <div className="max-w-sm rounded-sm border border-slate-300 bg-white px-5 py-4">
                  <EyeOff className="mx-auto text-slate-500" size={28} aria-hidden="true" />
                  <p className="mt-2 text-sm font-bold text-slate-800">Live frame unavailable</p>
                  <p className="mt-1 text-xs leading-5 text-slate-600">The approved backend does not currently expose a global video stream. No placeholder image or stored walking frame is shown.</p>
                </div>
              </div>
            )}
            {frame?.detections.map((detection) => <DetectionOverlay detection={detection} key={`${detection.track_id ?? "none"}-${detection.label}`} />)}
            <div className="absolute left-3 top-3">
              <StatusBadge tone={edge.connection === "LIVE" ? "green" : "slate"}>
                <Radio size={13} aria-hidden="true" /> {edge.connection === "LIVE" ? "Live edge feed" : "Awaiting stream"}
              </StatusBadge>
            </div>
          </div>
          <p className="mt-2 text-xs text-slate-500">Privacy-preserving monitor · no continuous frame persistence · normalized overlay coordinates</p>
        </div>
        <div className="grid content-start gap-3 sm:grid-cols-3 xl:grid-cols-1">
          <Metric label="Inference time" value={formatMs(inferenceMs)} suffix="ms" hint="Detector + segmenter" />
          <Metric label="Risk engine time" value={formatMs(frame?.timings.risk_ms)} suffix="ms" hint="Scoring and decision" />
          <Metric label="Total frame time" value={formatMs(frame?.timings.total_ms)} suffix="ms" hint={frame ? `Frame ${frame.frame_id}` : "No live frame"} />
          <div className={`rounded-sm border px-4 py-4 sm:col-span-3 xl:col-span-1 ${riskPanelClass(risk)}`}>
            <div className="flex items-center gap-2">
              {risk === "CLEAR" ? <ShieldCheck size={20} aria-hidden="true" /> : <ShieldAlert size={20} aria-hidden="true" />}
              <p className="text-xs font-semibold">Risk engine state</p>
            </div>
            <p className="mt-2 text-xl font-bold">{risk}</p>
            <p className="mt-1 text-xs leading-5">{frame?.guidance.speech || "No current risk decision is being streamed."}</p>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

type RiskState = "CAUTION" | "CLEAR" | "CRITICAL_STOP" | "NO_DATA";

function riskState(frame: FrameAnalysisResponse | null): RiskState {
  if (!frame) return "NO_DATA";
  if (frame.guidance.action === "CLEAR") return "CLEAR";
  if (frame.guidance.action === "STOP") return "CRITICAL_STOP";
  return "CAUTION";
}

function RiskBadge({ state }: { state: RiskState }) {
  const tone = state === "CLEAR" ? "green" : state === "CRITICAL_STOP" ? "red" : state === "CAUTION" ? "yellow" : "slate";
  return <StatusBadge tone={tone}>{state.replace("_", " ")}</StatusBadge>;
}

function DetectionOverlay({ detection }: { detection: DetectionResult }) {
  const className = detection.risk_level === "CRITICAL" || detection.risk_level === "HIGH"
    ? "border-red-600 bg-red-500/10 text-red-900"
    : detection.risk_level === "WARN"
      ? "border-amber-500 bg-amber-400/10 text-amber-950"
      : "border-emerald-600 bg-emerald-500/10 text-emerald-900";
  return (
    <div
      className={`pointer-events-none absolute border-2 ${className}`}
      style={{
        left: `${detection.bbox.x1 * 100}%`,
        top: `${detection.bbox.y1 * 100}%`,
        width: `${(detection.bbox.x2 - detection.bbox.x1) * 100}%`,
        height: `${(detection.bbox.y2 - detection.bbox.y1) * 100}%`,
      }}
    >
      <span className="absolute -top-6 left-[-2px] whitespace-nowrap rounded-t bg-current px-1.5 py-1 text-[10px] font-bold text-white [color:inherit]">
        <span className="text-white">{detection.label} · {Math.round(detection.confidence * 100)}%</span>
      </span>
    </div>
  );
}

function formatMs(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(1) : "—";
}

function riskPanelClass(state: RiskState): string {
  if (state === "CLEAR") return "border-emerald-200 bg-emerald-50 text-emerald-900";
  if (state === "CRITICAL_STOP") return "border-red-300 bg-red-50 text-red-950";
  if (state === "CAUTION") return "border-amber-300 bg-amber-50 text-amber-950";
  return "border-slate-200 bg-slate-50 text-slate-700";
}
