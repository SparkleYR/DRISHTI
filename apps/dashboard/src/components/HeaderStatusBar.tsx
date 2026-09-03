import type { HealthResponse } from "@drishti/contracts";
import { Accessibility, Cpu, RefreshCw, Server, ShieldCheck, Wifi, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

import type { EdgeStreamSnapshot } from "../types";
import { StatusBadge } from "./ui";

export function HeaderStatusBar(props: {
  edge: EdgeStreamSnapshot;
  health: HealthResponse | null;
  isRefreshing: boolean;
  onRefresh: () => void;
}) {
  const [fontScale, setFontScale] = useState(100);
  const [activeSection, setActiveSection] = useState("live-walk");
  const backendOnline = props.health?.status === "OK" || props.health?.status === "DEGRADED";
  const edgeLive = props.edge.connection === "LIVE";

  useEffect(() => {
    document.documentElement.style.fontSize = `${fontScale}%`;
    return () => { document.documentElement.style.fontSize = ""; };
  }, [fontScale]);

  const navigation = [
    ["live-walk", "Live Walk Stream"],
    ["ask-lock-guide", "Ask → Lock → Guide"],
    ["hazard-map", "Hazard Map"],
    ["hardware-logs", "System VRAM & Logs"],
    ["settings", "Settings"],
  ] as const;
  return (
    <header className="bg-white">
      <div className="border-b border-slate-200 bg-slate-100 text-xs text-slate-700">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-x-5 gap-y-1 px-4 py-1.5 sm:px-6 lg:px-8">
          <p className="font-medium">Official DRISHTI Local Accessibility Portal</p>
          <nav aria-label="Accessibility utilities" className="flex flex-wrap items-center gap-1 sm:gap-2">
            <a className="utility-link" href="#accessibility-statement">Screen Reader Access</a>
            <span aria-hidden="true" className="text-slate-300">|</span>
            <a className="utility-link" href="#dashboard-content">Skip to Main Content</a>
            <span aria-hidden="true" className="text-slate-300">|</span>
            <div className="inline-flex overflow-hidden rounded-sm border border-slate-300 bg-white" aria-label="Text size controls">
              <FontButton label="A−" onClick={() => setFontScale(90)} pressed={fontScale === 90} />
              <FontButton label="A" onClick={() => setFontScale(100)} pressed={fontScale === 100} />
              <FontButton label="A+" onClick={() => setFontScale(112)} pressed={fontScale === 112} />
            </div>
            <label className="sr-only" htmlFor="portal-language">Portal language</label>
            <select id="portal-language" className="min-h-7 rounded-sm border border-slate-300 bg-white px-2 text-xs font-medium text-slate-800" defaultValue="en">
              <option value="en">English</option>
              <option value="hi">हिन्दी</option>
            </select>
          </nav>
        </div>
      </div>
      <div className="border-b border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.06)]">
        <div className="mx-auto flex max-w-[1480px] flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-12 shrink-0 place-items-center rounded-sm border border-amber-300 bg-amber-50 text-amber-700" aria-hidden="true">
            <Accessibility size={27} strokeWidth={1.9} />
          </span>
          <span className="h-11 w-px bg-slate-300" aria-hidden="true" />
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-bold text-slate-900">DRISHTI</h1>
            <p className="mt-0.5 text-sm font-medium text-slate-600">Edge Operations Portal</p>
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
          <StatusBadge tone={props.health?.compute.selected_device === "CUDA" ? "green" : "yellow"}>
            <Cpu size={14} aria-hidden="true" /> RTX 4060 {props.health?.compute.selected_device === "CUDA" ? "CUDA ready" : "unavailable"}
          </StatusBadge>
          <StatusBadge tone={props.health?.walk_mode_available ? "green" : "red"}>
            <ShieldCheck size={14} aria-hidden="true" /> Walk mode {props.health?.walk_mode_available ? "ready" : "blocked"}
          </StatusBadge>
          <button
            type="button"
            onClick={props.onRefresh}
            className="ml-0 inline-flex min-h-9 items-center gap-2 rounded-sm border border-amber-600 bg-amber-600 px-3 text-sm font-semibold text-white hover:bg-amber-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700 lg:ml-1"
          >
            <RefreshCw className={props.isRefreshing ? "animate-spin" : ""} size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>
      </div>
      <nav aria-label="Primary navigation" className="border-b border-slate-300 bg-white">
        <div className="mx-auto flex max-w-[1480px] overflow-x-auto px-4 sm:px-6 lg:px-8">
          {navigation.map(([id, label]) => (
            <a
              className={`shrink-0 border-b-2 px-3 py-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-amber-700 ${activeSection === id ? "border-amber-600 font-semibold text-amber-700" : "border-transparent font-medium text-slate-700 hover:border-slate-300 hover:text-slate-950"}`}
              href={`#${id}`}
              key={id}
              onClick={() => setActiveSection(id)}
            >
              {label}
            </a>
          ))}
        </div>
      </nav>
      <div className="border-b border-slate-200 bg-[#fcfbf9]">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-2 px-4 py-2 text-xs text-slate-600 sm:px-6 lg:px-8">
          <span>Edge endpoint: <code className="font-semibold text-slate-800">{props.edge.endpoint}</code></span>
          <span>Live FPS: <strong className="tabular-nums text-slate-900">{props.edge.fps === null ? "Not exposed" : props.edge.fps.toFixed(1)}</strong></span>
        </div>
      </div>
    </header>
  );
}

function FontButton(props: { label: string; onClick: () => void; pressed: boolean }) {
  return (
    <button
      aria-label={`Set text size ${props.label}`}
      aria-pressed={props.pressed}
      className={`min-h-7 min-w-8 border-r border-slate-300 px-1.5 font-semibold last:border-r-0 ${props.pressed ? "bg-amber-50 text-amber-800" : "bg-white text-slate-700 hover:bg-slate-50"}`}
      onClick={props.onClick}
      type="button"
    >
      {props.label}
    </button>
  );
}
