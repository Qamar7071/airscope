import { AlertTriangle, BarChart3, CheckCircle2, FlaskConical } from "lucide-react";
import { useMetrics } from "../../hooks/useAirScopeData";
import { useCityStatus } from "../../hooks/useCityStatus";
import { useAppState, useDispatch } from "../../state/store";
import { fmtNum, fmtPct, fmtSignedPct } from "../../utils/formatting";
import { SectionTitle } from "../ui";

export default function EvidenceStep() {
  const s = useAppState();
  const dispatch = useDispatch();
  const { ready } = useCityStatus(s.cityId);
  const m = useMetrics(s.cityId, ready).data;
  if (!m) return <p className="text-xs text-txt-muted">Loading evaluation…</p>;
  if (!m.evaluation_available || !m.loso) {
    return <p className="text-xs text-txt-secondary">{m.message ?? "Fewer than 3 usable stations - spatial validation is not possible, so uncertainty is uncalibrated."}</p>;
  }
  const ens = m.loso.models[0];
  const baselines = m.loso.models.filter((r) => r.model.startsWith("Baseline"));
  const bench = m.osse?.placement_benchmark.scenarios ?? [];
  const best = bench.filter((x) => x.key === "coverage" || x.key === "variance").sort((a, b) => b.improvement_pct - a.improvement_pct)[0];
  const random = bench.find((x) => x.key === "random");
  const beats = best?.beats_random_draws;
  const draws = best?.random_draws;
  const withinNoise = best && random ? best.improvement_pct - random.improvement_pct < (random.improvement_std ?? 0) : false;
  const cal = m.calibration;
  const cov90 = cal ? cal.empirical_coverage[cal.levels.indexOf(0.9)] : null;

  return (
    <div className="space-y-4">
      {m.provenance?.synthetic && (
        <div className="flex gap-2 rounded-xl bg-status-warning/10 p-3 text-[11.5px] leading-snug text-status-warning ring-1 ring-status-warning/30">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{m.honesty_note}</span>
        </div>
      )}
      <div>
        <SectionTitle>Held-out stations (leave-one-station-out)</SectionTitle>
        <table className="w-full text-[11.5px]">
          <thead>
            <tr className="text-[10.5px] text-txt-muted">
              <th className="pb-1 text-left font-medium">Model</th>
              <th className="pb-1 text-right font-medium">RMSE</th>
              <th className="pb-1 text-right font-medium">R²</th>
            </tr>
          </thead>
          <tbody className="kbd-num">
            {[ens, ...baselines].map((r) => (
              <tr key={r.model} className="border-t border-white/[0.05]">
                <td className={`py-1 ${r === ens ? "font-medium text-txt-primary" : "text-txt-secondary"}`}>{r.model.replace("Baseline: ", "")}</td>
                <td className="py-1 text-right">{fmtNum(r.rmse, 1)}</td>
                <td className="py-1 text-right">{r.r2 == null ? "–" : r.r2.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className={`mt-2 flex gap-2 text-[11.5px] leading-snug ${m.loso.ensemble_beats_best_baseline ? "text-status-good" : "text-status-warning"}`}>
          {m.loso.ensemble_beats_best_baseline ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span>
            {m.loso.ensemble_beats_best_baseline
              ? `The ensemble beats the best simple baseline (${m.loso.best_baseline.replace("Baseline: ", "")}) at held-out stations.`
              : `At held-out stations the ensemble does not beat simple ${m.loso.best_baseline.replace("Baseline: ", "")}. With this few stations, spatial detail in the map is uncertain - which is why the uncertainty layer and new sensors matter.`}
          </span>
        </div>
        <p className="mt-1 text-[10.5px] text-txt-muted">RMSE in µg/m³. {m.data?.n_stations} stations, {m.data?.n_observations.toLocaleString()} station-hours.</p>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11.5px]">
        <div className="rounded-xl bg-white/[0.03] p-2.5 ring-1 ring-white/[0.06]">
          <div className="text-[10.5px] text-txt-muted">Random K-fold looks</div>
          <div className="text-base font-semibold">{fmtPct(m.random_kfold?.optimism_pct, 0)} better</div>
          <div className="text-[10.5px] text-txt-secondary">than honest spatial CV - why AirScope reports LOSO</div>
        </div>
        <div className="rounded-xl bg-white/[0.03] p-2.5 ring-1 ring-white/[0.06]">
          <div className="text-[10.5px] text-txt-muted">90% intervals cover</div>
          <div className="text-base font-semibold">{cov90 == null ? "–" : fmtPct(100 * cov90, 0)}</div>
          <div className="text-[10.5px] text-txt-secondary">of held-out readings (nested LOSO)</div>
        </div>
      </div>
      {m.osse && (
        <div>
          <SectionTitle>Synthetic-truth experiment (OSSE)</SectionTitle>
          <ul className="space-y-1 text-[11.5px] text-txt-secondary">
            <li className="flex justify-between"><span>City-wide RMSE, ensemble</span><span className="kbd-num text-txt-primary">{fmtNum(m.osse.reconstruction.metrics.rmse, 1)}</span></li>
            <li className="flex justify-between"><span>City-wide RMSE, IDW interpolation</span><span className="kbd-num text-txt-primary">{fmtNum(m.osse.reconstruction.idw_baseline.rmse, 1)}</span></li>
            <li className="flex justify-between"><span>Grid cells inside 90% interval</span><span className="kbd-num text-txt-primary">{fmtPct(100 * (m.osse.reconstruction.interval_coverage_90 ?? 0), 0)}</span></li>
          </ul>
          {best && random && (
            <div className={`mt-2 rounded-xl p-2.5 text-[11.5px] leading-snug ring-1 ${best.improvement_pct > 0 && !withinNoise ? "bg-status-good/10 text-txt-primary ring-status-good/30" : "bg-white/[0.03] text-txt-secondary ring-white/[0.06]"}`}>
              {best.improvement_pct >= 0 ? (
                <>Adding {m.osse.placement_benchmark.k} AirScope sites cut city-wide error by <b>{fmtPct(best.improvement_pct, 1)}</b></>
              ) : (
                <>Adding {m.osse.placement_benchmark.k} AirScope sites <b>raised</b> city-wide error by <b>{fmtPct(-best.improvement_pct, 1)}</b></>
              )}{" "}
              (random sites: {fmtSignedPct(random.improvement_pct, 1)} ± {fmtNum(random.improvement_std ?? 0, 1)})
              {beats != null && draws ? `; better than ${beats} of ${draws} random placements.` : "."}
              {best.improvement_pct < 0
                ? " Coverage and uncertainty still improve, but in this synthetic city stations in polluted hotspots shift the retrained model and raise errors elsewhere (preferential sampling). See the methodology."
                : withinNoise
                  ? " The gap to random placement is smaller than the spread between random draws, so treat it as indicative."
                  : ""}
            </div>
          )}
        </div>
      )}
      <div className="flex gap-2">
        <button className="btn-ghost flex-1" onClick={() => dispatch({ type: "openCharts", tab: "validation" })}>
          <BarChart3 className="h-4 w-4" /> Validation charts
        </button>
        {m.osse && (
          <button className="btn-ghost flex-1" onClick={() => dispatch({ type: "openCharts", tab: "osse" })}>
            <FlaskConical className="h-4 w-4" /> OSSE charts
          </button>
        )}
      </div>
    </div>
  );
}
