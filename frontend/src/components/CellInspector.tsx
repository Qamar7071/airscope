import { Crosshair } from "lucide-react";
import type { GapsResponse, GridResponse, Locality } from "../types";
import { aqiBand } from "../utils/aqi";
import { GAP_COLORS } from "../utils/colors";
import { fmtCoord, fmtInt, fmtKm, fmtPct, fmtPm } from "../utils/formatting";
import { describeLocation } from "../utils/geo";
import { AqiBadge } from "./ui";

const CLASS_BY_CODE = ["low", "moderate", "high", "critical"];

function Bar({ label, value }: { label: string; value: number | null | undefined }) {
  const v = value ?? 0;
  return (
    <div className="grid grid-cols-[86px_1fr_32px] items-center gap-2 text-[11px]">
      <span className="text-txt-muted">{label}</span>
      <span className="h-1.5 rounded-full bg-ink-700">
        <span className="block h-full rounded-full bg-txt-secondary" style={{ width: `${Math.round(v * 100)}%` }} />
      </span>
      <span className="kbd-num text-right text-txt-secondary">{value == null ? "–" : v.toFixed(2)}</span>
    </div>
  );
}

interface Props {
  idx: number;
  lat: number;
  lon: number;
  grid: GridResponse;
  gaps?: GapsResponse;
  localities?: Locality[];
  onSimulate: () => void;
}

/** Everything AirScope knows about one grid cell. */
export default function CellInspector({ idx, lat, lon, grid, gaps, localities, onSimulate }: Props) {
  const L = grid.layers;
  const pm = L.pm25?.[idx] ?? null;
  const band = aqiBand(pm);
  const gapCode = gaps?.labels[idx];
  const gapClass = gapCode == null ? null : CLASS_BY_CODE[gapCode];
  return (
    <div className="w-[250px] space-y-2.5">
      <div>
        <div className="text-[13px] font-semibold text-txt-primary">{describeLocation(localities, lat, lon)}</div>
        <div className="text-[11px] text-txt-muted">{fmtCoord(lat, lon)} · {grid.mode === "period" ? `period average (${grid.hours} h sample)` : "selected hour"}</div>
      </div>
      {grid.pm25_available && (
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl font-semibold">{fmtPm(pm)}</span>
            {band && <AqiBadge category={band.short} color={band.color} textColor={band.text} />}
          </div>
          <div className="text-[11px] text-txt-secondary">
            90% interval {fmtPm(L.lower?.[idx])} – {fmtPm(L.upper?.[idx])} (±{fmtPct(L.relative_uncertainty?.[idx], 0)})
          </div>
        </div>
      )}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11.5px]">
        <dt className="text-txt-muted">Population density</dt>
        <dd className="text-right">{fmtInt(L.population[idx])} /km²</dd>
        <dt className="text-txt-muted">Nearest monitor</dt>
        <dd className="text-right">{fmtKm(L.nearest_station_km[idx])}</dd>
        <dt className="text-txt-muted">Coverage probability</dt>
        <dd className="text-right">{fmtPct(100 * (L.coverage[idx] ?? 0), 0)}</dd>
        {L.osse_error && (
          <>
            <dt className="text-txt-muted">OSSE actual error</dt>
            <dd className="text-right">{fmtPm(L.osse_error[idx])}</dd>
          </>
        )}
      </dl>
      {gaps && gapClass && (
        <div className="space-y-1.5 rounded-lg bg-white/[0.03] p-2 ring-1 ring-white/[0.06]">
          <div className="flex items-center justify-between text-[11.5px]">
            <span className="font-medium text-txt-primary">Monitoring Gap Index</span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ background: GAP_COLORS[gapClass] }} aria-hidden />
              <span className="kbd-num font-semibold">{gaps.gap_index[idx]?.toFixed(2)}</span>
              <span className="capitalize text-txt-secondary">{gapClass}</span>
            </span>
          </div>
          <Bar label="Coverage gap" value={gaps.components.coverage_deficit[idx]} />
          <Bar label="Uncertainty" value={gaps.components.uncertainty[idx]} />
          {gaps.pm25_available && <Bar label="Pollution" value={gaps.components.pollution[idx]} />}
          <Bar label="Population" value={gaps.components.population[idx]} />
        </div>
      )}
      <button className="btn-ghost w-full" onClick={onSimulate}>
        <Crosshair className="h-3.5 w-3.5" /> Simulate a sensor here
      </button>
    </div>
  );
}
