// Types mirroring the AirScope REST API (see docs/api.md).

export type NumArr = (number | null)[];
export type LayerId = "pm25" | "uncertainty" | "gaps" | "population" | "coverage" | "osse_error" | "none";
export type StepId = "pollution" | "coverage" | "uncertainty" | "gaps" | "placement" | "evidence";
export type Strategy = "coverage" | "variance" | "population" | "random";
export type ChartTab = "station" | "validation" | "uncertainty" | "drivers" | "curve" | "osse" | "weather";
export type ModelState = "ready" | "training" | "pending" | "error" | "no_data";

export interface Provenance {
  mode: "demo" | "live";
  synthetic: boolean;
  label: string;
  sources?: string[];
  description?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  fetched_at?: string | null;
  stale?: boolean;
  stale_reason?: string | null;
  fallback?: { requested_mode: string; reason: string } | null;
  licenses?: string[];
}

export interface ModelStatus {
  state: ModelState;
  progress: number;
  message: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  trained_at?: string | null;
}

export interface Health {
  status: string;
  version: string;
  data_mode: "demo" | "live";
  configured_mode: string;
  live_enabled: boolean;
  openaq_key_configured: boolean;
  models: Record<string, ModelStatus>;
}

export interface PolygonGeometry {
  type: "Polygon";
  coordinates: number[][][];
}

export interface CitySummary {
  id: string;
  name: string;
  country: string;
  timezone: string;
  center: { lat: number; lon: number; label: string };
  bbox: { west: number; south: number; east: number; north: number };
  grid_cell_km: number;
  coverage_radius_km: number;
  domain_note: string;
  is_primary: boolean;
  boundary: PolygonGeometry;
  n_stations: number;
  n_usable_stations: number;
  data_mode: "demo" | "live";
  data_label: string;
  synthetic: boolean;
  model_status: ModelStatus;
}

export interface Locality {
  name: string;
  lat: number;
  lon: number;
}

export interface QcReport {
  observations: Record<string, number>;
  weather: { unavailable: string[]; remaining_missing: Record<string, number>; interpolated: Record<string, number> };
  stations: { station_id: string; completeness: number; usable: boolean; flags: string[] }[];
  period: { start: string | null; end: string | null; hours: number };
  rules: Record<string, number | number[]>;
}

export interface CityDetail extends Omit<CitySummary, "n_stations" | "n_usable_stations" | "data_mode" | "data_label" | "synthetic"> {
  domain_area_km2: number;
  grid: { cells: number; cell_km: number; nrows: number; ncols: number };
  dataset: { n_stations: number; n_usable_stations: number; n_observations: number; period: QcReport["period"]; qc: QcReport };
  provenance: Provenance;
  localities: Locality[];
  model: null | {
    trained_at: string;
    members: Record<string, string>;
    n_stations: number;
    evaluation_available: boolean;
    uncertainty: UncertaintyModel;
  };
}

export interface UncertaintyModel {
  scale: number;
  spatial_var: number;
  range_km: number;
  nugget_ratio: number;
  calibrated: boolean;
  method: string;
}

export interface GridGeometry {
  north: number;
  south: number;
  east: number;
  west: number;
  nrows: number;
  ncols: number;
  dlat: number;
  dlon: number;
  cell_km: number;
  cell_area_km2: number;
  n_inside: number;
  mask: number[];
}

export interface AqiRow {
  category: string;
  color: string;
  cells: number;
  area_km2: number;
  population: number;
  population_pct: number;
}

export interface GridResponse {
  city: string;
  mode: "snapshot" | "period" | "coverage-only";
  timestamp: string | null;
  hours: number | null;
  n_stations_used: number | null;
  pm25_available: boolean;
  geometry: GridGeometry;
  layers: {
    pm25?: NumArr;
    lower?: NumArr;
    upper?: NumArr;
    uncertainty?: NumArr;
    relative_uncertainty?: NumArr;
    uncertainty_score?: NumArr;
    kriging_variance?: NumArr;
    osse_error?: NumArr;
    coverage: NumArr;
    population: NumArr;
    nearest_station_km: NumArr;
  };
  stats: {
    population_total: number;
    pm25?: { min: number; max: number; mean: number; population_weighted_mean: number; p10: number; p50: number; p90: number };
    aqi_distribution?: AqiRow[];
    population_above_who_24h?: number;
    population_unhealthy?: number;
    uncertainty?: { mean_halfwidth: number; mean_relative_pct: number; max_relative_pct: number };
  };
  uncertainty_model: UncertaintyModel;
  coverage_radius_km: number;
  provenance: Provenance;
}

