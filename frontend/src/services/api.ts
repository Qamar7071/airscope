import axios, { AxiosError } from "axios";
import type {
  CityDetail,
  CitySummary,
  GapWeights,
  GapsResponse,
  GridResponse,
  Health,
  Metrics,
  OsseResponse,
  PlacementParams,
  RecommendationsResponse,
  SimulationResponse,
  SourcesResponse,
  StationSeries,
  StationsResponse,
  Timesteps,
  WeatherSeries,
} from "../types";

const BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "").replace(/\/$/, "");

export const http = axios.create({ baseURL: `${BASE}/api`, timeout: 90_000 });

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get notReady(): boolean {
    return this.status === 503 && this.code === "model_not_ready";
  }
}

function normalize(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  const ax = err as AxiosError<{ error?: string; message?: string; status?: unknown }>;
  if (ax?.isAxiosError) {
    if (!ax.response) {
      return new ApiError(0, "network_error", "Cannot reach the AirScope backend. Is it running on port 8000?");
    }
    const body = ax.response.data ?? {};
    return new ApiError(ax.response.status, body.error ?? "http_error", body.message ?? ax.message, body.status);
  }
  return new ApiError(0, "unknown_error", err instanceof Error ? err.message : String(err));
}

async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  try {
    const res = await http.get<T>(url, { params });
    return res.data;
  } catch (e) {
    throw normalize(e);
  }
}

async function post<T>(url: string, body: unknown): Promise<T> {
  try {
    const res = await http.post<T>(url, body);
    return res.data;
  } catch (e) {
    throw normalize(e);
  }
}

export function weightParams(w: GapWeights): Record<string, number> {
  return {
    w_coverage: w.coverage,
    w_uncertainty: w.uncertainty,
    w_pollution: w.pollution,
    w_population: w.population,
    balance: w.balance,
  };
}

export const api = {
  health: () => get<Health>("/health"),
  sources: () => get<SourcesResponse>("/sources"),
  cities: () => get<{ cities: CitySummary[] }>("/cities").then((r) => r.cities),
  city: (id: string) => get<CityDetail>(`/cities/${id}`),
  timesteps: (id: string) => get<Timesteps>(`/cities/${id}/timesteps`),
  grid: (id: string, time: string) => get<GridResponse>(`/cities/${id}/grid`, { time }),
  gaps: (id: string, time: string, w: GapWeights) => get<GapsResponse>(`/cities/${id}/gaps`, { time, ...weightParams(w) }),
  recommendations: (id: string, time: string, w: GapWeights, p: PlacementParams) =>
    get<RecommendationsResponse>(`/cities/${id}/recommendations`, { time, ...weightParams(w), ...p }),
  simulate: (id: string, time: string, w: GapWeights, sites: { lat: number; lon: number }[]) =>
    post<SimulationResponse>(`/cities/${id}/simulate`, { time, weights: weightParams(w), sites }),
  osse: (id: string, sites: { lat: number; lon: number }[]) => post<OsseResponse>(`/cities/${id}/osse`, { sites }),
  stations: (id: string, time: string) => get<StationsResponse>(`/cities/${id}/stations`, { time }),
  stationSeries: (id: string, stationId: string, hours = 168) =>
    get<StationSeries>(`/cities/${id}/stations/${encodeURIComponent(stationId)}/timeseries`, { hours }),
  weather: (id: string, hours = 168) => get<WeatherSeries>(`/cities/${id}/weather`, { hours }),
  metrics: (id: string) => get<Metrics>(`/cities/${id}/metrics`),
  retrain: (id: string) => post<{ status: string }>(`/cities/${id}/train`, {}),
};
