import type { HealthResponse, ModuleHealth } from "@drishti/contracts";
import { BrainCircuit, Cpu, Database, HardDrive, MemoryStick, ServerCog } from "lucide-react";

import type { EdgeStreamSnapshot } from "../types";
import { SectionCard, StatusBadge } from "./ui";

export function HardwareModelManager(props: {
  edge: EdgeStreamSnapshot;
  health: HealthResponse;
}) {
  const vram = props.edge.vram;
  const usedPercent = vram ? Math.min(100, Math.max(0, (vram.usedMib / vram.totalMib) * 100)) : 0;
  return (
    <SectionCard
      description="Local compute readiness and resident-model state. Hardware counters remain blank when the backend does not expose them."
      eyebrow="Module D"
      icon={ServerCog}
      id="hardware-logs"
      title="Edge Hardware & Model VRAM Manager"
      trailing={<StatusBadge tone={props.health.compute.selected_device === "CUDA" ? "green" : "red"}><Cpu size={13} aria-hidden="true" />{props.health.compute.device_name ?? "Compute unavailable"}</StatusBadge>}
    >
      <div className="grid gap-4 p-5 sm:grid-cols-2 sm:p-6 xl:grid-cols-4">
        <div className="rounded-sm border border-slate-300 bg-[#fcfbf9] p-4 sm:col-span-2">
          <div className="flex items-start justify-between gap-4">
            <div className="flex gap-3"><span className="grid size-9 place-items-center rounded-sm border border-amber-200 bg-amber-50 text-amber-700"><MemoryStick size={19} aria-hidden="true" /></span><div><p className="text-sm font-bold text-slate-950">RTX 4060 VRAM</p><p className="mt-0.5 text-xs text-slate-500">On-device CUDA memory</p></div></div>
            <StatusBadge tone={vram ? usedPercent > 90 ? "red" : usedPercent > 75 ? "yellow" : "green" : "slate"}>{vram ? `${usedPercent.toFixed(0)}% used` : "Not exposed"}</StatusBadge>
          </div>
          <div className="mt-5 h-3 overflow-hidden rounded-sm bg-slate-200" role="progressbar" aria-label="RTX 4060 VRAM used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={vram ? Math.round(usedPercent) : undefined}>
            <div className="h-full bg-amber-600 transition-[width]" style={{ width: `${usedPercent}%` }} />
          </div>
          <div className="mt-2 flex justify-between gap-3 text-xs font-semibold text-slate-600">
            <span>{vram ? `${Math.round(vram.usedMib)} MiB used` : "— MiB used"}</span>
            <span>{vram ? `${Math.round(vram.freeMib)} MiB free` : "— MiB free"}</span>
          </div>
        </div>
        <ModelStatus icon={Cpu} label="YOLO11n" module={props.health.models.detector} readyLabel="ACTIVE" />
        <ModelStatus icon={HardDrive} label="SegFormer-B0" module={props.health.models.segmentation} readyLabel="ACTIVE" />
        <ModelStatus icon={BrainCircuit} label="Moondream2 VLM" module={props.health.models.vlm} readyLabel="STANDBY / UNLOADED" />
        <ModelStatus icon={Database} label="SQLite" module={props.health.database} readyLabel="READY" />
      </div>
    </SectionCard>
  );
}

function ModelStatus(props: {
  icon: typeof Cpu;
  label: string;
  module: ModuleHealth;
  readyLabel: string;
}) {
  const Icon = props.icon;
  const ready = props.module.status === "READY";
  return (
    <div className="rounded-sm border border-slate-300 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="grid size-9 place-items-center rounded-sm border border-slate-200 bg-[#fcfbf9] text-slate-700"><Icon size={18} aria-hidden="true" /></span>
        <StatusBadge tone={ready ? "green" : props.module.status === "DEGRADED" ? "yellow" : "red"}>{ready ? props.readyLabel : props.module.status}</StatusBadge>
      </div>
      <p className="mt-4 text-sm font-bold text-slate-950">{props.label}</p>
      <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{props.module.detail ?? "Local model health reported by backend."}</p>
    </div>
  );
}
