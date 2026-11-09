import { Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";

// Chart tokens (validated against the panel surface #13161b with the dataviz palette validator).
export const C = {
  s1: "#3987e5", // series 1 - blue
  s2: "#d95926", // series 2 - orange
  s3: "#199e70", // series 3 - aqua
  muted: "#5b616b", // de-emphasised series / baselines
  grid: "#262a31",
  axis: "#3a414c",
  tick: "#7f8792",
  text: "#b4bac4",
  surface: "#13161b",
};

export const axisProps = {
  stroke: C.axis,
  tick: { fill: C.tick, fontSize: 11 },
  tickLine: false,
} as const;

export const gridProps = { stroke: C.grid, vertical: false } as const;

export interface TableSpec {
  columns: string[];
  rows: (string | number | null)[][];
}

/** Chart container: title, one-line subtitle, optional table view (every chart has a table twin). */
export function ChartCard({ title, subtitle, children, table, note, height = 230 }: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  table?: TableSpec;
  note?: ReactNode;
  height?: number;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <section className="flex min-w-0 flex-col rounded-xl bg-white/[0.025] p-3 ring-1 ring-white/[0.06]">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[13px] font-semibold text-txt-primary">{title}</h3>
          {subtitle && <p className="text-[11px] leading-snug text-txt-muted">{subtitle}</p>}
        </div>
        {table && (
          <button
            className={`btn-icon h-7 w-7 shrink-0 ${showTable ? "bg-white/10 text-txt-primary" : ""}`}
            onClick={() => setShowTable((v) => !v)}
            aria-pressed={showTable}
            aria-label={showTable ? "Show chart" : "Show data table"}
            title={showTable ? "Show chart" : "Show data table"}
          >
            <Table2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {showTable && table ? (
        <div className="scroll-thin overflow-auto" style={{ maxHeight: height }}>
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-ink-900">
              <tr>
                {table.columns.map((c) => (
                  <th key={c} className="px-1.5 py-1 text-left font-medium text-txt-muted">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody className="kbd-num">
              {table.rows.map((r, i) => (
                <tr key={i} className="border-t border-white/[0.05]">
                  {r.map((v, j) => (
                    <td key={j} className="px-1.5 py-1 text-txt-secondary">{v ?? "–"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }} className="min-w-0">{children}</div>
      )}
      {note && <div className="mt-1.5 text-[10.5px] leading-snug text-txt-muted">{note}</div>}
    </section>
  );
}

interface TooltipItem {
  name?: string | number;
  value?: number | string | (number | string)[];
  color?: string;
  dataKey?: string | number;
}

/** Tooltip: values lead (strong), series names follow; short line keys, never boxes. */
export function ChartTooltip({ active, payload, label, format, labelFormat }: {
  active?: boolean;
  payload?: TooltipItem[];
  label?: string | number;
  format?: (v: number, name: string) => string;
  labelFormat?: (l: string | number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass rounded-lg px-2.5 py-2 text-[11px]">
      {label !== undefined && <div className="mb-1 text-txt-muted">{labelFormat ? labelFormat(label) : label}</div>}
      <ul className="space-y-0.5">
        {payload.map((p, i) => {
          const raw = p.value;
          const name = String(p.name ?? p.dataKey ?? "");
          const shown = Array.isArray(raw)
            ? raw.map((x) => (typeof x === "number" ? (format ? format(x, name) : x.toFixed(1)) : x)).join(" – ")
            : typeof raw === "number"
              ? format ? format(raw, name) : raw.toFixed(1)
              : raw;
          return (
            <li key={i} className="flex items-center gap-2">
              <span className="h-[2px] w-3 rounded-full" style={{ background: p.color }} aria-hidden />
              <span className="font-semibold text-txt-primary">{shown}</span>
              <span className="text-txt-secondary">{name}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Legend rendered as HTML: swatch shape mirrors the mark (line vs rect). */
export function Legend({ items }: { items: { label: string; color: string; shape?: "line" | "rect" | "dot" }[] }) {
  return (
    <ul className="mb-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-txt-secondary">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-1.5">
          {it.shape === "rect" ? (
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: it.color }} aria-hidden />
          ) : it.shape === "dot" ? (
            <span className="h-2 w-2 rounded-full" style={{ background: it.color }} aria-hidden />
          ) : (
            <span className="h-[2px] w-3.5 rounded-full" style={{ background: it.color }} aria-hidden />
          )}
          {it.label}
        </li>
      ))}
    </ul>
  );
}

export function EmptyChart({ children }: { children: ReactNode }) {
  return <div className="flex h-full items-center justify-center px-6 text-center text-xs text-txt-muted">{children}</div>;
}
