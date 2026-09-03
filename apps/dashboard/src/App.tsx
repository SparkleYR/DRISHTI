import type {
  DashboardAccessibilityResponse,
  DashboardSummaryResponse,
  HazardRecord,
  HazardStatus,
  HealthResponse,
} from "@drishti/contracts";
import { useCallback, useEffect, useState } from "react";

import { fetchHealth } from "./api/health";
import {
  fetchAccessibility,
  fetchActiveHazards,
  fetchDashboardSummary,
  mergeHazards,
  updateHazardStatus,
} from "./api/hazards";

interface DashboardState {
  accessibility: DashboardAccessibilityResponse;
  health: HealthResponse;
  summary: DashboardSummaryResponse;
  hazards: HazardRecord[];
}

export function App() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [operatorAlias, setOperatorAlias] = useState("access-desk");
  const [assignedTo, setAssignedTo] = useState("facilities-team");
  const [duplicateId, setDuplicateId] = useState("");
  const [workingId, setWorkingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
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
    if (!operatorAlias.trim()) {
      setError("Enter a local operator alias before changing status.");
      return;
    }
    if (newStatus === "ASSIGNED" && !assignedTo.trim()) {
      setError("Enter an assignee before assigning a report.");
      return;
    }
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
      setError(caught instanceof Error ? caught.message : "Status update failed.");
    } finally {
      setWorkingId(null);
    }
  };

  const applyMerge = async (primary: HazardRecord) => {
    const duplicate = state?.hazards.find((item) => item.id === duplicateId.trim());
    if (!operatorAlias.trim()) {
      setError("Enter a local operator alias before merging reports.");
      return;
    }
    if (!duplicate || duplicate.id === primary.id) {
      setError("Enter the ID of another active report to merge.");
      return;
    }
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
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">DRISHTI ACCESSOPS · LOCAL ONLY</p>
          <h1>Accessibility operations</h1>
          <p className="subtitle">Anonymous reports synchronized through the laptop backend every two seconds.</p>
        </div>
        <button type="button" onClick={() => void refresh()}>Refresh now</button>
      </header>

      {error ? <section className="panel error" role="alert"><strong>Local sync issue:</strong> {error}</section> : null}
      {!state ? <p className="loading" role="status">Loading local operations…</p> : null}
      {state ? (
        <>
          <Overview state={state} />
          <AccessibilityIntelligence accessibility={state.accessibility} />
          <OperatorControls
            assignedTo={assignedTo}
            duplicateId={duplicateId}
            operatorAlias={operatorAlias}
            setAssignedTo={setAssignedTo}
            setDuplicateId={setDuplicateId}
            setOperatorAlias={setOperatorAlias}
          />
          <MapPlane hazards={state.hazards} />
          <VerificationQueue
            hazards={state.hazards}
            onMerge={applyMerge}
            onStatus={applyStatus}
            workingId={workingId}
          />
          <RecentlyResolved hazards={state.summary.recently_resolved} />
        </>
      ) : null}
    </main>
  );
}

function AccessibilityIntelligence({ accessibility }: { accessibility: DashboardAccessibilityResponse }) {
  return (
    <section className="panel" aria-label="Hall accessibility intelligence">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">EXPLAINABLE HALL INTELLIGENCE</p>
          <h2>Recurring hazards and route score</h2>
        </div>
        <span className="timestamp">{accessibility.expired_temporary_count} expired automatically</span>
      </div>
      <p className="advisory" role="note">{accessibility.disclaimer}</p>
      <div className="route-list">
        {accessibility.routes.map((route) => (
          <article className="route-card" key={route.route_id}>
            <div className="route-score">
              <div>
                <strong>{route.route_name}</strong>
                <small>{route.map_id} · map v{route.map_version} · spec {route.specification_version}</small>
              </div>
              <div className="score-value" data-band={route.band}>
                <strong>{route.score}</strong><span>/100</span><small>{formatBand(route.band)}</small>
              </div>
            </div>
            <p>{route.description}</p>
            <p className="route-counts">{route.active_hazard_count} active route hazard(s) · {route.recurring_hazard_count} recurring</p>
            <div className="segment-list">
              {route.segments.map((segment) => (
                <details key={segment.segment.id} open={segment.factors.length > 0}>
                  <summary>
                    <span>{segment.segment.sequence}. {segment.segment.name}</span>
                    <strong>{segment.score}/100 · {formatBand(segment.band)}</strong>
                  </summary>
                  {segment.factors.length ? segment.factors.map((factor) => (
                    <div className="score-factor" key={`${segment.segment.id}-${factor.hazard_id}`}>
                      <div><strong>{factor.category}</strong><span>−{factor.penalty_points} points</span></div>
                      <p>{factor.explanation}</p>
                      <small>
                        severity {factor.severity_points} × status {factor.status_factor.toFixed(2)} × recurrence {factor.recurrence_factor.toFixed(2)} × confidence {factor.confidence_factor.toFixed(2)} × freshness {factor.freshness_factor.toFixed(2)} × spatial {factor.spatial_factor.toFixed(2)}
                      </small>
                    </div>
                  )) : <p>No active reported hazard currently affects this segment.</p>}
                </details>
              ))}
            </div>
          </article>
        ))}
        {accessibility.routes.length === 0 ? <p>No active versioned routes are configured.</p> : null}
      </div>
    </section>
  );
}

