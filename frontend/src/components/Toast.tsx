import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type Kind = "success" | "info" | "error";

interface ToastItem {
  id: number;
  kind: Kind;
  title: string;
  description?: string;
}

interface ToastApi {
  push: (t: Omit<ToastItem, "id">) => void;
}

const Ctx = createContext<ToastApi>({ push: () => undefined });

const ICONS = { success: CheckCircle2, info: Info, error: AlertTriangle };
const TONE: Record<Kind, string> = {
  success: "text-status-good",
  info: "text-brand-400",
  error: "text-status-critical",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = useCallback(
    (t: Omit<ToastItem, "id">) => {
      const id = Date.now() + Math.random();
      setItems((xs) => [...xs.slice(-3), { ...t, id }]);
      setTimeout(() => dismiss(id), t.kind === "error" ? 7000 : 4000);
    },
    [dismiss],
  );
  const value = useMemo(() => ({ push }), [push]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed left-1/2 top-4 z-[2000] flex w-[min(92vw,420px)] -translate-x-1/2 flex-col gap-2" aria-live="polite">
        <AnimatePresence initial={false}>
          {items.map((t) => {
            const Icon = ICONS[t.kind];
            return (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, y: -12, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.98 }}
                transition={{ duration: 0.18 }}
                className="glass pointer-events-auto flex items-start gap-3 rounded-xl px-3.5 py-3"
                role={t.kind === "error" ? "alert" : "status"}
              >
                <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${TONE[t.kind]}`} aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-txt-primary">{t.title}</p>
                  {t.description && <p className="mt-0.5 text-xs text-txt-secondary">{t.description}</p>}
                </div>
                <button className="text-txt-muted hover:text-txt-primary" onClick={() => dismiss(t.id)} aria-label="Dismiss notification">
                  <X className="h-4 w-4" />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
