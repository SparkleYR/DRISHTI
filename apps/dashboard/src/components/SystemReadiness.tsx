import type { HealthResponse } from "@drishti/contracts";
import { CheckCircle2, ChevronDown, XCircle } from "lucide-react";
import { useState } from "react";

/**
 * One plain-language answer to the only infrastructure question a coordinator
 * has: can people go out and walk right now?
 *
 * Model names, VRAM counters, and per-stage timings are engineering detail, so
 * they live behind a disclosure that is closed by default — available when
 * something breaks and a technician needs to be told what is wrong.
 */
export function SystemReadiness(props: { health: HealthResponse }) {
  const [open, setOpen] = useState(false);
  const ready = props.health.walk_mode_available;
  const problems = Object.entries(props.health.models)
    .filter(([, model]) => model.status !== "READY")
    .map(([name, model]) => ({ name, ...model }));
  // Depth is a documented, permanent fallback rather than a fault to report.
  const blocking = problems.filter((problem) => problem.name !== "depth");

  return (
    <section
      className={`rounded-sm border ${ready ? "border-emerald-300 bg-emerald-50" : "border-red-300 bg-red-50"}`}
      aria-label="System readiness"
    >
      <div className="flex flex-wrap items-center gap-3 px-5 py-4 sm:px-6">
        {ready ? (
          <CheckCircle2 className="shrink-0 text-emerald-700" size={26} aria-hidden="true" />
        ) : (
          <XCircle className="shrink-0 text-red-700" size={26} aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          <p className={`text-base font-bold ${ready ? "text-emerald-950" : "text-red-950"}`}>
            {ready ? "Ready — people can walk" : "Not ready — Walk Mode is unavailable"}
          </p>
          <p className={`mt-0.5 text-sm ${ready ? "text-emerald-900" : "text-red-900"}`}>
            {ready
              ? blocking.length === 0
                ? "All assistance is working normally."
                : `Working, with reduced help: ${blocking.map((item) => plainName(item.name)).join(", ")}.`
              : "Phones will not be able to start Walk Mode until this is fixed."}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-sm border border-ink-200 bg-white px-3 text-[0.8rem] font-semibold text-ink-700 hover:border-amber-400 hover:bg-amber-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700"
        >
          Technical details
          <ChevronDown className={open ? "rotate-180 transition" : "transition"} size={14} aria-hidden="true" />
        </button>
      </div>
      {open ? (
        <div className="border-t border-ink-200 bg-white px-5 py-4 sm:px-6">
          <p className="text-[0.8rem] text-ink-500">
            Share this with your technical contact if something is wrong.
          </p>
          <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
            <div className="flex justify-between gap-3 border-b border-ink-200 pb-1.5 text-sm">
              <dt className="text-ink-500">Computer</dt>
              <dd className="font-semibold text-ink-900">{props.health.compute.device_name ?? "Unavailable"}</dd>
            </div>
            <div className="flex justify-between gap-3 border-b border-ink-200 pb-1.5 text-sm">
              <dt className="text-ink-500">Database</dt>
              <dd className="font-semibold text-ink-900">{props.health.database.status}</dd>
            </div>
            {Object.entries(props.health.models).map(([name, model]) => (
              <div className="flex justify-between gap-3 border-b border-ink-200 pb-1.5 text-sm" key={name}>
                <dt className="text-ink-500">{plainName(name)}</dt>
                <dd className={`font-semibold ${model.status === "READY" ? "text-ink-900" : "text-amber-800"}`}>
                  {model.status}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </section>
  );
}

function plainName(key: string): string {
  const names: Record<string, string> = {
    detector: "Obstacle detection",
    segmentation: "Floor and wall reading",
    tracker: "Movement tracking",
    depth: "Distance estimate",
    india_hazards: "Indoor hazard rules",
    ocr: "Sign reading",
    vlm: "Object finding",
  };
  return names[key] ?? key;
}
