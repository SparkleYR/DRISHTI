import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * One section of the dashboard.
 *
 * The header is deliberately quiet: a small uppercase eyebrow, a serif title,
 * and a rule. Earlier revisions put a coloured icon chip on every card, which
 * made four equally-loud boxes and destroyed any sense of priority — the icon
 * now sits inline with the eyebrow at label size, so the title carries the card.
 */
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
    <section
      id={props.id}
      className={`scroll-mt-12 rounded-sm border border-ink-200 bg-white ${props.className ?? ""}`}
    >
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-ink-200 px-6 py-5 sm:px-7">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.09em] text-amber-800">
            <Icon size={13} strokeWidth={2.4} aria-hidden="true" />
            {props.eyebrow}
          </p>
          <h2 className="mt-1.5 text-2xl font-semibold leading-tight text-ink-900">{props.title}</h2>
          {props.description ? (
            <p className="mt-2 max-w-2xl text-[0.9rem] leading-6 text-ink-500">{props.description}</p>
          ) : null}
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
    green: "border-emerald-300 bg-emerald-50 text-emerald-900",
    red: "border-red-300 bg-red-50 text-red-900",
    slate: "border-ink-200 bg-ink-50 text-ink-600",
    yellow: "border-amber-300 bg-amber-50 text-amber-900",
  };
  return (
    <span
      className={`inline-flex min-h-8 items-center gap-1.5 whitespace-nowrap rounded-sm border px-2.5 text-[0.8rem] font-semibold ${tones[tone]}`}
    >
      {props.children}
    </span>
  );
}

/** A single figure. The number is the point, so it gets the serif and the size. */
export function Metric(props: {
  hint?: string;
  label: string;
  suffix?: string;
  value: string | number;
}) {
  return (
    <div className="border-l-2 border-ink-200 pl-4">
      <p className="text-[0.75rem] font-semibold uppercase tracking-[0.07em] text-ink-500">{props.label}</p>
      <p className="mt-1.5 font-display text-4xl font-semibold leading-none tabular text-ink-900">
        {props.value}
        {props.suffix ? (
          <span className="ml-1.5 font-sans text-base font-semibold text-ink-400">{props.suffix}</span>
        ) : null}
      </p>
      {props.hint ? <p className="mt-2 text-[0.8rem] leading-5 text-ink-500">{props.hint}</p> : null}
    </div>
  );
}
