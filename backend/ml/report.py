"""Write docs/demo_results.md from the trained models' metrics files.

    python -m ml.report

Every number in the generated document is read from ``models/<city>/metrics.json``,
which the training pipeline computes; nothing is typed by hand. Re-run after
re-training so the documentation always matches the artifacts.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import PROJECT_DIR, get_settings, load_cities  # noqa: E402


def _f(v, d=1, suffix=""):
    return "–" if v is None else f"{v:.{d}f}{suffix}"


def build_report() -> str:
    settings = get_settings()
    lines = [
        "# AirScope demo results (generated)",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `python -m ml.report` from `backend/models/*/metrics.json`._",
        "",
        "> **All numbers below are computed on SYNTHETIC demo data** (AirScope's documented OSSE nature run).",
        "> They show how the pipeline behaves on realistic simulated data. They are **not** a validation",
        "> against real-world measurements and must not be quoted as real-world accuracy.",
        "",
    ]
    rows_loso, rows_cal, rows_osse, rows_bench = [], [], [], []
    for cid, city in load_cities().items():
        path = Path(settings.models_dir) / cid / "metrics.json"
        if not path.exists():
            lines.append(f"- {city.name}: no trained model found (run `make train`).")
            continue
        m = json.loads(path.read_text(encoding="utf-8"))
        loso = m.get("loso") or {}
        models = {r["model"]: r for r in loso.get("models", [])}
        ens = models.get("AirScope ensemble", {})
        idw = models.get("Baseline: inverse distance weighting", {})
        net = models.get("Baseline: network mean", {})
        rk = m.get("random_kfold") or {}
        rows_loso.append(
            f"| {city.name} | {m['data']['n_stations']} | {_f(ens.get('rmse'))} | {_f(ens.get('r2'), 2)} | {_f(idw.get('rmse'))} | "
            f"{_f(net.get('rmse'))} | {'yes' if loso.get('ensemble_beats_best_baseline') else 'no'} | {_f(rk.get('optimism_pct'), 0, '%')} |"
        )
        cal = m.get("calibration") or {}
        if cal:
            cov = dict(zip(cal.get("levels", []), cal.get("empirical_coverage", [])))
            var = m.get("variogram") or {}
            rows_cal.append(
                f"| {city.name} | {_f(100 * (cov.get(0.9) or 0), 0, '%')} | {_f(100 * (cov.get(0.5) or 0), 0, '%')} | "
                f"{_f(100 * (cal.get('model_only_coverage_90') or 0), 0, '%')} | {_f(var.get('range_km'), 1, ' km')} ({var.get('method', '–')}) |"
            )
        osse = m.get("osse") or {}
        if osse:
            rec = osse["reconstruction"]
            rows_osse.append(
                f"| {city.name} | {_f(rec['metrics']['rmse'])} | {_f(rec['idw_baseline']['rmse'])} | {_f(rec['population_weighted']['rmse'])} | "
                f"{_f(100 * (rec.get('interval_coverage_90') or 0), 0, '%')} | {_f(rec.get('uncertainty_error_spearman'), 2)} | {_f(rec.get('spatial_pattern_correlation'), 2)} |"
            )
            sc = {s["key"]: s for s in osse["placement_benchmark"]["scenarios"]}
            rnd = sc.get("random", {})
            def cell(key):
                s = sc.get(key)
                if not s:
                    return "–"
                extra = f" (beats {s['beats_random_draws']}/{s['random_draws']})" if "beats_random_draws" in s else ""
                return f"{_f(s['improvement_pct'], 1, '%')}{extra}"
            rows_bench.append(
                f"| {city.name} | {osse['placement_benchmark']['k']} | {cell('coverage')} | {cell('variance')} | {cell('population')} | "
                f"{_f(rnd.get('improvement_pct'), 1, '%')} ± {_f(rnd.get('improvement_std'), 1)} |"
            )
    lines += [
        "## 1. Leave-one-station-out (LOSO) validation",
        "",
        "Each station is predicted by a model trained without it. RMSE in µg/m³.",
        "",
        "| City | Stations | Ensemble RMSE | Ensemble R² | IDW RMSE | Network-mean RMSE | Ensemble beats best baseline? | Random K-fold optimism |",
        "|---|---|---|---|---|---|---|---|",
        *rows_loso,
        "",
        "_Random K-fold optimism_: how much lower the RMSE looks with a non-spatial random split - the reason AirScope reports LOSO.",
        "",
        "## 2. Uncertainty calibration (nested LOSO)",
        "",
        "| City | Coverage of 90% intervals | Coverage of 50% intervals | Tree-model spread only (90%) | Variogram range |",
        "|---|---|---|---|---|",
        *rows_cal,
        "",
        "## 3. OSSE: city-wide reconstruction against the synthetic truth",
        "",
        "| City | Ensemble RMSE | IDW RMSE | Population-weighted RMSE | Cells inside 90% interval | Uncertainty-error Spearman | Spatial pattern correlation |",
        "|---|---|---|---|---|---|---|",
        *rows_osse,
        "",
        "## 4. OSSE: city-wide error reduction from new stations",
        "",
        "Virtual stations sample the synthetic truth; the ensemble is retrained; city-wide RMSE is re-measured.",
        "",
        "| City | New stations | AirScope coverage | AirScope kriging variance | Population heuristic | Random (mean ± sd) |",
        "|---|---|---|---|---|---|",
        *rows_bench,
        "",
        "See `docs/methodology.md` for how each number is computed and for the limitations of these experiments.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    out = PROJECT_DIR / "docs" / "demo_results.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
