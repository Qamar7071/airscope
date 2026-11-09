# AirScope methodology

This document explains how AirScope turns a handful of monitoring stations into
(1) a city-wide PM2.5 estimate with honest uncertainty, (2) a map of monitoring
blind spots and (3) recommended coordinates for new stations. It also explains
how the offline demo is built, so that the demo can be evaluated without
pretending to be real data.

Contents

1. [The problem](#1-the-problem)
2. [Data and quality control](#2-data-and-quality-control)
3. [Features](#3-features)
4. [Model](#4-model)
5. [Validation](#5-validation)
6. [Uncertainty](#6-uncertainty)
7. [Monitoring Gap Index](#7-monitoring-gap-index)
8. [Sensor placement](#8-sensor-placement)
9. [The offline demo as an OSSE](#9-the-offline-demo-as-an-osse)
10. [Design decisions backed by experiments](#10-design-decisions-backed-by-experiments)
11. [Limitations](#11-limitations)
12. [References](#12-references)

---

## 1. The problem

Islamabad, Lahore and Karachi are large cities with few reference-grade
monitors. Most residents live kilometres from the nearest station, so the air
they breathe is not measured. Two questions follow, and AirScope is built
around both:

* What is the best estimate of PM2.5 where there is no station, and how sure can
  we be?
* Where would one more station reduce that uncertainty the most, for the most
  people?

The second question is AirScope's core contribution: **monitoring-gap discovery
and optimal sensor placement**, with the estimation model in a supporting role.

## 2. Data and quality control

| Input | Live mode | Offline demo |
|---|---|---|
| PM2.5 stations and hourly values | OpenAQ API v3 (`/locations`, `/sensors/{id}/hours`), free key required | simulated stations sampling the synthetic nature run (section 9) |
| Hourly weather | Open-Meteo (temperature, humidity, wind, pressure, boundary-layer height) | synthetic weather with diurnal cycles and stagnation episodes |
| Population density | bundled approximate surface (`datasets/population_density.csv`) | same |
| Elevation | bundled approximate terrain (`datasets/elevation.csv`) | same |
| Analysis domain | hand-digitised polygons (`datasets/city_boundaries.json`) | same |

Quality control (`data/data_processor.py`) is applied identically in both modes,
and every removal is counted in a QC report that the UI shows:

1. non-numeric or missing values are dropped;
2. duplicate readings within an hour are averaged;
3. values below 0 or above 1000 µg/m³ are removed;
4. *stuck sensors* - six or more identical consecutive hourly values - are removed;
5. isolated positive *spikes* are removed with a Hampel filter: a 7-hour rolling
   median, flagging values more than 6 × 1.4826 × MAD above it and more than
   twice the median;
6. stations with under 25 % valid hours, or outside the analysis domain, are
   shown but excluded from training.

Weather values outside physical ranges become missing; gaps of up to six hours
are interpolated in time (wind direction through its u/v components so that
350° and 10° average to 0°, not 180°). Remaining gaps are imputed later inside
the model pipeline.

The demo generator injects realistic faults (random gaps, multi-hour outages,
negative values, spikes and a stuck sensor) so the QC stage is exercised; the
test-suite checks that each injected fault type is caught.

## 3. Features

Each training observation is one station-hour; each prediction target is one
grid cell at one hour. Both are described by the same vector
(`ml/features.py`).

| Group | Features | Notes |
|---|---|---|
| Spatial | latitude, longitude, elevation, distance to the city reference point, log(1 + population density) | raw coordinates are part of every observation but *not* model inputs by default (section 10) |
| Temporal | sin/cos of local hour, sin/cos of day of year, month | cyclic encoding keeps 23:00 next to 00:00 |
| Meteorological | temperature, relative humidity, wind speed, wind u/v, surface pressure, boundary-layer height, ventilation index (= BLH × wind speed) | wind direction is encoded as components; the ventilation index is the standard dispersion proxy |
| Network context | mean and inverse-distance-weighted PM2.5 of the *other* stations in the same hour | a station never sees its own reading, which keeps training consistent with prediction at unmonitored cells |

**Validation and imputation.** `FeatureValidator` converts physically impossible
values (for example relative humidity above 100 %) into missing values; a median
imputer fitted on the training data fills them. Both live inside the
scikit-learn pipeline that is saved with the model, so training and inference
are preprocessed identically. A feature that is completely absent at training
time (for instance boundary-layer height from a weather model that lacks it) is
kept as a constant column, so the model still loads and predicts.

## 4. Model

AirScope uses a **pre-specified multi-model ensemble** trained on log(1 + PM2.5):

* random forest (150 trees, min. 5 samples per leaf, 50 % of features per split);
* histogram gradient boosting (300 iterations, learning rate 0.05);
* XGBoost (400 trees, depth 5) when the optional package is installed.

The ensemble prediction is the geometric mean of the members (the mean in log
space). Two additional histogram gradient-boosting models with quantile loss
(5th and 95th percentiles) estimate the conditional spread used in section 6.
Training is fully deterministic (fixed seeds); artifacts are saved to
`backend/models/<city>/` together with the dataset fingerprint, so a model is
retrained automatically only when its data change.

Why not choose the single best model by cross-validation? See section 10.

## 5. Validation

The primary score is **leave-one-station-out (LOSO) cross-validation**: each
station is predicted by a model trained without it, whose network features use
only the remaining stations. This answers the question AirScope exists for -
"how wrong are we where there is no station?" - and avoids the well-documented
optimism of random splits on spatial data (Roberts et al., 2017; Ploton et al.,
2020).

The ensemble is always compared with three transparent baselines computed in
the same folds: the training mean, the mean of the other stations in the same
hour, and inverse distance weighting (IDW). **The UI states plainly when a
baseline does as well as or better than the ensemble.** A random K-fold over
station-hours is also reported, only to show how much it overstates accuracy.

Permutation importance is computed on the held-out station of each fold. Each
feature is replaced by random draws from its pooled distribution across all
stations (rather than shuffled within the held-out station, which would leave
static station attributes unchanged), and the increase in RMSE is averaged over
folds. Whole feature groups are also permuted together.

Results for the bundled demo are generated into
[`docs/demo_results.md`](demo_results.md) by `make report` - computed from the
model artifacts, never typed by hand.

## 6. Uncertainty

Tree models are notoriously over-confident away from their training data: their
spread does not grow with distance to the nearest station. AirScope therefore
combines three sources of uncertainty, in log units:

```
sigma_total(x, t) = c * sqrt( sigma_q(x,t)^2 + sigma_mm(x,t)^2 + s_sp^2 * rho(x) )
```

| Term | Meaning | Estimated from |
|---|---|---|
| sigma_q | conditional spread: (log q95 − log q05) / (2 × 1.645) | quantile gradient-boosting models |
| sigma_mm | disagreement between ensemble members | standard deviation of member predictions |
| rho(x) | normalised simple-kriging variance in [0, 1]; ~0 at a station, → 1 far from all stations | station geometry and an exponential covariance |
| s_sp² | extra error variance at unmonitored locations | LOSO residuals: (mean r² − mean σ_model²) / mean ρ |
| c | conformal scale so that 90 % intervals cover 90 % of held-out errors | LOSO residuals |

The covariance range and nugget come from an exponential variogram fitted by
weighted least squares to the semivariance of LOSO residuals between station
pairs (falling back to the city's documented default range when the fit is
degenerate, which is reported).

**Honest calibration check.** Calibration is evaluated with *nested* LOSO: the
parameters used to judge station *h* are estimated without station *h*. The UI
reports both the calibrated coverage and the coverage of the tree-model spread
alone, which makes the value of the spatial term visible. In demo mode the
calibration is also checked at every grid cell against the synthetic truth.

## 7. Monitoring Gap Index

For every grid cell AirScope computes four components in [0, 1]
(`ml/gaps.py`):

| Component | Definition |
|---|---|
| D - coverage deficit | 1 − C, with C = 1 − ∏ₛ (1 − exp(−dₛ / R)) the probability that at least one station represents the cell; R is the station representativeness radius (2 km in Islamabad and Lahore, 2.5 km in Karachi, configurable) |
| U - uncertainty | calibrated sigma_total, robustly scaled to the city's 2nd–98th percentiles |
| P - pollution | estimated PM2.5, robustly scaled |
| Pop - population | log population density, robustly scaled |

They are combined in two stages, with user-adjustable weights:

```
Observation deficit  O = (w_D·D + w_U·U) / (w_D + w_U)        "how poorly observed"
Exposure need        N = (w_P·P + w_Pop·Pop) / (w_P + w_Pop)  "how much it matters"
MGI = O^α · N^(1−α)        (α = balance, default 0.5)
```

The geometric mean is deliberate: a blind spot must be *both* poorly observed
*and* important. A well-monitored dense district, or an empty hillside far from
any station, cannot score highly by excelling on one dimension. This is the same
argument that moved the UN Human Development Index from an arithmetic to a
geometric mean in 2010.

Cells are classified as critical (MGI ≥ 0.75), high (≥ 0.60), moderate (≥ 0.45)
or low. Connected critical cells (8-connectivity) form **blind-spot clusters**,
ranked by population-weighted severity and labelled with the nearest named
locality. The scaling ranges are fixed on the current network and reused for
"after" scenarios, so before/after comparisons are on the same scale.

## 8. Sensor placement

`ml/sensor_placement.py` offers four strategies.

**Need-weighted coverage (default).** Maximise

```
F(S) = Σ_c w_c · [1 − ∏_{s ∈ E ∪ S} (1 − exp(−d(c, s) / R))]
```

over sets S of k new sites, where E are existing stations and
w_c = N_c · (0.5 + 0.5·U_c) weights cells by exposure need, boosted by
uncertainty. F is monotone submodular (a weighted probabilistic-coverage
function), so the greedy algorithm achieves at least (1 − 1/e) ≈ 63 % of the
optimum for an unconstrained budget (Nemhauser, Wolsey & Fisher, 1978). With
the practical spacing constraints below the bound no longer formally applies,
but greedy remains a strong and transparent heuristic. Each greedy step is a
single matrix-vector product, so recommendations are computed in well under a
second.

**Kriging-variance reduction.** Greedily choose sites that most reduce the
need-weighted kriging prediction variance, using rank-one posterior covariance
updates - the classic geostatistical network-design criterion (cf. Krause,
Singh & Guestrin, 2008).

**Population heuristic** and **random** placement are transparent baselines.

**Constraints.** Candidate sites are grid cells inside the domain with population
density ≥ a threshold (default 200 people/km², a proxy for power, access and
security), at least 1.5 km from existing stations and 2 km from each other (all
adjustable).

**Impact.** For any set of sites - recommended or placed by the user - AirScope
recomputes coverage, the kriging variance and the gap index *a priori*: the
kriging variance depends only on where stations are, not on what they would
measure, so the expected improvement can be computed before any sensor is
installed. Reported metrics are the need-weighted coverage, the share of
residents within R of a monitor, the reduction of spatial uncertainty, and the
residents remaining in critical gaps. A greedy curve (k = 0 … 12) shows the
diminishing returns of each additional station.

## 9. The offline demo as an OSSE

AirScope must run offline, without keys, deterministically, and without
presenting fabricated numbers as observations. It therefore follows the
**Observing System Simulation Experiment (OSSE)** methodology used by
meteorological agencies to evaluate observing networks before building them
(Masutani et al., 2010).

1. A documented synthetic "nature run" defines PM2.5 everywhere in each city for
   every hour of a 30-day period (`data/demo_generator.py`,
   `datasets/synthetic_city_profiles.json`):

   ```
   PM(x,t) = R(t)·D(t)·H(t)·S(t) · [B_reg + B_city·(a_pop·P(x)·E_res(h) + Σ_k q_k·E_k(h)·K_k(x,t))]
             · elev(x) · exp(rf(x)) · marine(x,t)
   ```

   with ventilation dilution D (boundary-layer height × wind speed), humidity
   growth H, regional transport episodes R, a seasonal trend S, diurnal emission
   profiles E, wind-advected Gaussian plumes K from industrial areas, traffic
   hubs, road corridors and brick-kiln clusters, cleaner air on the Margalla
   Hills slopes and along the Karachi coast, and a smooth random field rf(x)
   representing local structure that no covariate explains.
2. Simulated stations, placed in plausible but deliberately uneven locations,
   sample the nature run with instrument-type noise, gaps and faults. AirScope's
   pipeline only ever sees these samples - exactly as it would see OpenAQ data.
3. Because the truth is known everywhere, AirScope can measure what real data
   cannot: the error of the city-wide map, whether its 90 % intervals really cover
   90 % of cells, whether the uncertainty map ranks cells by actual error, and how
   much each placement strategy *actually* reduces city-wide error. For the
   placement benchmark, virtual reference stations are added at the chosen
   sites, the ensemble is retrained, and the error is re-measured. AirScope's
   strategies are compared with the population heuristic and with five random
   placements.

**Fraternal, not identical, twin.** The model never sees the analytic population
field, the emission sources or the random field; it uses the coarse bundled CSV
surfaces instead. This avoids the over-optimism of an "identical twin"
experiment in which the model's inputs generate the truth.

**What the placement benchmark found.** The generated report
([`docs/demo_results.md`](demo_results.md)) shows three different outcomes. In Karachi, AirScope's
recommended sites reduced city-wide error far more than any random placement. In Islamabad, all
informed strategies helped, but by amounts within the large spread of random placements. In Lahore,
adding five stations did not reduce city-wide error and often increased it, for random placements as
well as AirScope's. A diagnostic run showed why. Error fell sharply near the new stations
(roughly 36 → 29 µg/m³ within 1.5 km), but rose slightly far from them, together with the overall
bias. The recommended sites are polluted hotspots, so adding them shifts the relationships the
retrained model learns (for example between population density and PM2.5) and it over-predicts cleaner
areas elsewhere. This is the classic **preferential sampling** problem of geostatistics (Diggle,
Menezes & Su, 2010). Two quick mitigations (removing static covariates; stronger regularisation) did
not fix it. Coverage and uncertainty gains are guaranteed by design because they depend only on station
geometry; turning extra stations into lower city-wide error in a hotspot-dominated city needs a
preferential-sampling-aware estimator, which is on the roadmap.

**What the OSSE does and does not show.** It shows that the methodology behaves
as designed on a realistic, physically motivated synthetic city. It does not show
that the same accuracy would be achieved in the real Islamabad, Lahore or
Karachi. Every OSSE number is labelled synthetic in the API, the UI and the
generated report.

## 10. Design decisions backed by experiments

**A fixed ensemble rather than "the best LOSO model".** With seven, mostly
central stations, LOSO has seven noisy folds that are not representative of the
whole city. During development the LOSO ranking of model families disagreed with
their ranking on the full synthetic truth (for example, pure IDW scored best at
held-out stations in Islamabad but worse than the ensemble across the city). Using
LOSO to *select* a model would therefore mostly select noise (Wadoux et al., 2021,
discuss why cross-validation is a weak guide to map accuracy with clustered
samples). AirScope pre-specifies the ensemble and uses LOSO to report skill
honestly - including when a baseline wins - and to calibrate uncertainty.

**No raw coordinates as model inputs by default.** Tree models that split on
latitude and longitude produce axis-aligned rectangular artefacts in the map,
which are physically meaningless. A reproducible ablation (`python -m
ml.ablation`, synthetic data) compared three options:

| City | Variant | LOSO RMSE | Grid RMSE (vs synthetic truth) | Spatial pattern corr. |
|---|---|---|---|---|
| islamabad | raw | 29.99 | 22.13 | 0.326 |
| islamabad | none | 27.4 | 22.19 | 0.388 |
| islamabad | ogc | 28.57 | 22.23 | 0.326 |
| lahore | raw | 44.94 | 39.47 | 0.507 |
| lahore | none | 44.51 | 39.43 | 0.463 |
| lahore | ogc | 42.45 | 40.89 | 0.39 |
| karachi | raw | 10.25 | 13.65 | 0.592 |
| karachi | none | 10.05 | 13.95 | 0.607 |
| karachi | ogc | 10.11 | 14.22 | 0.55 |

Compared with raw coordinates, dropping them removed the artefacts and lowered
held-out (LOSO) error in all three cities, while the city-wide error against the
synthetic truth changed by about 2 % or less. Oblique coordinates (Møller et al.,
2020) had the lowest held-out error in Lahore but the highest city-wide error in
every city, and replaced the rectangles with diagonal cuts. Location still enters the model through
elevation, distance to the centre, population density and the IDW network
feature; raw coordinates can be re-enabled with
`AIRSCOPE_COORDINATE_FEATURES=true`.

**Things that were tried and rejected.** Modelling the residual from IDW instead
of PM2.5 itself, ridge regression on the same features (which extrapolated
catastrophically from seven stations), and "spatial jitter" augmentation of
station attributes all generalised worse under LOSO and on the synthetic truth.

## 11. Limitations

* **Preferential sampling.** Stations placed in hotspots can bias a retrained
  model elsewhere; in the synthetic Lahore this cancelled the error reduction from
  new stations (section 9). The coverage and uncertainty gains are not affected.
* **Few stations.** Seven stations constrain spatial structure weakly. Held-out
  errors are large in the most isolated places, and the uncertainty layer says
  so. This is the problem AirScope is designed to expose, not to hide.
* **Synthetic demo.** Demo results demonstrate methodology, not real-world accuracy.
* **Approximate geography.** Population, elevation, boundaries and locality
  coordinates are documented approximations. Replace them with WorldPop or GHSL
  population, a DEM such as Copernicus GLO-90, and official boundaries for
  operational use (`docs/adding_a_city.md` describes the formats).
* **Policy parameters.** The representativeness radius, the gap-index weights and
  the siting constraints are choices, exposed as parameters, not facts.
* **City-level weather.** One weather series per city is used; intra-urban
  meteorological variation (sea breeze fronts, valley flows) is only represented
  through static features.
* **Hourly AQI.** The US EPA AQI is defined for 24-hour means; AirScope shows
  hourly categories for orientation only.
* **Low-cost sensors.** Live OpenAQ data may include low-cost sensors with
  humidity-related biases; AirScope's QC does not apply sensor-specific
  corrections.

## 12. References

* Angelopoulos, A. N. & Bates, S. (2023). Conformal prediction: a gentle introduction. *Foundations and Trends in Machine Learning*, 16(4).
* Diggle, P. J., Menezes, R. & Su, T.-L. (2010). Geostatistical inference under preferential sampling. *Journal of the Royal Statistical Society: Series C (Applied Statistics)*, 59(2), 191–232.
* Hengl, T., Nussbaum, M., Wright, M. N., Heuvelink, G. B. M. & Gräler, B. (2018). Random forest as a generic framework for predictive modeling of spatial and spatio-temporal variables. *PeerJ*, 6, e5518.
* Krause, A., Singh, A. & Guestrin, C. (2008). Near-optimal sensor placements in Gaussian processes: theory, efficient algorithms and empirical studies. *Journal of Machine Learning Research*, 9, 235–284.
* Masutani, M. et al. (2010). Observing system simulation experiments. In *Data Assimilation: Making Sense of Observations*, Springer, 647–679.
* Meinshausen, N. (2006). Quantile regression forests. *Journal of Machine Learning Research*, 7, 983–999.
* Møller, A. B., Beucher, A. M., Pouladi, N. & Greve, M. H. (2020). Oblique geographic coordinates as covariates for digital soil mapping. *SOIL*, 6, 269–289.
* Nemhauser, G. L., Wolsey, L. A. & Fisher, M. L. (1978). An analysis of approximations for maximizing submodular set functions - I. *Mathematical Programming*, 14, 265–294.
* Ploton, P. et al. (2020). Spatial validation reveals poor predictive performance of large-scale ecological mapping models. *Nature Communications*, 11, 4540.
* Roberts, D. R. et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*, 40, 913–929.
* Wadoux, A. M. J.-C., Heuvelink, G. B. M., de Bruin, S. & Brus, D. J. (2021). Spatial cross-validation is not the right way to evaluate map accuracy. *Ecological Modelling*, 457, 109692.
* US EPA (2024). Final rule: reconsideration of the National Ambient Air Quality Standards for particulate matter (revised PM2.5 AQI breakpoints).
* World Health Organization (2021). *WHO global air quality guidelines.*
