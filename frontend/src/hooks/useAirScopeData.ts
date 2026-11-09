import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, api } from "../services/api";
import type { GapWeights, Health, PlacementParams, SimSite } from "../types";

// While a city's model is still training the API answers 503: keep retrying quietly.
const retry = (failureCount: number, error: unknown) =>
  error instanceof ApiError && error.notReady ? true : error instanceof ApiError && error.status === 400 ? false : failureCount < 2;
const retryDelay = (attempt: number, error: unknown) =>
  error instanceof ApiError && error.notReady ? 3000 : Math.min(1000 * 2 ** attempt, 8000);

const common = { retry, retryDelay, staleTime: 5 * 60_000, refetchOnWindowFocus: false } as const;

export function useDebouncedValue<T>(value: T, delay = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return v;
}

const anyTraining = (h?: Health) => !!h && Object.values(h.models).some((m) => m.state === "training" || m.state === "pending");

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: (q) => (anyTraining(q.state.data) ? 2000 : 20_000),
    retry: true,
    retryDelay: 3000,
  });
}

export const useSources = () => useQuery({ queryKey: ["sources"], queryFn: api.sources, ...common, staleTime: Infinity });
export const useCities = () => useQuery({ queryKey: ["cities"], queryFn: api.cities, ...common, retry: true, retryDelay: 3000 });

export const useCity = (id: string | null) =>
  useQuery({ queryKey: ["city", id], queryFn: () => api.city(id!), enabled: !!id, ...common });

export const useTimesteps = (id: string | null, ready: boolean) =>
  useQuery({ queryKey: ["timesteps", id], queryFn: () => api.timesteps(id!), enabled: !!id && ready, ...common });

export const useGrid = (id: string | null, time: string | null, ready: boolean) =>
  useQuery({
    queryKey: ["grid", id, time],
    queryFn: () => api.grid(id!, time!),
    enabled: !!id && !!time && ready,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === id ? prev : undefined),
    ...common,
  });

export const useGaps = (id: string | null, weights: GapWeights, ready: boolean) => {
  const w = useDebouncedValue(weights);
  return useQuery({
    queryKey: ["gaps", id, w],
    queryFn: () => api.gaps(id!, "period", w),
    enabled: !!id && ready,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === id ? prev : undefined),
    ...common,
  });
};

export const useRecommendations = (id: string | null, weights: GapWeights, placement: PlacementParams, ready: boolean) => {
  const w = useDebouncedValue(weights);
  const p = useDebouncedValue(placement);
  return useQuery({
    queryKey: ["recommendations", id, w, p],
    queryFn: () => api.recommendations(id!, "period", w, p),
    enabled: !!id && ready,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === id ? prev : undefined),
    ...common,
  });
};

export const useSimulation = (id: string | null, weights: GapWeights, sites: SimSite[], ready: boolean) => {
  const w = useDebouncedValue(weights);
  const s = useDebouncedValue(sites.map(({ lat, lon }) => ({ lat: +lat.toFixed(5), lon: +lon.toFixed(5) })), 250);
  return useQuery({
    queryKey: ["simulate", id, w, s],
    queryFn: () => api.simulate(id!, "period", w, s),
    enabled: !!id && ready && s.length > 0,
    placeholderData: keepPreviousData,
    ...common,
  });
};

export const useStations = (id: string | null, time: string | null) =>
  useQuery({
    queryKey: ["stations", id, time],
    queryFn: () => api.stations(id!, time && time !== "period" ? time : "latest"),
    enabled: !!id,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === id ? prev : undefined),
    ...common,
  });

export const useStationSeries = (id: string | null, stationId: string | null) =>
  useQuery({
    queryKey: ["series", id, stationId],
    queryFn: () => api.stationSeries(id!, stationId!, 168),
    enabled: !!id && !!stationId,
    ...common,
  });

export const useWeather = (id: string | null) =>
  useQuery({ queryKey: ["weather", id], queryFn: () => api.weather(id!, 168), enabled: !!id, ...common });

export const useMetrics = (id: string | null, ready: boolean) =>
  useQuery({ queryKey: ["metrics", id], queryFn: () => api.metrics(id!), enabled: !!id && ready, ...common });

export const useOsse = (id: string | null) =>
  useMutation({ mutationFn: (sites: { lat: number; lon: number }[]) => api.osse(id!, sites) });
