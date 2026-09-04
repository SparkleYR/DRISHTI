import { Footprints, ShieldAlert, WifiOff } from "lucide-react";

import type { ActiveWalkSession } from "../api/health";
import { SectionCard, StatusBadge } from "./ui";

/** Longer than this since the last frame and the device has effectively gone quiet. */
const SIGNAL_STALE_MS = 10_000;

/**
 * Who is out walking right now.
 *
 * Sessions are anonymous by design — DRISHTI never collects identity or route
 * history — so a walker is shown by a short device tag derived from the session
 * id. The coordinator matches that tag to a person from their own handout sheet.
 */
export function WalkersNow(props: { sessions: ActiveWalkSession[]; now: number }) {
  const walkers = props.sessions.map((session) => describe(session, props.now));
  const needsAttention = walkers.filter((walker) => walker.tone === "red").length;

  return (
    <SectionCard
      description="Anonymous device sessions. DRISHTI never records who is walking, where they have been, or their camera view."
      eyebrow="Right now"
      icon={Footprints}
      id="walkers"
      title="People out walking"
      trailing={
        <StatusBadge tone={needsAttention > 0 ? "red" : walkers.length > 0 ? "green" : "slate"}>
          {walkers.length === 0
            ? "Nobody walking"
            : `${walkers.length} walking${needsAttention > 0 ? ` · ${needsAttention} need a check` : ""}`}
        </StatusBadge>
      }
    >
      {walkers.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-slate-600 sm:px-6">
          Nobody is walking right now. Sessions appear here the moment someone starts Walk Mode on their phone.
        </p>
      ) : (
        <ul className="divide-y divide-slate-200">
          {walkers.map((walker) => (
            <li key={walker.id} className="flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4 sm:px-6">
              <span
                className={`grid size-11 shrink-0 place-items-center rounded-sm border text-sm font-bold ${
                  walker.tone === "red"
                    ? "border-red-300 bg-red-50 text-red-800"
                    : walker.tone === "yellow"
                      ? "border-amber-300 bg-amber-50 text-amber-800"
                      : "border-emerald-300 bg-emerald-50 text-emerald-800"
                }`}
                aria-hidden="true"
              >
                {walker.tag}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-slate-950">Device {walker.tag}</p>
                <p className="mt-0.5 text-xs text-slate-600">Walking for {walker.duration}</p>
              </div>
              <div className="min-w-[13rem]">
                <p className="text-xs font-semibold text-slate-600">Assistant is saying</p>
                <p className={`mt-0.5 text-sm font-bold ${walker.tone === "red" ? "text-red-800" : "text-slate-950"}`}>
                  {walker.guidance}
                </p>
              </div>
              <StatusBadge tone={walker.signalTone}>
                {walker.signalTone === "red" ? <WifiOff size={13} aria-hidden="true" /> : null}
                {walker.signal}
              </StatusBadge>
            </li>
          ))}
        </ul>
      )}
      {needsAttention > 0 ? (
        <p className="flex items-center gap-2 border-t border-red-200 bg-red-50 px-5 py-3 text-sm font-semibold text-red-900 sm:px-6" role="status">
          <ShieldAlert size={16} aria-hidden="true" />
          Someone may need help. Check on the devices marked above.
        </p>
      ) : null}
    </SectionCard>
  );
}

interface WalkerView {
  duration: string;
  guidance: string;
  id: string;
  signal: string;
  signalTone: "green" | "red" | "slate" | "yellow";
  tag: string;
  tone: "green" | "red" | "yellow";
}

function describe(session: ActiveWalkSession, now: number): WalkerView {
  const startedMs = Date.parse(session.started_at);
  const lastFrameMs = session.last_frame_at ? Date.parse(session.last_frame_at) : null;
  const sinceSignalMs = lastFrameMs === null ? null : now - lastFrameMs;
  const stale = sinceSignalMs === null || sinceSignalMs > SIGNAL_STALE_MS;

  let signal = "Connected";
  let signalTone: WalkerView["signalTone"] = "green";
  if (lastFrameMs === null) {
    signal = "Waiting for first frame";
    signalTone = "slate";
  } else if (stale) {
    signal = `No signal for ${formatDuration(sinceSignalMs ?? 0)}`;
    signalTone = "red";
  }

  const guidance = guidanceSentence(session.last_action);
  // Red means "look at this person": either their phone went quiet, or the
  // assistant is actively telling them to stop.
  const tone: WalkerView["tone"] =
    stale || session.last_action === "STOP"
      ? "red"
      : session.last_action === "CAUTION" || session.last_action === "PAUSE_UNCLEAR"
        ? "yellow"
        : "green";

  return {
    duration: formatDuration(Math.max(0, now - startedMs)),
    guidance,
    id: session.session_id,
    signal,
    signalTone,
    tag: session.session_id.slice(0, 2).toUpperCase(),
    tone,
  };
}

function guidanceSentence(action: ActiveWalkSession["last_action"]): string {
  switch (action) {
    case "STOP":
      return "Stop — something ahead";
    case "CAUTION":
      return "Slow down";
    case "MOVE_LEFT":
      return "Move left";
    case "MOVE_RIGHT":
      return "Move right";
    case "PAUSE_UNCLEAR":
      return "Pause — view unclear";
    case "CLEAR":
      return "Path is clear";
    default:
      return "Not started yet";
  }
}

function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.round(milliseconds / 1000);
  if (totalSeconds < 60) return `${totalSeconds} sec`;
  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hr ${minutes % 60} min`;
}
