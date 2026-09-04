import type { HazardRecord, HazardSeverity, HazardStatus } from "@drishti/contracts";
import { AlertTriangle, Accessibility, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import type { ActiveWalkSession } from "./api/health";
import { fetchActiveWalkSessions, fetchHealth } from "./api/health";
import {
  createHazard,
  fetchAccessibility,
  fetchActiveHazards,
  fetchDashboardSummary,
  mergeHazards,
  updateHazardStatus,
} from "./api/hazards";
import { HazardMap } from "./components/HazardMap";
import { HazardOperations } from "./components/HazardOperations";
import { ReportHazard } from "./components/ReportHazard";
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
  const [reporting, setReporting] = useState(false);

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

  /**
   * File a hazard the coordinator saw themselves. The map identity comes from
   * the live route, so this never invents a map id or version.
   */
  const submitHazard = async (input: {
    category: string;
    severity: HazardSeverity;
    temporary: boolean;
    position: { x: number; y: number } | null;
  }) => {
    const route = state?.accessibility.routes[0] ?? null;
    setReporting(true);
    try {
      await createHazard({
        category: input.category,
        severity: input.severity,
        temporary: input.temporary,
        mapCoordinate:
          route && input.position
            ? {
                map_id: route.map_id,
                map_version: route.map_version,
                x: input.position.x,
                y: input.position.y,
              }
            : undefined,
      });
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That report did not go through.");
    } finally {
      setReporting(false);
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
    <div className="min-h-screen text-ink-900">
      <a
        href="#dashboard-content"
        className="sr-only z-50 rounded-sm border border-amber-700 bg-white px-4 py-2 font-semibold text-amber-900 focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to main content
      </a>

      {/* Staff running the programme may themselves have low vision. */}
      <div className="border-b border-ink-200 bg-ink-50">
        <div className="mx-auto flex max-w-[1180px] items-center justify-end gap-2 px-5 py-2 sm:px-7">
          <span className="text-[0.8rem] font-medium text-ink-500">Text size</span>
          <div className="inline-flex overflow-hidden rounded-sm border border-ink-300 bg-white" aria-label="Text size controls">
            <FontButton label="A-" scale={90} current={fontScale} onSelect={setFontScale} />
            <FontButton label="A" scale={100} current={fontScale} onSelect={setFontScale} />
            <FontButton label="A+" scale={112} current={fontScale} onSelect={setFontScale} />
          </div>
        </div>
      </div>

      <header className="border-b-2 border-ink-800 bg-white">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-4 px-5 py-6 sm:px-7">
          <div className="flex min-w-0 items-center gap-3.5">
            <Accessibility size={30} strokeWidth={1.7} className="shrink-0 text-amber-800" aria-hidden="true" />
            <div className="min-w-0">
              <p className="font-display text-[1.7rem] font-semibold leading-none tracking-[-0.015em] text-ink-900">
                DRISHTI
              </p>
              <p className="mt-1.5 text-[0.9rem] text-ink-500">Walking programme operations</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex min-h-11 items-center gap-2 rounded-sm border border-ink-300 bg-white px-4 text-[0.9rem] font-semibold text-ink-700 hover:border-amber-500 hover:bg-amber-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700"
          >
            <RefreshCw className={isRefreshing ? "animate-spin" : ""} size={16} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </header>

      <main id="dashboard-content" className="mx-auto max-w-[1180px] space-y-7 px-5 py-8 sm:px-7">
        {error ? (
          <div className="flex gap-3 rounded-sm border-l-4 border-red-700 bg-red-50 px-5 py-4 text-red-950" role="alert">
            <AlertTriangle className="mt-0.5 shrink-0" size={20} aria-hidden="true" />
            <div>
              <p className="font-display text-lg font-semibold leading-tight">Cannot reach the system</p>
              <p className="mt-1 text-[0.9rem]">{error}</p>
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
            <div className="flex justify-end">
              <ReportHazard
                busy={reporting}
                onSubmit={submitHazard}
                route={state.accessibility.routes[0] ?? null}
              />
            </div>
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
          <div className="rounded-sm border border-ink-200 bg-white p-14 text-center" role="status">
            <span
              className="mx-auto block size-8 animate-spin rounded-full border-4 border-ink-200 border-t-amber-700"
              aria-hidden="true"
            />
            <p className="mt-4 font-display text-lg text-ink-600">Loading…</p>
          </div>
        )}
      </main>

      <footer id="accessibility-statement" className="mt-4 border-t border-ink-200 bg-white">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-2 px-5 py-5 text-[0.8rem] text-ink-400 sm:px-7">
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
      className={`min-h-8 px-3 text-[0.8rem] font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700 ${
        pressed ? "bg-amber-800 text-white" : "text-ink-700 hover:bg-amber-50"
      }`}
    >
      {props.label}
    </button>
  );
}
