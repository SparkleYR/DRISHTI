import type { HazardRecord, HazardStatus } from "@drishti/contracts";
import { ClipboardCheck, Merge, UserRoundCog } from "lucide-react";

import { SectionCard, StatusBadge } from "./ui";

export function HazardOperations(props: {
  assignedTo: string;
  duplicateId: string;
  hazards: HazardRecord[];
  onMerge: (hazard: HazardRecord) => Promise<void>;
  onStatus: (hazard: HazardRecord, status: HazardStatus) => Promise<void>;
  operatorAlias: string;
  setAssignedTo: (value: string) => void;
  setDuplicateId: (value: string) => void;
  setOperatorAlias: (value: string) => void;
  workingId: string | null;
}) {
  return (
    <SectionCard
      description="Review, assign, resolve, and consolidate anonymous local reports with optimistic version checks."
      eyebrow="Operations"
      icon={ClipboardCheck}
      id="settings"
      title="Hazard Verification Queue"
      trailing={<StatusBadge tone={props.hazards.length ? "yellow" : "green"}>{props.hazards.length} active</StatusBadge>}
    >
      <div className="border-b border-slate-300 bg-[#fcfbf9] p-5 sm:p-6">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Operator alias" value={props.operatorAlias} onChange={props.setOperatorAlias} />
          <Field label="Assign to" value={props.assignedTo} onChange={props.setAssignedTo} />
          <Field label="Duplicate report ID" value={props.duplicateId} onChange={props.setDuplicateId} />
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="border-b border-slate-300 bg-white text-xs text-slate-600">
            <tr><th className="px-6 py-3 font-semibold">Hazard</th><th className="px-4 py-3 font-semibold">Severity</th><th className="px-4 py-3 font-semibold">Status</th><th className="px-4 py-3 font-semibold">Confidence</th><th className="px-4 py-3 font-semibold">Observations</th><th className="px-6 py-3 text-right font-semibold">Actions</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {props.hazards.map((hazard) => (
              <tr className="hover:bg-amber-50/40" key={hazard.id}>
                <th className="px-6 py-4"><p className="font-bold text-slate-950">{hazard.category}</p><p className="mt-1 max-w-[260px] truncate font-mono text-[11px] font-normal text-slate-500">{hazard.id}</p></th>
                <td className="px-4 py-4"><StatusBadge tone={severityTone(hazard.severity)}>{hazard.severity}</StatusBadge></td>
                <td className="px-4 py-4 font-semibold text-slate-700">{hazard.status.replace("_", " ")}</td>
                <td className="px-4 py-4 tabular-nums text-slate-700">{Math.round(hazard.confidence * 100)}%</td>
                <td className="px-4 py-4 tabular-nums text-slate-700">{hazard.confirmation_count}</td>
                <td className="px-6 py-4"><div className="flex flex-wrap justify-end gap-2">{nextActions(hazard.status).map(([label, status]) => <ActionButton disabled={props.workingId === hazard.id} key={status} label={label} onClick={() => void props.onStatus(hazard, status)} />)}<ActionButton disabled={props.workingId === hazard.id} icon={Merge} label="Merge" onClick={() => void props.onMerge(hazard)} /></div></td>
              </tr>
            ))}
            {props.hazards.length === 0 ? <tr><td className="px-6 py-10 text-center text-slate-500" colSpan={6}>No active hazard reports require action.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function Field(props: { label: string; onChange: (value: string) => void; value: string }) {
  return <label className="grid gap-1.5 text-xs font-semibold text-slate-700">{props.label}<span className="relative"><UserRoundCog className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={15} aria-hidden="true" /><input className="min-h-10 w-full rounded-sm border border-slate-300 bg-white pl-9 pr-3 text-sm font-medium text-slate-950 outline-none placeholder:text-slate-400 focus:border-amber-600 focus:ring-2 focus:ring-amber-100" value={props.value} onChange={(event) => props.onChange(event.target.value)} /></span></label>;
}

function ActionButton(props: { disabled: boolean; icon?: typeof Merge; label: string; onClick: () => void }) {
  const Icon = props.icon;
  return <button disabled={props.disabled} onClick={props.onClick} type="button" className="inline-flex min-h-8 items-center gap-1.5 rounded-sm border border-slate-300 bg-white px-2.5 text-xs font-semibold text-slate-800 hover:border-amber-400 hover:bg-amber-50 disabled:cursor-wait disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700">{Icon ? <Icon size={13} aria-hidden="true" /> : null}{props.label}</button>;
}

function nextActions(status: HazardStatus): Array<[string, HazardStatus]> {
  if (status === "NEW") return [["Verify", "VERIFIED"], ["Reject", "REJECTED"]];
  if (status === "VERIFIED") return [["Assign", "ASSIGNED"], ["Resolve", "RESOLVED"], ["Reject", "REJECTED"]];
  if (status === "ASSIGNED") return [["Start", "IN_PROGRESS"], ["Resolve", "RESOLVED"]];
  if (status === "IN_PROGRESS") return [["Resolve", "RESOLVED"]];
  return [];
}

function severityTone(severity: HazardRecord["severity"]): "green" | "red" | "slate" | "yellow" {
  if (severity === "CRITICAL" || severity === "HIGH") return "red";
  if (severity === "MEDIUM") return "yellow";
  return "green";
}
