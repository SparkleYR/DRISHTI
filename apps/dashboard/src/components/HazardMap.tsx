import type { DashboardAccessibilityResponse, HazardRecord } from "@drishti/contracts";
import { FileSpreadsheet, MapPinned } from "lucide-react";
import { useEffect, useRef } from "react";

import { SectionCard, StatusBadge } from "./ui";

/**
 * Where the reported hazards are on the walking route.
 *
 * Coordinates arrive normalized 0-1 against a versioned local reference plane,
 * so the drawing scales to whatever size the canvas is given. Nothing here is
 * hardcoded: route segments and hazard pins both come from the backend.
 */
export function HazardMap(props: {
  accessibility: DashboardAccessibilityResponse;
  hazards: HazardRecord[];
}) {
  const route = props.accessibility.routes[0] ?? null;
  const mapped = props.hazards.filter((hazard) => hazard.map_coordinate);

  return (
    <SectionCard
      description="Reported obstacles plotted on the walking route. Advisory facilities information, not live navigation."
      eyebrow="Route"
      icon={MapPinned}
      id="hazard-map"
      title="Where the hazards are"
      trailing={
        <button
          type="button"
          onClick={() => exportCsv(props.hazards)}
          className="inline-flex min-h-9 items-center gap-2 rounded-sm border border-ink-200 bg-white px-3 text-[0.8rem] font-semibold text-ink-700 hover:border-amber-400 hover:bg-amber-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700"
        >
          <FileSpreadsheet size={14} aria-hidden="true" />
          Download report
        </button>
      }
    >
      <div className="grid gap-6 p-5 sm:p-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(280px,.7fr)]">
        <div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-[0.95rem] font-bold text-ink-900">{route?.route_name ?? "No route configured"}</h3>
            <StatusBadge tone={mapped.length > 0 ? "yellow" : "green"}>
              {mapped.length === 0 ? "No hazards on the route" : `${mapped.length} hazard${mapped.length === 1 ? "" : "s"} marked`}
            </StatusBadge>
          </div>
          <RouteCanvas accessibility={props.accessibility} hazards={props.hazards} />
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[0.8rem] text-ink-500" aria-label="Map legend">
            <Legend color="bg-amber-700" label="The walking route" />
            <Legend color="bg-red-600" label="Serious hazard" />
            <Legend color="bg-amber-500" label="Moderate hazard" />
            <Legend color="bg-emerald-600" label="Minor hazard" />
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-sm border border-ink-200 bg-ink-50 p-5">
            <p className="text-[0.8rem] font-semibold text-ink-500">How safe this route is today</p>
            <div className="mt-2 flex items-end justify-between gap-4">
              <span className="text-4xl font-bold tabular-nums text-ink-900">
                {route ? Math.round(route.score) : "—"}
                <span className="ml-1 text-[0.95rem] font-bold text-ink-400">/ 100</span>
              </span>
              <StatusBadge tone={scoreTone(route?.score)}>{describeScore(route?.score)}</StatusBadge>
            </div>
            <div
              className="mt-4 h-2.5 overflow-hidden rounded-sm bg-slate-200"
              role="progressbar"
              aria-label="Route safety score"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={route ? Math.round(route.score) : undefined}
            >
              <div className="h-full bg-amber-600" style={{ width: `${route?.score ?? 0}%` }} />
            </div>
            <p className="mt-3 text-xs leading-5 text-ink-500">
              {route?.active_hazard_count ?? 0} open · {route?.recurring_hazard_count ?? 0} keep coming back
            </p>
          </div>

          <div className="overflow-hidden rounded-sm border border-ink-200">
            <div className="border-b border-ink-200 bg-ink-50 px-4 py-3">
              <h3 className="text-[0.95rem] font-bold text-ink-900">Most reported problems</h3>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="bg-white text-[0.8rem] text-ink-500">
                <tr>
                  <th className="px-4 py-2 font-semibold">Problem</th>
                  <th className="px-4 py-2 text-right font-semibold">Times seen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-200">
                {frequency(props.hazards).map((item) => (
                  <tr key={item.category}>
                    <th className="px-4 py-2.5 text-left font-semibold text-ink-700">{item.category}</th>
                    <td className="px-4 py-2.5 text-right tabular-nums font-bold text-ink-900">{item.observations}</td>
                  </tr>
                ))}
                {props.hazards.length === 0 ? (
                  <tr>
                    <td className="px-4 py-5 text-center text-ink-400" colSpan={2}>
                      Nothing reported right now
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <p className="rounded-sm border border-amber-300 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-950" role="note">
            {props.accessibility.disclaimer}
          </p>
        </div>
      </div>
    </SectionCard>
  );
}

function RouteCanvas(props: { accessibility: DashboardAccessibilityResponse; hazards: HazardRecord[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let context: CanvasRenderingContext2D | null = null;
    try {
      context = canvas.getContext("2d");
    } catch {
      return;
    }
    if (!context) return;

    // Match the bitmap to the element's real size so the drawing stays crisp on
    // high-DPI screens instead of being stretched by CSS.
    const ratio = typeof window === "undefined" ? 1 : Math.min(window.devicePixelRatio || 1, 2);
    const cssWidth = canvas.clientWidth || 760;
    const cssHeight = canvas.clientHeight || 380;
    canvas.width = Math.round(cssWidth * ratio);
    canvas.height = Math.round(cssHeight * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    const width = cssWidth;
    const height = cssHeight;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#fdf9ed";
    context.fillRect(0, 0, width, height);

    context.strokeStyle = "#e7dfcf";
    context.lineWidth = 1;
    for (let index = 0; index <= 10; index += 1) {
      const x = (width / 10) * index;
      const y = (height / 10) * index;
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.stroke();
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }

    context.strokeStyle = "#b45309";
    context.lineWidth = 6;
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

  const mapped = props.hazards.filter((hazard) => hazard.map_coordinate).length;
  return (
    <canvas
      ref={canvasRef}
      className="mt-3 aspect-[2/1] w-full rounded-sm border border-ink-200 bg-[#fdf9ed]"
      role="img"
      aria-label={`Walking route with ${mapped} hazard${mapped === 1 ? "" : "s"} marked`}
    />
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`size-2.5 rounded-full ${color}`} aria-hidden="true" />
      {label}
    </span>
  );
}

function frequency(hazards: HazardRecord[]) {
  const counts = new Map<string, { category: string; observations: number }>();
  for (const hazard of hazards) {
    const item = counts.get(hazard.category) ?? { category: hazard.category, observations: 0 };
    item.observations += hazard.confirmation_count;
    counts.set(hazard.category, item);
  }
  return [...counts.values()].sort(
    (left, right) => right.observations - left.observations || left.category.localeCompare(right.category),
  );
}

function describeScore(score: number | undefined): string {
  if (score === undefined) return "No route";
  if (score >= 80) return "Good";
  if (score >= 50) return "Needs attention";
  return "Poor";
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

function exportCsv(hazards: HazardRecord[]) {
  const rows = [["report_id", "problem", "severity", "status", "times_seen", "map_x", "map_y"]];
  for (const hazard of hazards) {
    rows.push([
      hazard.id,
      hazard.category,
      hazard.severity,
      hazard.status,
      String(hazard.confirmation_count),
      hazard.map_coordinate ? String(hazard.map_coordinate.x) : "",
      hazard.map_coordinate ? String(hazard.map_coordinate.y) : "",
    ]);
  }
  const body = rows.map((row) => row.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([body], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "drishti-hazard-report.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}
