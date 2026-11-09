import { AnimatePresence, motion } from "framer-motion";
import { ExternalLink, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useHealth, useSources } from "../hooks/useAirScopeData";
import { useAppState, useDispatch } from "../state/store";
import { Segmented } from "./ui";

type Tab = "overview" | "method" | "data" | "limits";

function Overview() {
  return (
    <div className="space-y-3 text-[13px] leading-relaxed text-txt-secondary">
      <p>
        Many Pakistani cities have only a handful of air-quality monitors, so most neighbourhoods have no direct PM2.5 measurement at all.
        <span className="text-txt-primary"> AirScope's central idea is to find those monitoring blind spots and say where new sensors would help most.</span>
      </p>
      <ol className="list-decimal space-y-1.5 pl-5">
        <li><span className="text-txt-primary">City-wide estimation</span> - an ML ensemble estimates PM2.5 everywhere from sparse stations, weather and geography.</li>
        <li><span className="text-txt-primary">Blind-spot detection</span> - the Monitoring Gap Index combines coverage, calibrated uncertainty, pollution and population.</li>
        <li><span className="text-txt-primary">Optimal sensor placement</span> - greedy optimisation proposes coordinates for new monitors and quantifies the improvement.</li>
      </ol>
      <p>
        The offline demo is an <span className="text-txt-primary">Observing System Simulation Experiment (OSSE)</span>, the method atmospheric
        scientists use to design observing networks: a documented synthetic "truth" field is sampled by simulated stations, so AirScope's
        estimates and placement strategies can be scored against a known answer. All demo data are labelled synthetic; no real measurements
        are shown and no real-world accuracy is claimed.
      </p>
    </div>
  );
}

function Method() {
  const steps = [
    ["Data & QC", "Hourly PM2.5 (OpenAQ v3 in live mode) and weather (Open-Meteo). Range checks, stuck-sensor and spike (Hampel) filters, completeness rules; every removal is counted."],
    ["Features", "Location, elevation, distance to centre, log population density; cyclic hour/day-of-year, month; temperature, humidity, wind u/v, pressure, boundary-layer height, ventilation index; mean and IDW of the other stations at the same hour."],
    ["Model", "Pre-specified ensemble (random forest + histogram gradient boosting + XGBoost when installed) on log PM2.5, combined as a geometric mean. Median imputation inside the saved pipeline."],
    ["Validation", "Leave-one-station-out CV against simple baselines (training mean, network mean, IDW); random K-fold shown only to expose its optimism; permutation importance on held-out stations."],
    ["Uncertainty", "Quantile-model spread + ensemble disagreement + a kriging-variance term from the station layout, scaled by a conformal factor; coverage checked with nested LOSO."],
    ["Gap index", "MGI = observation deficit^α × exposure need^(1−α), components robustly scaled within the city; critical clusters found by connected-component labelling."],
    ["Placement", "Greedy maximisation of need-weighted probabilistic coverage (monotone submodular, (1−1/e) guarantee without constraints) or kriging-variance reduction, with spacing, distance and population constraints."],
    ["OSSE", "Demo only: reconstruction error against the synthetic truth everywhere, and a placement benchmark that retrains with virtual stations for each strategy and for random draws."],
  ];
  return (
    <dl className="space-y-2.5">
      {steps.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[110px_1fr] gap-3 text-[12.5px]">
          <dt className="font-semibold text-txt-primary">{k}</dt>
          <dd className="leading-relaxed text-txt-secondary">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Data() {
  const sources = useSources();
  const health = useHealth();
  return (
    <div className="space-y-3">
      <p className="text-[12.5px] text-txt-secondary">
        Current mode: <span className="font-semibold text-txt-primary">{health.data?.data_mode === "live" ? "live (OpenAQ + Open-Meteo)" : "offline demo (synthetic)"}</span>.
        {!health.data?.openaq_key_configured && " Live mode needs a free OpenAQ API key in backend/.env (see README)."}
      </p>
      <ul className="space-y-2">
        {sources.data?.sources.map((src) => (
          <li key={src.id} className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/[0.06]">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-semibold text-txt-primary">{src.name}</span>
              {src.url && (
                <a href={src.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] text-brand-300 hover:underline">
                  Website <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
            <p className="mt-1 text-[12px] text-txt-secondary">{src.used_for}</p>
            <p className="mt-1 text-[11.5px] text-txt-muted"><span className="text-txt-secondary">Licence:</span> {src.license}</p>
            <p className="text-[11.5px] text-txt-muted"><span className="text-txt-secondary">Attribution:</span> {src.attribution}</p>
            <p className="text-[11.5px] text-txt-muted"><span className="text-txt-secondary">Access:</span> {src.access}</p>
          </li>
        ))}
      </ul>
      {sources.data?.standards.map((st) => (
        <p key={st.id} className="text-[11.5px] text-txt-muted"><span className="text-txt-secondary">{st.name}.</span> {st.note}</p>
      ))}
    </div>
  );
}

function Limits() {
  const items = [
    "With few, mostly central stations, any spatial model is weakly constrained. AirScope reports held-out errors honestly - including when simple interpolation does as well - and widens its intervals far from stations.",
    "Demo results come from a synthetic world. They demonstrate that the methodology works as designed; they are not evidence of accuracy in real Islamabad, Lahore or Karachi.",
    "Bundled population and elevation surfaces are documented approximations; replace them with WorldPop/GHSL and a DEM for real planning.",
    "Analysis domains are hand-digitised approximations, not administrative boundaries.",
    "Station representativeness (coverage radius) and the gap-index weights are policy choices exposed as parameters, not facts.",
    "Recommended coordinates are candidates for a field survey; power, access, security and permissions decide final siting.",
    "The AQI is defined for 24-hour means; hourly categories are shown for orientation only.",
  ];
  return (
    <ul className="list-disc space-y-2 pl-5 text-[12.5px] leading-relaxed text-txt-secondary">
      {items.map((i) => (
        <li key={i}>{i}</li>
      ))}
    </ul>
  );
}

export default function AboutModal() {
  const s = useAppState();
  const dispatch = useDispatch();
  const [tab, setTab] = useState<Tab>("overview");
  const close = () => dispatch({ type: "setAboutOpen", open: false });
  useEffect(() => {
    if (!s.aboutOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.aboutOpen]);

  return (
    <AnimatePresence>
      {s.aboutOpen && (
        <motion.div className="fixed inset-0 z-[1500] flex items-center justify-center bg-black/60 p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={close}>
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="about-title"
            initial={{ y: 16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 10, opacity: 0 }}
            className="glass flex max-h-[86vh] w-[min(96vw,760px)] flex-col rounded-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3.5">
              <div>
                <h2 id="about-title" className="text-base font-semibold text-txt-primary">About AirScope</h2>
                <p className="text-[11.5px] text-txt-muted">AI-driven monitoring-gap discovery and optimal sensor placement</p>
              </div>
              <button className="btn-icon" onClick={close} aria-label="Close dialog">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="px-5 pt-3">
              <Segmented
                ariaLabel="About sections"
                size="sm"
                value={tab}
                onChange={setTab}
                options={[
                  { value: "overview", label: "Overview" },
                  { value: "method", label: "Method" },
                  { value: "data", label: "Data & licences" },
                  { value: "limits", label: "Limitations" },
                ]}
              />
            </div>
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {tab === "overview" && <Overview />}
              {tab === "method" && <Method />}
              {tab === "data" && <Data />}
              {tab === "limits" && <Limits />}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
