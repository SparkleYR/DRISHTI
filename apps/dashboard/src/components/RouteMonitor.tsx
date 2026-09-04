import type { DashboardAccessibilityResponse, HazardRecord } from "@drishti/contracts";

import type { ActiveWalkSession } from "../api/health";
import { FileSpreadsheet, Radio } from "lucide-react";
import { useEffect, useRef } from "react";

import { SectionCard, StatusBadge } from "./ui";

/**
 * Live view of the walking route: where obstacles have been reported, and where
 * each walker who is out right now has got to.
 *
 * Honest limitation, stated on screen: DRISHTI has no indoor positioning
 * (DECISIONS.md D-057). A walker's spot on the line is estimated purely from how
 * long they have been walking, so it advances smoothly and reacts to their live
 * guidance and signal, but it is not a measured position. Route geometry and
 * hazard pins are real backend data; nothing here is hardcoded except the
 * display-pacing constants below, in the spirit of POLL_INTERVAL_MS.
 */
const EXPECTED_WALK_MS = 6 * 60_000; // a full pass of the demo hall, for pacing the token only
const SIGNAL_STALE_MS = 10_000; // matches WalkersNow: no frame this long = device quiet

export function RouteMonitor(props: {
  accessibility: DashboardAccessibilityResponse;
  hazards: HazardRecord[];
  now: number;
  sessions: ActiveWalkSession[];
}) {
  const route = props.accessibility.routes[0] ?? null;
  const mapped = props.hazards.filter((hazard) => hazard.map_coordinate);
  const live = props.sessions.length;

  return (
    <SectionCard
      description="Each walker who is out now, shown along the route. Position is estimated from time walked, not measured — DRISHTI has no indoor positioning."
      eyebrow="Live"
      icon={Radio}
      id="route-monitor"
      title="On the route now"
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
            <StatusBadge tone={live > 0 ? "green" : "slate"}>
              {live === 0 ? "Nobody on the route" : `${live} walker${live === 1 ? "" : "s"} out`}
            </StatusBadge>
          </div>
          <RouteCanvas
            accessibility={props.accessibility}
            hazards={props.hazards}
            now={props.now}
            sessions={props.sessions}
          />
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[0.8rem] text-ink-500" aria-label="Map legend">
            <Legend color="bg-amber-700" label="The walking route" />
            <Legend color="bg-emerald-600" label="Walker — clear" />
            <Legend color="bg-amber-500" label="Walker — caution" />
            <Legend color="bg-red-600" label="Walker — stop / hazard" />
            <Legend color="bg-ink-300" label="Walker — no signal" />
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
              className="mt-4 h-2.5 overflow-hidden rounded-sm bg-ink-200"
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
              <h3 className="text-[0.95rem] font-bold text-ink-900">Obstacles reported</h3>
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
            {props.accessibility.disclaimer} Walker markers are a time estimate, not a tracked location.
          </p>
        </div>
      </div>
    </SectionCard>
  );
}

interface RoutePoint {
  x: number;
  y: number;
}

function routePolyline(accessibility: DashboardAccessibilityResponse): RoutePoint[] {
  const route = accessibility.routes[0];
  if (!route || route.segments.length === 0) return [];
  const ordered = [...route.segments].sort((a, b) => a.segment.sequence - b.segment.sequence);
  const points: RoutePoint[] = [{ x: ordered[0].segment.start.x, y: ordered[0].segment.start.y }];
  for (const item of ordered) points.push({ x: item.segment.end.x, y: item.segment.end.y });
  return points;
}

/** Point at arc-length `t` (0..1) along a polyline, plus its unit direction. */
function sampleRoute(points: RoutePoint[], t: number): { at: RoutePoint; dir: RoutePoint } {
  if (points.length < 2) {
    const only = points[0] ?? { x: 0.5, y: 0.5 };
    return { at: only, dir: { x: 0, y: -1 } };
  }
  const lengths: number[] = [];
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    const seg = Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
    lengths.push(seg);
    total += seg;
  }
  let target = Math.min(Math.max(t, 0), 1) * total;
  for (let i = 1; i < points.length; i += 1) {
    const seg = lengths[i - 1];
    if (target <= seg || i === points.length - 1) {
      const f = seg === 0 ? 0 : target / seg;
      const a = points[i - 1];
      const b = points[i];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const norm = Math.hypot(dx, dy) || 1;
      return { at: { x: a.x + dx * f, y: a.y + dy * f }, dir: { x: dx / norm, y: dy / norm } };
    }
    target -= seg;
  }
  return { at: points[points.length - 1], dir: { x: 0, y: -1 } };
}

