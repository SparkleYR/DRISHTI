import type { DashboardAccessibilityResponse, HazardRecord } from "@drishti/contracts";
import { Download, FileJson, FileSpreadsheet, MapPinned } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

import { SectionCard, StatusBadge } from "./ui";

export function AccessibilityAnalytics(props: {
  accessibility: DashboardAccessibilityResponse;
  hazards: HazardRecord[];
}) {
  const route = props.accessibility.routes[0] ?? null;
  const frequency = useMemo(() => hazardFrequency(props.hazards), [props.hazards]);
  return (
    <SectionCard
      description="Versioned local-coordinate hazard intelligence. Scores are advisory facilities data, never live navigation instructions."
      eyebrow="Module C"
      icon={MapPinned}
      id="hazard-map"
      title="Accessibility Analytics & Digital Twin"
      trailing={
        <div className="flex flex-wrap gap-2">
          <ExportButton icon={FileSpreadsheet} label="Export CSV" onClick={() => exportCsv(props.hazards)} />
          <ExportButton icon={FileJson} label="Export JSON" onClick={() => exportJson(props.accessibility, props.hazards)} />
        </div>
      }
    >
      <div className="grid gap-6 p-5 sm:p-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,.8fr)]">
        <div>
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-slate-950">Normalized hazard coordinate plot</h3>
              <p className="mt-1 text-xs text-slate-500">Map space 0–1 · versioned local reference</p>
            </div>
            <StatusBadge tone="blue">{props.hazards.length} active records</StatusBadge>
          </div>
          <HazardCanvas accessibility={props.accessibility} hazards={props.hazards} />
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-600" aria-label="Hazard map legend">
            <Legend color="bg-red-600" label="Critical / high" />
            <Legend color="bg-amber-500" label="Medium" />
            <Legend color="bg-emerald-600" label="Low" />
            <Legend color="bg-amber-700" label="Route segment" />
          </div>
        </div>
        <div className="space-y-4">
          <div className="rounded-sm border border-slate-300 bg-[#fcfbf9] p-5">
            <p className="text-xs font-semibold text-slate-600">Overall route accessibility</p>
            <div className="mt-2 flex items-end justify-between gap-4">
              <div><span className="text-4xl font-bold tabular-nums text-slate-950">{route ? route.score.toFixed(1) : "—"}</span><span className="ml-1 text-sm font-bold text-slate-500">/ 100</span></div>
              <StatusBadge tone={scoreTone(route?.score)}>{route ? formatBand(route.band) : "No route"}</StatusBadge>
            </div>
            <div className="mt-4 h-2.5 overflow-hidden rounded-sm bg-slate-200" role="progressbar" aria-label="Overall route accessibility score" aria-valuemin={0} aria-valuemax={100} aria-valuenow={route?.score}>
              <div className="h-full bg-amber-600" style={{ width: `${route?.score ?? 0}%` }} />
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-600">{route?.route_name ?? "No versioned route configured"} · {route?.active_hazard_count ?? 0} active · {route?.recurring_hazard_count ?? 0} recurring</p>
          </div>
          <div className="overflow-hidden rounded-sm border border-slate-300">
            <div className="border-b border-slate-300 bg-[#fcfbf9] px-4 py-3">
              <h3 className="text-sm font-bold text-slate-950">Hazard frequency</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-white text-xs text-slate-600"><tr><th className="px-4 py-2 font-semibold">Category</th><th className="px-4 py-2 text-right font-semibold">Reports</th><th className="px-4 py-2 text-right font-semibold">Observations</th></tr></thead>
                <tbody className="divide-y divide-slate-200">
                  {frequency.map((item) => <tr key={item.category}><th className="px-4 py-2.5 font-semibold text-slate-800">{item.category}</th><td className="px-4 py-2.5 text-right tabular-nums text-slate-700">{item.reports}</td><td className="px-4 py-2.5 text-right tabular-nums font-bold text-slate-950">{item.observations}</td></tr>)}
                  {frequency.length === 0 ? <tr><td className="px-4 py-5 text-center text-slate-500" colSpan={3}>No active hazard records</td></tr> : null}
                </tbody>
              </table>
            </div>
          </div>
          <p className="rounded-sm border border-amber-300 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-950" role="note">{props.accessibility.disclaimer}</p>
        </div>
      </div>
    </SectionCard>
  );
}