export interface GapWeights {
  coverage: number;
  uncertainty: number;
  pollution: number;
  population: number;
  balance: number;
}

export interface Cluster {
  id: string;
  n_cells: number;
  area_km2: number;
  centroid: { lat: number; lon: number };
  peak: { lat: number; lon: number };
  peak_gap_index: number;
  mean_gap_index: number;
  mean_pm25: number | null;
  population: number;
  distance_to_nearest_station_km: number;
  location: { name: string | null; distance_km: number | null; label: string };
  cells: number[];
}

export interface ClassSummary {
  threshold: number;
  cells: number;
  area_km2: number;
  population: number;
  population_pct: number;
}

export interface NetworkMetrics {
  stations: number;
  population_within_radius_pct: number;
  area_within_radius_pct: number;
  need_weighted_coverage_pct: number;
  mean_sigma_log: number;
  typical_relative_halfwidth_pct: number;
  mean_gap_index: number;
  population_weighted_gap_index: number;
  critical_cells: number;
  critical_area_km2: number;
  population_in_critical_gaps: number;
  population_in_high_or_critical_gaps: number;
  median_distance_to_station_km: number;
  max_distance_to_station_km: number;
}

export interface GapsResponse {
  city: string;
  mode: string;
  timestamp: string | null;
  weights: GapWeights;
  classes: { name: string; threshold: number }[];
  class_codes: Record<string, number>;
  geometry: { nrows: number; ncols: number };
  gap_index: NumArr;
  labels: NumArr;
  observation_deficit: NumArr;
  exposure_need: NumArr;
  components: { coverage_deficit: NumArr; uncertainty: NumArr; pollution: NumArr; population: NumArr };
  summary: { by_class: Record<string, ClassSummary>; network: NetworkMetrics };
  clusters: Cluster[];
  pm25_available: boolean;
  provenance: Provenance;
}

export interface PlacementParams {
  k: number;
  strategy: Strategy;
  min_spacing_km: number;
  min_station_distance_km: number;
  min_population_density: number;
}

export interface Site {
  rank: number;
  lat: number;
  lon: number;
  cell_index: number;
  location: { name: string | null; distance_km: number | null; label: string };
  pm25: number | null;
  aqi_category: string | null;
  uncertainty_score: number;
  gap_index: number;
  population_density: number;
  nearest_station_km: number | null;
  objective_gain: number | null;
  newly_covered_population: number;
  reasons: string[];
}

export interface CurvePoint {
  k: number;
  need_weighted_coverage_pct: number;
  population_within_radius_pct: number;
  uncertainty_reduction_pct: number;
  population_in_critical_gaps: number;
  mean_gap_index: number;
}

export interface Impact {
  before: NetworkMetrics;
  after: NetworkMetrics;
  delta: Partial<Record<keyof NetworkMetrics | "uncertainty_reduction_pct", number>>;
}

export interface RecommendationsResponse {
  strategy: Strategy;
  strategy_label: string;
  constraints: PlacementParams & { seed: number; curve_max_k: number };
  weights: GapWeights;
  eligible_cells: number;
  sites: Site[];
  impact: Impact;
  curve: CurvePoint[];
  message: string | null;
  city: string;
  mode: string;
  timestamp: string | null;
  pm25_available: boolean;
  provenance: Provenance;
}

export interface SimulationResponse {
  sites: Site[];
  impact: Impact;
  curve: CurvePoint[];
  city: string;
  mode: string;
  timestamp: string | null;
  provenance: Provenance;
}

export interface OsseResponse {
  city: string;
  synthetic: boolean;
  sites: { lat: number; lon: number }[];
  baseline: { rmse: number; population_weighted_rmse: number };
  with_sites: { rmse: number; population_weighted_rmse: number };
  improvement_pct: number;
  pop_improvement_pct: number;
  eval_hours: number;
  note: string;
}

export interface PerStationLoso {
  station_id: string;
  name: string;
  kind: string | null;
  n: number;
  rmse: number;
  mae: number;
  bias: number;
  rmse_idw: number;
  rmse_network_mean: number;
  nearest_other_station_km: number;
  kriging_variance: number;
  mean_observed: number;
}

export interface Station {
  id: string;
  name: string;
  lat: number;
  lon: number;
  kind: string | null;
  provider: string | null;
  license: string | null;
  synthetic: boolean;
  usable: boolean;
  qc_flags: string[];
  completeness: number;
  latest_pm25: number | null;
  latest_timestamp: string | null;
  value_at_time: number | null;
  mean_pm25: number | null;
  aqi: number | null;
  aqi_category: string | null;
  nearest_other_station_km: number | null;
  loso: PerStationLoso | null;
}

