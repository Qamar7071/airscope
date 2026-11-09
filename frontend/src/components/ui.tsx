import { HelpCircle } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

export function StatTile({ label, value, sub, tone = "default", hint }: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "good" | "bad" | "brand";
  hint?: string;
}) {
  const toneCls = tone === "good" ? "text-status-good" : tone === "bad" ? "text-status-serious" : tone === "brand" ? "text-brand-300" : "text-txt-primary";
  return (
    <div className="rounded-xl bg-white/[0.03] px-3 py-2.5 ring-1 ring-white/[0.06]">
      <div className="flex items-center gap-1 text-[11px] text-txt-muted">
        <span>{label}</span>
        {hint && <InfoTip text={hint} />}
      </div>
      <div className={`mt-0.5 text-lg font-semibold leading-tight ${toneCls}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] leading-snug text-txt-secondary">{sub}</div>}
    </div>
  );
}

export function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        className="text-txt-muted hover:text-txt-secondary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-400 rounded"
        aria-describedby={open ? id : undefined}
        aria-label="More information"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
      >
        <HelpCircle className="h-3 w-3" />
      </button>
      {open && (
        <span id={id} role="tooltip" className="glass absolute left-1/2 top-5 z-50 w-60 -translate-x-1/2 rounded-lg px-2.5 py-2 text-[11px] font-normal normal-case leading-snug tracking-normal text-txt-secondary">
          {text}
        </span>
      )}
    </span>
  );
}

export function Slider({ label, value, min, max, step, onChange, format, hint }: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  hint?: string;
}) {
  const id = useId();
  const fill = `${((value - min) / (max - min)) * 100}%`;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <label htmlFor={id} className="flex items-center gap-1 text-txt-secondary">
          {label}
          {hint && <InfoTip text={hint} />}
        </label>
        <span className="kbd-num font-medium text-txt-primary">{format ? format(value) : value}</span>
      </div>
      <input
        id={id}
        type="range"
        className="range"
        min={min}
        max={max}
        step={step}
        value={value}
        style={{ ["--fill" as string]: fill }}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

export function Toggle({ label, checked, onChange, swatch, hint }: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  swatch?: ReactNode;
  hint?: string;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 py-1 text-xs text-txt-secondary hover:text-txt-primary">
      <span className="flex items-center gap-2">
        {swatch}
        {label}
        {hint && <InfoTip text={hint} />}
      </span>
      <span className="relative inline-flex">
        <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="h-4 w-7 rounded-full bg-ink-600 transition-colors peer-checked:bg-brand-500 peer-focus-visible:ring-2 peer-focus-visible:ring-brand-400/70" />
        <span className="absolute left-0.5 top-0.5 h-3 w-3 rounded-full bg-txt-primary transition-transform peer-checked:translate-x-3" />
      </span>
    </label>
  );
}

export function Segmented<T extends string>({ options, value, onChange, size = "md", ariaLabel }: {
  options: { value: T; label: ReactNode; title?: string }[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md";
  ariaLabel: string;
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex rounded-lg bg-white/[0.04] p-0.5 ring-1 ring-white/10">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            role="radio"
            aria-checked={active}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={`rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/70 ${
              size === "sm" ? "px-2 py-1 text-[11px]" : "px-3 py-1.5 text-xs"
            } ${active ? "bg-brand-500 text-ink-950 shadow" : "text-txt-secondary hover:text-txt-primary"}`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-2 mt-4 flex items-center justify-between first:mt-0">
      <h3 className="panel-title">{children}</h3>
      {right}
    </div>
  );
}

export function ProgressBar({ value, tone = "brand" }: { value: number; tone?: "brand" | "critical" }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)}>
      <div className={`h-full rounded-full transition-[width] duration-500 ${tone === "brand" ? "bg-brand-400" : "bg-status-critical"}`} style={{ width: `${Math.max(2, value * 100)}%` }} />
    </div>
  );
}

export function AqiBadge({ category, color, textColor }: { category: string | null; color: string; textColor: string }) {
  if (!category) return null;
  return (
    <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10.5px] font-semibold" style={{ background: color, color: textColor }}>
      {category}
    </span>
  );
}

/** Thin segmented bar (part-to-whole) with an accessible description. */
export function SegmentedBar({ parts, label }: { parts: { key: string; value: number; color: string; name: string }[]; label: string }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  const desc = parts.filter((p) => p.value > 0).map((p) => `${p.name}: ${((100 * p.value) / total).toFixed(1)}%`).join(", ");
  return (
    <div className="flex h-2 w-full gap-[2px] overflow-hidden rounded-full" role="img" aria-label={`${label}. ${desc}`}>
      {parts.filter((p) => p.value > 0).map((p) => (
        <div key={p.key} title={`${p.name}: ${((100 * p.value) / total).toFixed(1)}%`} style={{ width: `${(100 * p.value) / total}%`, background: p.color }} />
      ))}
    </div>
  );
}
