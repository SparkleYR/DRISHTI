import type { HazardRecord, HazardStatus } from "@drishti/contracts";
import { AlertTriangle, Accessibility, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import type { ActiveWalkSession } from "./api/health";
import { fetchActiveWalkSessions, fetchHealth } from "./api/health";
import {
  fetchAccessibility,
  fetchActiveHazards,
  fetchDashboardSummary,
  mergeHazards,
  updateHazardStatus,
} from "./api/hazards";
import { HazardMap } from "./components/HazardMap";
import { HazardOperations } from "./components/HazardOperations";
import { SystemReadiness } from "./components/SystemReadiness";
import { WalkersNow } from "./components/WalkersNow";
import type { DashboardState } from "./types";

const POLL_INTERVAL_MS = 2_000;

/**
 * The AccessOps dashboard, written for the coordinator running a walking
 * programme — not for an engineer reading the pipeline.
 *
 * Order follows what that person needs, most urgent first: is anyone out and
 * are they alright, is the system usable, what needs doing today, and where
 * are the hazards. Model states and hardware counters are detail, so they sit
 * behind a disclosure inside `SystemReadiness`.
 */
export function App() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [walkers, setWalkers] = useState<ActiveWalkSession[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [operatorAlias, setOperatorAlias] = useState("access-desk");
  const [assignedTo, setAssignedTo] = useState("facilities-team");
  const [duplicateId, setDuplicateId] = useState("");
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [fontScale, setFontScale] = useState(100);

  useEffect(() => {
    document.documentElement.style.fontSize = `${fontScale}%`;
    return () => {
      document.documentElement.style.fontSize = "";
    };
  }, [fontScale]);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [health, summary, hazards, accessibility, sessions] = await Promise.all([
        fetchHealth(),
        fetchDashboardSummary(),
        fetchActiveHazards(),
        fetchAccessibility(),
        fetchActiveWalkSessions(),
      ]);
      setState({ accessibility, health, summary, hazards: hazards.items });
      setWalkers(sessions);
      setNow(Date.now());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The backend is unreachable.");
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      await refresh();
      if (!stopped) timer = setTimeout(() => void poll(), POLL_INTERVAL_MS);
    };
    void poll();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [refresh]);

  // Keep "walking for 12 min" and "no signal for 14 sec" honest between polls.
  useEffect(() => {
    const ticker = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(ticker);
  }, []);

  const applyStatus = async (hazard: HazardRecord, newStatus: HazardStatus) => {
    if (!operatorAlias.trim()) return setError("Enter your name before changing a report.");
    if (newStatus === "ASSIGNED" && !assignedTo.trim()) return setError("Enter who this is assigned to.");
    setWorkingId(hazard.id);
    try {
      await updateHazardStatus(
        hazard,
        newStatus,
        operatorAlias.trim(),
        newStatus === "ASSIGNED" ? assignedTo.trim() : undefined,
      );
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That update did not go through.");
    } finally {
      setWorkingId(null);
    }
  };

  const applyMerge = async (primary: HazardRecord) => {
    const duplicate = state?.hazards.find((item) => item.id === duplicateId.trim());
    if (!operatorAlias.trim()) return setError("Enter your name before merging reports.");
    if (!duplicate || duplicate.id === primary.id) return setError("Enter the ID of another open report to merge.");
    setWorkingId(primary.id);
    try {
      await mergeHazards(primary, duplicate, operatorAlias.trim());
      setDuplicateId("");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That merge did not go through.");
    } finally {
      setWorkingId(null);
    }
  };

  return (
    <div className="min-h-screen text-slate-900">
      <a
        href="#dashboard-content"
        className="sr-only z-50 rounded-sm border border-amber-600 bg-white px-4 py-2 font-semibold text-amber-800 focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to main content
      </a>

      {/* Staff running the programme may themselves have low vision. */}
      <div className="border-b border-slate-200 bg-slate-100">
        <div className="mx-auto flex max-w-[1200px] items-center justify-end gap-2 px-4 py-1.5 sm:px-6">
          <span className="text-xs font-medium text-slate-600">Text size</span>
          <div className="inline-flex overflow-hidden rounded-sm border border-slate-300 bg-white" aria-label="Text size controls">
            <FontButton label="A-" scale={90} current={fontScale} onSelect={setFontScale} />
            <FontButton label="A" scale={100} current={fontScale} onSelect={setFontScale} />
            <FontButton label="A+" scale={112} current={fontScale} onSelect={setFontScale} />
          </div>
        </div>
      </div>

      <header className="border-b border-slate-300 bg-white">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <span
              className="grid size-11 shrink-0 place-items-center rounded-sm border border-amber-300 bg-amber-50 text-amber-700"
              aria-hidden="true"
            >
              <Accessibility size={25} strokeWidth={1.9} />
            </span>
            <div>
              <p className="text-lg font-bold leading-tight text-slate-950">DRISHTI</p>
              <p className="text-sm text-slate-600">Walking programme dashboard</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex min-h-10 items-center gap-2 rounded-sm border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 hover:border-amber-400 hover:bg-amber-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700"
          >
            <RefreshCw className={isRefreshing ? "animate-spin" : ""} size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </header>

      <main id="dashboard-content" className="mx-auto max-w-[1200px] space-y-5 px-4 py-6 sm:px-6">
        {error ? (
          <div className="flex gap-3 rounded-sm border border-red-300 bg-red-50 px-4 py-3 text-red-950" role="alert">
            <AlertTriangle className="mt-0.5 shrink-0" size={19} aria-hidden="true" />
            <div>
              <p className="text-sm font-bold">Cannot reach the system</p>
              <p className="mt-0.5 text-sm">{error}</p>
            </div>
          </div>
        ) : null}

        {state ? (
          <>
            {/* 1. Is anyone out, and are they alright? */}
            <WalkersNow now={now} sessions={walkers} />

            {/* 2. Can people go out at all? */}
            <SystemReadiness health={state.health} />

            {/* 3. What needs doing today? */}
            <HazardOperations
              assignedTo={assignedTo}
              duplicateId={duplicateId}
              hazards={state.hazards}
              onMerge={applyMerge}
              onStatus={applyStatus}
              operatorAlias={operatorAlias}
              setAssignedTo={setAssignedTo}
              setDuplicateId={setDuplicateId}
              setOperatorAlias={setOperatorAlias}
              workingId={workingId}
            />

            {/* 4. Where are the problems? */}
            <HazardMap accessibility={state.accessibility} hazards={state.hazards} />

          </>
        ) : (
          <div className="rounded-sm border border-slate-300 bg-white p-10 text-center" role="status">
            <span
              className="mx-auto block size-8 animate-spin rounded-full border-4 border-slate-200 border-t-amber-700"
              aria-hidden="true"
            />
            <p className="mt-3 text-sm font-bold text-slate-800">Loading…</p>
          </div>
        )}
      </main>

      <footer id="accessibility-statement" className="border-t border-slate-300 bg-white">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs text-slate-500 sm:px-6">
          <span>DRISHTI · runs entirely on this local network</span>
          <span>Advisory monitoring — not a replacement for mobility aids or human judgment</span>
        </div>
      </footer>
    </div>
  );
}

function FontButton(props: {
  current: number;
  label: string;
  onSelect: (scale: number) => void;
  scale: number;
}) {
  const pressed = props.current === props.scale;
  return (
    <button
      type="button"
      aria-label={`Set text size ${props.label}`}
      aria-pressed={pressed}
      onClick={() => props.onSelect(props.scale)}
      className={`min-h-7 px-2.5 text-xs font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700 ${
        pressed ? "bg-amber-700 text-white" : "text-slate-800 hover:bg-amber-50"
      }`}
    >
      {props.label}
    </button>
  );
}