function RouteCanvas(props: {
  accessibility: DashboardAccessibilityResponse;
  hazards: HazardRecord[];
  now: number;
  sessions: ActiveWalkSession[];
}) {
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

    const points = routePolyline(props.accessibility);

    // Route corridor: a soft band under a firm centre line.
    if (points.length >= 2) {
      context.strokeStyle = "rgba(180, 83, 9, 0.14)";
      context.lineWidth = 26;
      context.lineCap = "round";
      context.lineJoin = "round";
      traceLine(context, points, width, height);

      context.strokeStyle = "#b45309";
      context.lineWidth = 4;
      traceLine(context, points, width, height);

      dot(context, points[0].x * width, points[0].y * height, 5, "#b45309");
      dot(context, points[points.length - 1].x * width, points[points.length - 1].y * height, 5, "#b45309");
    }

    // Reported hazards.
    for (const hazard of props.hazards) {
      if (!hazard.map_coordinate) continue;
      const hx = hazard.map_coordinate.x * width;
      const hy = hazard.map_coordinate.y * height;
      context.beginPath();
      context.fillStyle = severityColor(hazard.severity);
      context.arc(hx, hy, 7 + Math.min(hazard.confirmation_count, 5), 0, Math.PI * 2);
      context.fill();
      context.lineWidth = 2.5;
      context.strokeStyle = "#ffffff";
      context.stroke();
    }

    // Walkers out now — estimated position along the route from time walked.
    if (points.length >= 1) {
      for (const session of props.sessions) {
        const startedMs = Date.parse(session.started_at);
        const lastFrameMs = session.last_frame_at ? Date.parse(session.last_frame_at) : null;
        const quiet = lastFrameMs === null || props.now - lastFrameMs > SIGNAL_STALE_MS;
        // Freeze a quiet walker where they were when the signal dropped.
        const clockMs = quiet && lastFrameMs !== null ? lastFrameMs : props.now;
        const elapsed = Number.isFinite(startedMs) ? Math.max(0, clockMs - startedMs) : 0;
        const t = Math.min(0.96, Math.max(0.03, elapsed / EXPECTED_WALK_MS));

        const { at, dir } = sampleRoute(points, t);
        let px = at.x * width;
        let py = at.y * height;

        // Nudge sideways when the assistant is steering them off-centre.
        if (session.last_action === "MOVE_LEFT" || session.last_action === "MOVE_RIGHT") {
          const side = session.last_action === "MOVE_LEFT" ? -1 : 1;
          px += -dir.y * side * 16;
          py += dir.x * side * 16;
        }

        const tone = quiet
          ? "#c2bcb2"
          : session.last_action === "STOP"
            ? "#dc2626"
            : session.last_risk_level === "HIGH" || session.last_risk_level === "CRITICAL"
              ? "#dc2626"
              : session.last_action === "CAUTION" ||
                  session.last_action === "PAUSE_UNCLEAR" ||
                  session.last_risk_level === "WATCH" ||
                  session.last_risk_level === "WARN"
                ? "#d97706"
                : "#059669";

        if (!quiet && session.last_action === "STOP") {
          context.beginPath();
          context.strokeStyle = "rgba(220, 38, 38, 0.35)";
          context.lineWidth = 3;
          context.arc(px, py, 20, 0, Math.PI * 2);
          context.stroke();
        }

        dot(context, px, py, 9, tone);
        context.lineWidth = 3;
        context.strokeStyle = "#ffffff";
        context.stroke();

        context.font = "600 11px Inter, system-ui, sans-serif";
        context.fillStyle = "#1a1714";
        context.textAlign = "center";
        context.textBaseline = "top";
        context.fillText(deviceTag(session.session_id), px, py + 13);
      }
    }
  }, [props.accessibility, props.hazards, props.sessions, props.now]);

  const live = props.sessions.length;
  return (
    <canvas
      ref={canvasRef}
      className="mt-3 aspect-[2/1] w-full rounded-sm border border-ink-200 bg-[#fdf9ed]"
      role="img"
      aria-label={
        live === 0
          ? "Walking route. Nobody is out right now."
          : `Walking route with ${live} walker${live === 1 ? "" : "s"} out, positioned by time walked.`
      }
    />
  );
}

function traceLine(context: CanvasRenderingContext2D, points: RoutePoint[], width: number, height: number) {
  context.beginPath();
  context.moveTo(points[0].x * width, points[0].y * height);
  for (let i = 1; i < points.length; i += 1) context.lineTo(points[i].x * width, points[i].y * height);
  context.stroke();
}

function dot(context: CanvasRenderingContext2D, x: number, y: number, r: number, fill: string) {
  context.beginPath();
  context.fillStyle = fill;
  context.arc(x, y, r, 0, Math.PI * 2);
  context.fill();
}

/** Same short tag WalkersNow shows, so the coordinator matches them across panels. */
function deviceTag(sessionId: string): string {
  const clean = sessionId.replace(/[^a-z0-9]/gi, "");
  return (clean.slice(-2) || "??").toUpperCase();
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
