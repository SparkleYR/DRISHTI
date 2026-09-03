import type { HazardRecord, HazardStatus } from "@drishti/contracts";
import { AlertTriangle, Clock3, Database, ListChecks, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { fetchHealth } from "./api/health";
import {
  fetchAccessibility,
  fetchActiveHazards,
  fetchDashboardSummary,
  mergeHazards,
  updateHazardStatus,
} from "./api/hazards";
import { AccessibilityAnalytics } from "./components/AccessibilityAnalytics";
import { HardwareModelManager } from "./components/HardwareModelManager";
import { HazardOperations } from "./components/HazardOperations";
import { HeaderStatusBar } from "./components/HeaderStatusBar";
import { LiveWalkMonitor } from "./components/LiveWalkMonitor";
import { TargetLockMonitor } from "./components/TargetLockMonitor";
import { useEdgeStream } from "./hooks/useEdgeStream";
import type { DashboardState } from "./types";

export function App() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [operatorAlias, setOperatorAlias] = useState("access-desk");
  const [assignedTo, setAssignedTo] = useState("facilities-team");
  const [duplicateId, setDuplicateId] = useState("");
  const [workingId, setWorkingId] = useState<string | null>(null);
  const edge = useEdgeStream();

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [health, summary, hazards, accessibility] = await Promise.all([
        fetchHealth(),
        fetchDashboardSummary(),
        fetchActiveHazards(),
        fetchAccessibility(),
      ]);
      setState({ accessibility, health, summary, hazards: hazards.items });
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Backend is unreachable.");
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      await refresh();
      if (!stopped) timer = setTimeout(() => void poll(), 2_000);
    };
    void poll();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [refresh]);

  const applyStatus = async (hazard: HazardRecord, newStatus: HazardStatus) => {
    if (!operatorAlias.trim()) return setError("Enter a local operator alias before changing status.");
    if (newStatus === "ASSIGNED" && !assignedTo.trim()) return setError("Enter an assignee before assigning a report.");
    setWorkingId(hazard.id);
    try {
      await updateHazardStatus(hazard, newStatus, operatorAlias.trim(), newStatus === "ASSIGNED" ? assignedTo.trim() : undefined);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Status update failed.");
    } finally {
      setWorkingId(null);
    }
  };

  const applyMerge = async (primary: HazardRecord) => {
    const duplicate = state?.hazards.find((item) => item.id === duplicateId.trim());
    if (!operatorAlias.trim()) return setError("Enter a local operator alias before merging reports.");
    if (!duplicate || duplicate.id === primary.id) return setError("Enter the ID of another active report to merge.");
    setWorkingId(primary.id);
    try {
      await mergeHazards(primary, duplicate, operatorAlias.trim());
      setDuplicateId("");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Merge failed.");
    } finally {
      setWorkingId(null);
    }
  };

  return (
    <div className="min-h-screen text-slate-900">
      <a href="#dashboard-content" className="sr-only z-50 rounded-sm border border-amber-600 bg-white px-4 py-2 font-semibold text-amber-800 focus:not-sr-only focus:fixed focus:left-3 focus:top-3">Skip to dashboard content</a>
      <HeaderStatusBar edge={edge} health={state?.health ?? null} isRefreshing={isRefreshing} onRefresh={() => void refresh()} />
      <main id="dashboard-content" className="mx-auto max-w-[1480px] space-y-5 px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
        {error ? (
          <div className="flex gap-3 rounded-sm border border-red-300 bg-red-50 px-4 py-3 text-red-950" role="alert">
            <AlertTriangle className="mt-0.5 shrink-0" size={19} aria-hidden="true" />
            <div><p className="text-sm font-bold">Local synchronization issue</p><p className="mt-0.5 text-sm">{error}</p></div>
          </div>
        ) : null}

        {state ? <OperationalSummary state={state} /> : (
          <div className="rounded-sm border border-slate-300 bg-white p-8 text-center" role="status">
            <span className="mx-auto block size-8 animate-spin rounded-full border-4 border-slate-200 border-t-amber-700" aria-hidden="true" />
            <p className="mt-3 text-sm font-bold text-slate-800">Loading local operations…</p>
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-3">
          <LiveWalkMonitor edge={edge} />
          <TargetLockMonitor edge={edge} />
        </div>

        {state ? (
          <>
            <AccessibilityAnalytics accessibility={state.accessibility} hazards={state.hazards} />
            <HardwareModelManager edge={edge} health={state.health} />
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
          </>
        ) : null}
      </main>
      <footer id="accessibility-statement" className="border-t border-slate-300 bg-white">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs text-slate-500 sm:px-6 lg:px-8">
          <span>DRISHTI local-only accessibility prototype</span>
          <span>Advisory monitoring · not a replacement for mobility aids or human judgment</span>
        </div>
      </footer>
    </div>
  );
}

function OperationalSummary({ state }: { state: DashboardState }) {
  const items = [
    { icon: ListChecks, label: "Awaiting review", value: state.summary.awaiting_review },
    { icon: ShieldCheck, label: "Active verified", value: state.summary.active_verified_hazards },
    { icon: Database, label: "Database", value: state.health.database.status },
    { icon: Clock3, label: "Last local sync", value: new Date(state.summary.server_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) },
  ];
  return (
    <section className="grid overflow-hidden rounded-sm border border-slate-300 bg-white sm:grid-cols-2 lg:grid-cols-4" aria-label="Operations summary">
      {items.map((item, index) => {
        const Icon = item.icon;
        return <div className={`flex items-center gap-3 px-5 py-4 ${index ? "border-t border-slate-300 sm:border-l sm:border-t-0" : ""}`} key={item.label}><span className="grid size-9 place-items-center rounded-sm border border-slate-200 bg-[#fcfbf9] text-slate-700"><Icon size={18} aria-hidden="true" /></span><div><p className="text-xs font-medium text-slate-600">{item.label}</p><p className="mt-0.5 text-lg font-bold tabular-nums text-slate-950">{item.value}</p></div></div>;
      })}
    </section>
  );
}
