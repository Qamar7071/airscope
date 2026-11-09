import { ScanSearch } from "lucide-react";
import { useGrid, useMetrics } from "../../hooks/useAirScopeData";
import { useCityStatus } from "../../hooks/useCityStatus";
import { useAppState, useDispatch, useTimeParam } from "../../state/store";
import { fmtKm, fmtPct } from "../../utils/formatting";
import MetricsPanel from "../MetricsPanel";
import { SectionTitle } from "../ui";

export default function UncertaintyStep() {
  const s = useAppState();
  const dispatch = useDispatch();
  const { ready } = useCityStatus(s.cityId);
  const grid = useGrid(s.cityId, useTimeParam(), ready);
  const metrics = useMetrics(s.cityId, ready);
  const u = grid.data?.stats.uncertainty;
  const cal = metrics.data?.calibration;
  const cov90 = cal ? cal.empirical_coverage[cal.levels.indexOf(0.9)] : null;
  const um = grid.data?.uncertainty_model;
  const osse = metrics.data?.osse?.reconstruction;

  return (
    <div className="space-y-4">
      <p className="text-xs leading-relaxed text-txt-secondary">
        Every estimate carries a calibrated 90% interval. Uncertainty grows away from stations and under unusual conditions - exactly
        where a new sensor would teach the model the most.
      </p>
      <MetricsPanel
        loading={!u}
        tiles={[
          { label: "Typical 90% interval", value: `±${fmtPct(u?.mean_relative_pct, 0)}`, sub: `±${Math.round(u?.mean_halfwidth ?? 0)} µg/m³ on average` },
          { label: "Least certain cell", value: `±${fmtPct(u?.max_relative_pct, 0)}`, sub: "relative half-width" },
          {
            label: "Calibrated coverage (90%)",
            value: cov90 == null ? "–" : fmtPct(100 * cov90, 0),
            sub: "held-out stations, nested LOSO",
            tone: cov90 != null && Math.abs(cov90 - 0.9) <= 0.05 ? "good" : "default",
            hint: "Share of held-out station readings that fell inside the 90% interval. Ideal: 90%.",
          },
          {
            label: "Tree-model spread alone",
            value: cal?.model_only_coverage_90 == null ? "–" : fmtPct(100 * cal.model_only_coverage_90, 0),
            sub: "coverage without the spatial term",
            tone: "bad",
            hint: "Quantile + ensemble spread only. Tree models are over-confident far from stations; AirScope's kriging term fixes this.",
          },
        ]}
      />
      <div>
        <SectionTitle>How the uncertainty is built</SectionTitle>
        <ol className="list-decimal space-y-1.5 pl-4 text-[11.5px] leading-snug text-txt-secondary">
          <li><span className="text-txt-primary">Conditional spread</span> from quantile gradient-boosting models (5th–95th percentile).</li>
          <li><span className="text-txt-primary">Model disagreement</span> between the ensemble members.</li>
          <li>
            <span className="text-txt-primary">Spatial blind-spot term</span>: kriging variance from the station layout (range {fmtKm(um?.range_km)}, nugget{" "}
            {um ? `${Math.round(100 * um.nugget_ratio)}%` : "–"}), scaled by the error seen at held-out stations.
          </li>
          <li><span className="text-txt-primary">Conformal calibration</span>: one scale factor ({um?.scale.toFixed(2) ?? "–"}) so 90% intervals cover 90% of held-out errors.</li>
        </ol>
      </div>
      {osse && (
        <div className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
          <div className="flex items-center gap-2 text-xs font-semibold text-txt-primary">
            <ScanSearch className="h-4 w-4 text-brand-400" aria-hidden /> Check against the synthetic truth
          </div>
          <p className="mt-1 text-[11.5px] leading-snug text-txt-secondary">
            In the demo, the true field is known. 90% intervals covered {fmtPct(100 * (osse.interval_coverage_90 ?? 0), 0)} of grid cells, and the
            uncertainty map ranks cells by their actual error with Spearman ρ = {osse.uncertainty_error_spearman?.toFixed(2) ?? "–"}.
          </p>
          <button className="btn-ghost mt-2 w-full" onClick={() => dispatch({ type: "setLayer", layer: s.layer === "osse_error" ? "uncertainty" : "osse_error" })}>
            {s.layer === "osse_error" ? "Back to the uncertainty layer" : "Show the actual error map"}
          </button>
        </div>
      )}
    </div>
  );
}
