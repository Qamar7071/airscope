import type { ModelStatus } from "../types";
import { useHealth } from "./useAirScopeData";

/** Model readiness for a city. "no_data" still allows coverage-only analysis. */
export function useCityStatus(cityId: string | null): { status?: ModelStatus; ready: boolean; demo: boolean } {
  const health = useHealth();
  const status = cityId ? health.data?.models[cityId] : undefined;
  return {
    status,
    ready: status?.state === "ready" || status?.state === "no_data",
    demo: health.data?.data_mode !== "live",
  };
}