export interface StationsResponse {
  city: string;
  time: string;
  stations: Station[];
  provenance: Provenance;
}

export interface StationSeries {
  city: string;
  station_id: string;
  timestamps: string[];
  observed: NumArr;
  predicted: NumArr;
  lower: NumArr;
  upper: NumArr;
  loso: PerStationLoso | null;
  note: string;
}

export interface Timesteps {
  city: string;
  timezone: string;
  timestamps: string[];
  stations_reporting: number[];
  latest: string | null;
  period: { start: string | null; end: string | null; hours: number } | null;
}

export interface WeatherSeries {
  city: string;
  timestamps: string[];
  temperature_c: NumArr;
  relative_humidity_pct: NumArr;
  wind_speed_ms: NumArr;
  wind_direction_deg: NumArr;
  boundary_layer_height_m: NumArr;
  ventilation_index: NumArr;
  network_mean_pm25: NumArr;
  provenance: Provenance;
}

export interface MetricRow {
  model: string;
  n: number;
  rmse: number;
  mae: number;
  bias: number;
  r2: number | null;
  nrmse: number | null;
  station_rmse_mean: number | null;
  station_rmse_max: number | null;
}

export interface RegMetrics {
  n: number;
  rmse: number | null;
  mae: number | null;
  bias: number | null;
  r2: number | null;
  nrmse: number | null;
}

export interface OsseScenario {
  key: string;
  label: string;
  rmse: number;
  population_weighted_rmse: number;
  improvement_pct: number;
  pop_improvement_pct: number;
  improvement_std?: number;
  pop_improvement_std?: number;
  beats_random_draws?: number;
  random_draws?: number;
  sites?: { lat: number; lon: number }[];
}

export interface Metrics {
  city_id: string;
  generated_at?: string;
  provenance?: Partial<Provenance>;
  honesty_note?: string;
  message?: string;
  data?: { n_stations: number; n_observations: number; period_start: string | null; period_end: string | null; qc: Record<string, number> };
  evaluation_available: boolean;
  loso?: {
    scheme: string;
    models: MetricRow[];
    per_station: PerStationLoso[];
    skill_vs_idw: number | null;
    skill_vs_network_mean: number | null;
    best_baseline: string;
    ensemble_beats_best_baseline: boolean;
  } | null;
  random_kfold?: { model: string; random_kfold: RegMetrics; loso: RegMetrics; optimism_pct: number | null; note: string } | null;
  calibration?: {
    method: string;
    levels: number[];
    empirical_coverage: (number | null)[];
    model_only_coverage_90: number | null;
    scale: number;
    spatial_variance: number;
    note: string;
  } | null;
  variogram?: {
    nugget: number;
    psill: number;
    range_km: number;
    method: string;
    nugget_ratio: number;
    pairs: { a: string; b: string; distance_km: number; semivariance: number; n: number }[];
    curve: { distance_km: number; semivariance: number }[];
  } | null;
  feature_importance?: {
    method: string;
    features: { name: string; rmse_increase: number; relative_pct: number; fold_std: number; description?: string; group?: string }[];
    groups: { name: string; rmse_increase: number; relative_pct: number; fold_std: number }[];
  } | null;
  osse?: {
    description: string;
    synthetic: boolean;
    eval_hours: number;
    cells: number;
    reconstruction: {
      metrics: RegMetrics;
      population_weighted: RegMetrics;
      idw_baseline: RegMetrics;
      interval_coverage_90: number | null;
      coverage_by_distance: { band: string; cells: number; rmse: number; interval_coverage_90: number; mean_sigma_log: number }[];
      uncertainty_error_spearman: number | null;
      spatial_pattern_correlation: number;
    };
    placement_benchmark: { k: number; scenarios: OsseScenario[] };
  } | null;
  training?: { profile: string; seconds: number; members: string[]; xgboost_available: boolean; target_transform: string };
  model?: { trained_at: string; members: Record<string, string>; features: string[]; network_features: boolean };
}

export interface Source {
  id: string;
  name: string;
  url: string | null;
  used_for: string;
  access: string;
  license: string;
  attribution: string;
  used_in_demo: boolean;
}

export interface SourcesResponse {
  sources: Source[];
  standards: { id: string; name: string; note: string }[];
}

export interface SimSite {
  id: string;
  lat: number;
  lon: number;
}