function HazardCanvas(props: { accessibility: DashboardAccessibilityResponse; hazards: HazardRecord[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let context: CanvasRenderingContext2D | null = null;
    try { context = canvas.getContext("2d"); } catch { return; }
    if (!context) return;
    const width = canvas.width;
    const height = canvas.height;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#fdf9ed";
    context.fillRect(0, 0, width, height);
    context.strokeStyle = "#e7dfcf";
    context.lineWidth = 1;
    for (let index = 0; index <= 10; index += 1) {
      const x = (width / 10) * index;
      const y = (height / 10) * index;
      context.beginPath(); context.moveTo(x, 0); context.lineTo(x, height); context.stroke();
      context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke();
    }
    context.strokeStyle = "#b45309";
    context.lineWidth = 5;
    context.lineCap = "round";
    for (const route of props.accessibility.routes) {
      for (const segment of route.segments) {
        context.beginPath();
        context.moveTo(segment.segment.start.x * width, segment.segment.start.y * height);
        context.lineTo(segment.segment.end.x * width, segment.segment.end.y * height);
        context.stroke();
      }
    }
    for (const hazard of props.hazards) {
      if (!hazard.map_coordinate) continue;
      const x = hazard.map_coordinate.x * width;
      const y = hazard.map_coordinate.y * height;
      context.beginPath();
      context.fillStyle = severityColor(hazard.severity);
      context.arc(x, y, 8 + Math.min(hazard.confirmation_count, 6), 0, Math.PI * 2);
      context.fill();
      context.lineWidth = 3;
      context.strokeStyle = "#ffffff";
      context.stroke();
    }
  }, [props.accessibility, props.hazards]);
  return (
    <canvas
      ref={canvasRef}
      width={760}
      height={380}
      className="mt-3 aspect-[2/1] w-full rounded-sm border border-slate-300 bg-[#fdf9ed]"
      role="img"
      aria-label={`Digital twin coordinate plot with ${props.hazards.filter((hazard) => hazard.map_coordinate).length} mapped active hazards`}
    />
  );
}

function ExportButton(props: { icon: typeof Download; label: string; onClick: () => void }) {
  const Icon = props.icon;
  return <button type="button" onClick={props.onClick} className="inline-flex min-h-9 items-center gap-2 rounded-sm border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-800 hover:border-amber-400 hover:bg-amber-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700"><Icon size={14} aria-hidden="true" />{props.label}</button>;
}

function Legend({ color, label }: { color: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span className={`size-2.5 rounded-full ${color}`} aria-hidden="true" />{label}</span>;
}

function hazardFrequency(hazards: HazardRecord[]) {
  const counts = new Map<string, { category: string; observations: number; reports: number }>();
  for (const hazard of hazards) {
    const item = counts.get(hazard.category) ?? { category: hazard.category, observations: 0, reports: 0 };
    item.reports += 1;
    item.observations += hazard.confirmation_count;
    counts.set(hazard.category, item);
  }
  return [...counts.values()].sort((left, right) => right.observations - left.observations || left.category.localeCompare(right.category));
}

function exportCsv(hazards: HazardRecord[]) {
  const rows = [["id", "category", "severity", "status", "confidence", "observations", "map_id", "map_version", "x", "y"]];
  for (const hazard of hazards) rows.push([
    hazard.id,
    hazard.category,
    hazard.severity,
    hazard.status,
    String(hazard.confidence),
    String(hazard.confirmation_count),
    hazard.map_coordinate?.map_id ?? "",
    hazard.map_coordinate?.map_version ?? "",
    hazard.map_coordinate ? String(hazard.map_coordinate.x) : "",
    hazard.map_coordinate ? String(hazard.map_coordinate.y) : "",
  ]);
  download("drishti-hazards.csv", rows.map((row) => row.map(csvCell).join(",")).join("\n"), "text/csv;charset=utf-8");
}

function exportJson(accessibility: DashboardAccessibilityResponse, hazards: HazardRecord[]) {
  download("drishti-accessibility-report.json", JSON.stringify({ exported_at: new Date().toISOString(), accessibility, hazards }, null, 2), "application/json");
}

function download(filename: string, body: string, mime: string) {
  const url = URL.createObjectURL(new Blob([body], { type: mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

function formatBand(value: string): string {
  return value.toLowerCase().replaceAll("_", " ");
}

function scoreTone(score: number | undefined): "green" | "red" | "slate" | "yellow" {
  if (score === undefined) return "slate";
  if (score >= 80) return "green";
  if (score >= 50) return "yellow";
  return "red";
}

function severityColor(severity: HazardRecord["severity"]): string {
  if (severity === "CRITICAL" || severity === "HIGH") return "#dc2626";
  if (severity === "MEDIUM") return "#d97706";
  return "#059669";
}