function formatBand(value: string): string {
  return value.toLowerCase().replaceAll("_", " ");
}

function Overview({ state }: { state: DashboardState }) {
  const summary = state.summary;
  return (
    <section className="summary" aria-label="Operations summary">
      <StatusCard label="Awaiting review" value={summary.awaiting_review} />
      <StatusCard label="Active verified" value={summary.active_verified_hazards} />
      <StatusCard label="Assigned" value={summary.counts.assigned + summary.counts.in_progress} />
      <StatusCard label="Recently resolved" value={summary.recently_resolved.length} />
      <StatusCard label="Database" value={state.health.database.status} />
      <StatusCard label="Walk Mode" value={state.health.walk_mode_available ? "AVAILABLE" : "NOT AVAILABLE"} />
    </section>
  );
}

function OperatorControls(props: {
  operatorAlias: string;
  assignedTo: string;
  duplicateId: string;
  setOperatorAlias: (value: string) => void;
  setAssignedTo: (value: string) => void;
  setDuplicateId: (value: string) => void;
}) {
  return (
    <section className="panel controls-panel">
      <label>Operator alias<input value={props.operatorAlias} onChange={(event) => props.setOperatorAlias(event.target.value)} /></label>
      <label>Assign to<input value={props.assignedTo} onChange={(event) => props.setAssignedTo(event.target.value)} /></label>
      <label>Duplicate report ID<input value={props.duplicateId} onChange={(event) => props.setDuplicateId(event.target.value)} /></label>
    </section>
  );
}

function MapPlane({ hazards }: { hazards: HazardRecord[] }) {
  const mapped = hazards.filter((hazard) => hazard.map_coordinate);
  return (
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">VERSIONED LOCAL COORDINATES</p><h2>Map plane</h2></div><span className="timestamp">Campus image pending</span></div>
      <div className="map-plane" aria-label="Normalized local hazard map">
        {mapped.map((hazard) => (
          <button
            aria-label={`${hazard.category}, ${hazard.status}`}
            className="map-marker"
            key={hazard.id}
            style={{ left: `${hazard.map_coordinate!.x * 100}%`, top: `${hazard.map_coordinate!.y * 100}%` }}
            title={`${hazard.category} · ${hazard.map_coordinate!.map_id} v${hazard.map_coordinate!.map_version}`}
            type="button"
          >{hazard.confirmation_count}</button>
        ))}
        {mapped.length === 0 ? <p>No active reports have map coordinates.</p> : null}
      </div>
    </section>
  );
}

function VerificationQueue(props: {
  hazards: HazardRecord[];
  workingId: string | null;
  onStatus: (hazard: HazardRecord, status: HazardStatus) => Promise<void>;
  onMerge: (hazard: HazardRecord) => Promise<void>;
}) {
  return (
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">POLLING QUEUE</p><h2>Verification and resolution</h2></div><span className="timestamp">{props.hazards.length} active</span></div>
      <div className="report-list">
        {props.hazards.map((hazard) => (
          <article className="report" key={hazard.id}>
            <div><strong>{hazard.category}</strong><span>{hazard.severity} · {hazard.status} · confidence {Math.round(hazard.confidence * 100)}%</span><small>ID {hazard.id} · v{hazard.version} · {hazard.confirmation_count} confirmation(s){hazard.has_consented_evidence ? " · consented evidence attached" : ""}</small></div>
            <div className="actions">
              {nextActions(hazard.status).map(([label, status]) => <button disabled={props.workingId === hazard.id} key={status} onClick={() => void props.onStatus(hazard, status)} type="button">{label}</button>)}
              <button disabled={props.workingId === hazard.id} onClick={() => void props.onMerge(hazard)} type="button">Merge into this</button>
            </div>
          </article>
        ))}
        {props.hazards.length === 0 ? <p>No active hazard reports.</p> : null}
      </div>
    </section>
  );
}

function RecentlyResolved({ hazards }: { hazards: HazardRecord[] }) {
  return <section className="panel"><div className="panel-heading"><h2>Recently resolved</h2></div>{hazards.length ? hazards.map((item) => <p key={item.id}>{item.category} · {new Date(item.last_seen_at).toLocaleString()}</p>) : <p>No resolved reports yet.</p>}</section>;
}

function nextActions(status: HazardStatus): Array<[string, HazardStatus]> {
  if (status === "NEW") return [["Verify", "VERIFIED"], ["Reject", "REJECTED"]];
  if (status === "VERIFIED") return [["Assign", "ASSIGNED"], ["Resolve", "RESOLVED"], ["Reject", "REJECTED"]];
  if (status === "ASSIGNED") return [["Start", "IN_PROGRESS"], ["Resolve", "RESOLVED"]];
  if (status === "IN_PROGRESS") return [["Resolve", "RESOLVED"]];
  return [];
}

function StatusCard({ label, value }: { label: string; value: string | number }) {
  return <article className="status-card"><span>{label}</span><strong>{value}</strong></article>;
}
