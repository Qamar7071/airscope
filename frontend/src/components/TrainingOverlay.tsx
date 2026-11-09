import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, BrainCircuit, RefreshCw } from "lucide-react";
import { useCities } from "../hooks/useAirScopeData";
import { useCityStatus } from "../hooks/useCityStatus";
import { api } from "../services/api";
import { useAppState } from "../state/store";
import { ProgressBar } from "./ui";
import { useToast } from "./Toast";

/** Shown while the selected city's model is being trained (first start or after data changes). */
export default function TrainingOverlay() {
  const s = useAppState();
  const toast = useToast();
  const cities = useCities();
  const { status } = useCityStatus(s.cityId);
  const city = cities.data?.find((c) => c.id === s.cityId);
  const visible = !!status && (status.state === "training" || status.state === "pending" || status.state === "error");

  return (
    <AnimatePresence>
      {visible && status && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          className="pointer-events-auto glass absolute left-1/2 top-1/2 z-[1100] w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 rounded-2xl p-5"
          role="status"
          aria-live="polite"
        >
          {status.state === "error" ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-status-critical">
                <AlertTriangle className="h-5 w-5" aria-hidden />
                <h2 className="text-sm font-semibold">Training failed for {city?.name}</h2>
              </div>
              <p className="text-xs text-txt-secondary">{status.error}</p>
              <button
                className="btn-primary"
                onClick={() =>
                  api.retrain(s.cityId!).then(
                    () => toast.push({ kind: "info", title: "Retraining queued" }),
                    (e: Error) => toast.push({ kind: "error", title: "Could not queue retraining", description: e.message }),
                  )
                }
              >
                <RefreshCw className="h-4 w-4" /> Retry training
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2.5">
                <BrainCircuit className="h-5 w-5 text-brand-400" aria-hidden />
                <div>
                  <h2 className="text-sm font-semibold text-txt-primary">Preparing the {city?.name ?? ""} model</h2>
                  <p className="text-[11px] text-txt-muted">First run only - results are saved and reused afterwards.</p>
                </div>
              </div>
              <ProgressBar value={status.progress} />
              <p className="text-xs text-txt-secondary">{status.message}</p>
              <p className="text-[11px] leading-snug text-txt-muted">
                AirScope is training its model ensemble, validating it by leaving out one station at a time, calibrating the
                uncertainty, and (in demo mode) scoring sensor-placement strategies against the synthetic truth.
              </p>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
