import type { TargetTrackingTelemetry } from "@drishti/contracts";
import { AlertOctagon, Clock3, Crosshair, LockKeyhole, Target } from "lucide-react";

import type { EdgeStreamSnapshot } from "../types";
import { SectionCard, StatusBadge } from "./ui";

const IDLE: TargetTrackingTelemetry = {
  tracking_state: "IDLE",
  target_name: null,
  clock_direction: null,
  target_center: null,
  confidence: null,
  is_safety_overridden: false,
  speech: "",
  speak: false,
  haptic_pattern: "NONE",
};

export function TargetLockMonitor({ edge }: { edge: EdgeStreamSnapshot }) {
  const target = edge.targetTracking ?? edge.frameAnalysis?.target_tracking ?? IDLE;
  const stateTone = target.tracking_state === "LOCKED_TRACKING"
    ? "green"
    : target.tracking_state === "TARGET_LOST"
      ? "red"
      : target.tracking_state === "LOCATING"
        ? "yellow"
        : "slate";
  return (
    <SectionCard
      className="min-w-0"
      description="On-demand VLM localization and conventional frame-to-frame tracking handoff."
      eyebrow="Module B"
      icon={Target}
      id="ask-lock-guide"
      title="Ask → Lock → Guide"
      trailing={<StatusBadge tone={stateTone}>{target.tracking_state.replace("_", " ")}</StatusBadge>}
    >
      <div className="space-y-4 p-5 sm:p-6">
        {target.is_safety_overridden ? (
          <div className="flex gap-3 rounded-sm border border-red-300 bg-red-50 p-3 text-red-950" role="alert">
            <AlertOctagon className="mt-0.5 shrink-0" size={19} aria-hidden="true" />
            <div><p className="text-sm font-bold">Safety override active</p><p className="mt-0.5 text-xs leading-5">Risk Engine guidance has preempted all target speech and haptic cues.</p></div>
          </div>
        ) : null}
        <dl className="divide-y divide-slate-200 rounded-sm border border-slate-300">
          <Detail icon={LockKeyhole} label="Locked target" value={target.target_name ?? "No target locked"} />
          <Detail icon={Clock3} label="Clock direction" value={target.clock_direction ?? "—"} />
          <Detail
            icon={Crosshair}
            label="Normalized centre"
            value={target.target_center ? `x ${target.target_center.x.toFixed(3)} · y ${target.target_center.y.toFixed(3)}` : "—"}
          />
        </dl>
        <div className="rounded-sm border border-slate-300 bg-[#fcfbf9] p-4">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="font-semibold text-slate-700">Tracker confidence</span>
            <strong className="tabular-nums text-slate-950">{target.confidence === null ? "Not available" : `${Math.round(target.confidence * 100)}%`}</strong>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-sm bg-slate-200" role="progressbar" aria-label="Tracker confidence" aria-valuemin={0} aria-valuemax={100} aria-valuenow={target.confidence === null ? undefined : Math.round(target.confidence * 100)}>
            <div className="h-full bg-amber-600 transition-[width]" style={{ width: `${(target.confidence ?? 0) * 100}%` }} />
          </div>
        </div>
        <p className="text-xs leading-5 text-slate-500">Target telemetry becomes live only when a Walk session publishes frame analysis. VLM remains unloaded during continuous tracking.</p>
      </div>
    </SectionCard>
  );
}

function Detail(props: { icon: typeof LockKeyhole; label: string; value: string }) {
  const Icon = props.icon;
  return (
    <div className="grid grid-cols-[28px_1fr] gap-x-2 px-4 py-3">
      <Icon className="mt-0.5 text-slate-500" size={16} aria-hidden="true" />
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <dt className="text-xs font-semibold text-slate-600">{props.label}</dt>
        <dd className="text-sm font-bold text-slate-950">{props.value}</dd>
      </div>
    </div>
  );
}
