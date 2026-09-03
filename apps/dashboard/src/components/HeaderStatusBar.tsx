import type { HealthResponse } from "@drishti/contracts";
import { Activity, Cpu, RefreshCw, Server, ShieldCheck, Wifi, WifiOff } from "lucide-react";

import type { EdgeStreamSnapshot } from "../types";
import { StatusBadge } from "./ui";

export function HeaderStatusBar(props: {
  edge: EdgeStreamSnapshot;
  health: HealthResponse | null;
  isRefreshing: boolean;
  onRefresh: () => void;
}) {
  const backendOnline = props.health?.status === "OK" || props.health?.status === "DEGRADED";
  const edgeLive = props.edge.connection === "LIVE";
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-[1480px] flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-blue-700 text-white" aria-hidden="true">
            <Activity size={24} />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-blue-700">Local accessibility operations</p>
            <h1 className="truncate text-xl font-extrabold tracking-tight text-slate-950 sm:text-2xl">DRISHTI Edge Monitoring System</h1>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={backendOnline ? "green" : "red"}>
            <Server size={14} aria-hidden="true" /> REST {backendOnline ? "connected" : "offline"}
          </StatusBadge>
          <StatusBadge tone={edgeLive ? "green" : props.edge.connection === "CONNECTING" ? "yellow" : "slate"}>
            {edgeLive ? <Wifi size={14} aria-hidden="true" /> : <WifiOff size={14} aria-hidden="true" />}
            Edge {props.edge.connection.toLowerCase()}
          </StatusBadge>
          <StatusBadge tone={props.health?.compute.selected_device === "CUDA" ? "blue" : "yellow"}>
            <Cpu size={14} aria-hidden="true" /> RTX 4060 {props.health?.compute.selected_device === "CUDA" ? "CUDA ready" : "unavailable"}
          </StatusBadge>
          <StatusBadge tone={props.health?.walk_mode_available ? "green" : "red"}>
            <ShieldCheck size={14} aria-hidden="true" /> Walk mode {props.health?.walk_mode_available ? "ready" : "blocked"}
          </StatusBadge>
          <button
            type="button"
            onClick={props.onRefresh}
            className="ml-0 inline-flex min-h-9 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-bold text-slate-800 shadow-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 lg:ml-1"
          >
            <RefreshCw className={props.isRefreshing ? "animate-spin" : ""} size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>
      <div className="border-t border-slate-100 bg-slate-50">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-2 px-4 py-2 text-xs text-slate-600 sm:px-6 lg:px-8">
          <span>Edge endpoint: <code className="font-semibold text-slate-800">{props.edge.endpoint}</code></span>
          <span>Live FPS: <strong className="tabular-nums text-slate-900">{props.edge.fps === null ? "Not exposed" : props.edge.fps.toFixed(1)}</strong></span>
        </div>
      </div>
    </header>
  );
}
