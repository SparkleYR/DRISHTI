import type { HazardSeverity, RouteAccessibilityScore } from "@drishti/contracts";
import { MapPin, Plus } from "lucide-react";
import { useState } from "react";

const SEVERITIES: HazardSeverity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

/**
 * Lets the coordinator file an obstacle they saw themselves, rather than
 * waiting for a walker to report it.
 *
 * Every value on the wire is either typed by the operator or read from the
 * live route — nothing about the map is baked in here. When the backend has no
 * route configured the position fields disappear and the report is filed
 * without a map coordinate, which the contract allows.
 */
export function ReportHazard(props: {
  busy: boolean;
  onSubmit: (input: {
    category: string;
    severity: HazardSeverity;
    temporary: boolean;
    position: { x: number; y: number } | null;
  }) => Promise<void>;
  route: RouteAccessibilityScore | null;
}) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState<HazardSeverity>("MEDIUM");
  const [temporary, setTemporary] = useState(true);
  const [x, setX] = useState("0.50");
  const [y, setY] = useState("0.50");

  const canPlace = props.route !== null;
  const trimmed = category.trim();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!trimmed) return;
    const px = Number(x);
    const py = Number(y);
    const usable = canPlace && Number.isFinite(px) && Number.isFinite(py);
    await props.onSubmit({
      category: trimmed,
      severity,
      temporary,
      position: usable ? { x: clamp01(px), y: clamp01(py) } : null,
    });
    setCategory("");
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-10 items-center gap-2 rounded-sm border border-ink-300 bg-white px-3.5 text-[0.85rem] font-semibold text-ink-700 hover:border-amber-500 hover:bg-amber-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700"
      >
        <Plus size={15} aria-hidden="true" />
        Report an obstacle
      </button>
    );
  }

  return (
    <form
      onSubmit={(event) => void submit(event)}
      className="w-full rounded-sm border border-amber-300 bg-amber-50/60 p-5"
      aria-label="Report an obstacle you have seen"
    >
      <p className="font-display text-lg font-semibold text-ink-900">Report an obstacle you have seen</p>
      <p className="mt-1 text-[0.85rem] text-ink-500">
        Filed under your own observation. No photograph is stored.
      </p>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <label className="grid gap-1.5 text-[0.8rem] font-semibold text-ink-600">
          What is it?
          <input
            autoFocus
            required
            maxLength={96}
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="e.g. chair blocking the corridor"
            className="min-h-11 w-full rounded-sm border border-ink-300 bg-white px-3 text-[0.95rem] font-medium text-ink-900 outline-none placeholder:font-normal placeholder:text-ink-400 focus:border-amber-600 focus:ring-2 focus:ring-amber-100"
          />
        </label>

        <label className="grid gap-1.5 text-[0.8rem] font-semibold text-ink-600">
          How serious?
          <select
            value={severity}
            onChange={(event) => setSeverity(event.target.value as HazardSeverity)}
            className="min-h-11 w-full rounded-sm border border-ink-300 bg-white px-3 text-[0.95rem] font-medium text-ink-900 outline-none focus:border-amber-600 focus:ring-2 focus:ring-amber-100"
          >
            {SEVERITIES.map((value) => (
              <option key={value} value={value}>
                {value.charAt(0) + value.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </label>
      </div>

      {canPlace ? (
        <div className="mt-4">
          <p className="flex items-center gap-1.5 text-[0.8rem] font-semibold text-ink-600">
            <MapPin size={14} aria-hidden="true" />
            Where on {props.route?.route_name}?
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-4">
            <Coord label="Across" value={x} onChange={setX} />
            <Coord label="Along" value={y} onChange={setY} />
            <span className="text-[0.8rem] text-ink-400">0 = top left, 1 = bottom right</span>
          </div>
        </div>
      ) : (
        <p className="mt-4 text-[0.85rem] text-ink-500">
          No route is configured, so this will be filed without a position on the map.
        </p>
      )}

      <label className="mt-4 flex items-center gap-2.5 text-[0.9rem] font-medium text-ink-700">
        <input
          type="checkbox"
          checked={temporary}
          onChange={(event) => setTemporary(event.target.checked)}
          className="size-4 accent-amber-700"
        />
        This will move on its own (expires automatically)
      </label>

      <div className="mt-5 flex flex-wrap gap-2.5">
        <button
          type="submit"
          disabled={props.busy || !trimmed}
          className="inline-flex min-h-11 items-center rounded-sm bg-amber-800 px-4 text-[0.9rem] font-semibold text-white hover:bg-amber-900 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700"
        >
          {props.busy ? "Filing…" : "File this report"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="inline-flex min-h-11 items-center rounded-sm border border-ink-300 bg-white px-4 text-[0.9rem] font-semibold text-ink-700 hover:bg-ink-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function Coord(props: { label: string; onChange: (value: string) => void; value: string }) {
  return (
    <label className="grid gap-1 text-[0.8rem] font-semibold text-ink-600">
      {props.label}
      <input
        type="number"
        min={0}
        max={1}
        step={0.01}
        value={props.value}
        onChange={(event) => props.onChange(event.target.value)}
        className="min-h-10 w-24 rounded-sm border border-ink-300 bg-white px-2.5 text-[0.95rem] tabular text-ink-900 outline-none focus:border-amber-600 focus:ring-2 focus:ring-amber-100"
      />
    </label>
  );
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}
