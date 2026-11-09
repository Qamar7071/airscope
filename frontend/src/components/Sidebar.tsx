import { AnimatePresence, motion } from "framer-motion";
import { Activity, Gauge, MapPinned, ShieldAlert, Signal, Sigma } from "lucide-react";
import { useGrid } from "../hooks/useAirScopeData";
import { useCityStatus } from "../hooks/useCityStatus";
import { useAppState, useDispatch, useTimeParam } from "../state/store";
import type { StepId } from "../types";
import CoverageStep from "./steps/CoverageStep";
import EvidenceStep from "./steps/EvidenceStep";
import GapsStep from "./steps/GapsStep";
import PlacementStep from "./steps/PlacementStep";
import PollutionStep from "./steps/PollutionStep";
import UncertaintyStep from "./steps/UncertaintyStep";

const STEPS: { id: StepId; label: string; question: string; icon: typeof Activity }[] = [
  { id: "pollution", label: "Pollution", question: "Where is air pollution likely to be high?", icon: Activity },
  { id: "coverage", label: "Coverage", question: "Where does the city lack monitoring coverage?", icon: Signal },
  { id: "uncertainty", label: "Uncertainty", question: "Where is the model uncertain?", icon: Gauge },
  { id: "gaps", label: "Blind spots", question: "Which poorly observed areas matter most?", icon: ShieldAlert },
  { id: "placement", label: "Placement", question: "Where should new monitoring stations go?", icon: MapPinned },
  { id: "evidence", label: "Evidence", question: "How far can these results be trusted?", icon: Sigma },
];

const BODY: Record<StepId, () => JSX.Element> = {
  pollution: PollutionStep,
  coverage: CoverageStep,
  uncertainty: UncertaintyStep,
  gaps: GapsStep,
  placement: PlacementStep,
  evidence: EvidenceStep,
};

export default function Sidebar() {
  const s = useAppState();
  const dispatch = useDispatch();
  const { ready } = useCityStatus(s.cityId);
  const grid = useGrid(s.cityId, useTimeParam(), ready);
  const osseAvailable = !!grid.data?.layers.osse_error;
  const current = STEPS.find((x) => x.id === s.step)!;
  const Body = BODY[s.step];
  const idx = STEPS.findIndex((x) => x.id === s.step);

  return (
    <aside className="glass flex h-full min-h-0 flex-col rounded-xl" aria-label="Insight navigator">
      <nav className="grid grid-cols-6 gap-1 border-b border-white/[0.06] p-1.5" aria-label="Analysis steps">
        {STEPS.map((st, i) => {
          const active = st.id === s.step;
          const Icon = st.icon;
          return (
            <button
              key={st.id}
              onClick={() => dispatch({ type: "setStep", step: st.id, osseAvailable })}
              aria-current={active ? "step" : undefined}
              title={st.question}
              className={`group flex flex-col items-center gap-1 rounded-lg px-1 py-1.5 text-[10px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/70 ${
                active ? "bg-brand-500/15 text-brand-300 ring-1 ring-brand-400/40" : "text-txt-muted hover:bg-white/[0.05] hover:text-txt-primary"
              }`}
            >
              <span className="relative">
                <Icon className="h-4 w-4" aria-hidden />
                <span className={`absolute -right-2 -top-1.5 text-[8px] ${active ? "text-brand-300" : "text-txt-muted"}`}>{i + 1}</span>
              </span>
              <span className="truncate">{st.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="px-4 pb-1 pt-3">
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-brand-400">Step {idx + 1} of 6</p>
        <h2 className="mt-0.5 text-[15px] font-semibold leading-snug text-txt-primary">{current.question}</h2>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-2">
        <AnimatePresence mode="wait">
          <motion.div key={s.step + (s.cityId ?? "")} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 6 }} transition={{ duration: 0.15 }}>
            <Body />
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="flex items-center justify-between border-t border-white/[0.06] px-3 py-2">
        <button
          className="btn-ghost px-2 py-1 text-xs"
          disabled={idx === 0}
          onClick={() => dispatch({ type: "setStep", step: STEPS[idx - 1].id, osseAvailable })}
        >
          ← {idx > 0 ? STEPS[idx - 1].label : "Back"}
        </button>
        <button
          className="btn-primary px-2 py-1 text-xs"
          disabled={idx === STEPS.length - 1}
          onClick={() => dispatch({ type: "setStep", step: STEPS[idx + 1].id, osseAvailable })}
        >
          {idx < STEPS.length - 1 ? STEPS[idx + 1].label : "Done"} →
        </button>
      </div>
    </aside>
  );
}
