import type { ReactNode } from "react";
import { StatTile } from "./ui";

export interface Tile {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "good" | "bad" | "brand";
  hint?: string;
}

/** A compact grid of KPI tiles. Values are formatted by the caller; nothing here invents numbers. */
export default function MetricsPanel({ tiles, loading }: { tiles: Tile[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-2" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-[66px] animate-pulse rounded-xl bg-white/[0.03] ring-1 ring-white/[0.06]" />
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2">
      {tiles.map((t) => (
        <StatTile key={t.label} {...t} />
      ))}
    </div>
  );
}
