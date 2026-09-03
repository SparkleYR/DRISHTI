import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function SectionCard(props: {
  children: ReactNode;
  className?: string;
  description?: string;
  eyebrow: string;
  id?: string;
  icon: LucideIcon;
  title: string;
  trailing?: ReactNode;
}) {
  const Icon = props.icon;
  return (
    <section id={props.id} className={`scroll-mt-12 rounded-sm border border-slate-300 bg-white ${props.className ?? ""}`}>
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-300 px-5 py-4 sm:px-6">
        <div className="flex min-w-0 gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-sm border border-amber-200 bg-amber-50 text-amber-700" aria-hidden="true">
            <Icon size={19} strokeWidth={2} />
          </span>
          <div>
            <p className="text-xs font-semibold text-amber-700">{props.eyebrow}</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-900">{props.title}</h2>
            {props.description ? <p className="mt-1 max-w-3xl text-sm leading-5 text-slate-600">{props.description}</p> : null}
          </div>
        </div>
        {props.trailing}
      </header>
      {props.children}
    </section>
  );
}

export function StatusBadge(props: {
  children: ReactNode;
  tone?: "blue" | "green" | "red" | "slate" | "yellow";
}) {
  const tone = props.tone ?? "slate";
  const tones = {
    blue: "border-amber-300 bg-amber-50 text-amber-900",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    red: "border-red-200 bg-red-50 text-red-800",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
    yellow: "border-amber-300 bg-amber-50 text-amber-900",
  };
  return (
    <span className={`inline-flex min-h-7 items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs font-semibold ${tones[tone]}`}>
      {props.children}
    </span>
  );
}

export function Metric(props: {
  hint?: string;
  label: string;
  suffix?: string;
  value: string | number;
}) {
  return (
    <div className="rounded-sm border border-slate-300 bg-[#fcfbf9] px-4 py-3">
      <p className="text-xs font-semibold text-slate-600">{props.label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-slate-950">
        {props.value}{props.suffix ? <span className="ml-1 text-sm font-semibold text-slate-500">{props.suffix}</span> : null}
      </p>
      {props.hint ? <p className="mt-1 text-xs text-slate-500">{props.hint}</p> : null}
    </div>
  );
}
