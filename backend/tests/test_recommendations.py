"""Sensor placement: constraints, determinism and sensible choices."""
import numpy as np
import pytest

from geospatial.distance import nearest_distance_km, pairwise_haversine_km
from ml.gaps import GapWeights
from ml.sensor_placement import PlacementConstraints, recommend, select_sites, simulate


def _coords(ctx, picks):
    idx = [j for j, _ in picks]
    return ctx.lat[idx], ctx.lon[idx]


@pytest.mark.parametrize("strategy", ["coverage", "variance", "population", "random"])
def test_constraints_respected(test_context, strategy):
    ctx = test_context
    c = PlacementConstraints(k=6, strategy=strategy, min_spacing_km=2.0, min_station_distance_km=1.5, min_population_density=600)
    picks = select_sites(ctx, GapWeights(), c)
    assert 0 < len(picks) <= 6
    lat, lon = _coords(ctx, picks)
    d = pairwise_haversine_km(lat, lon, lat, lon)
    np.fill_diagonal(d, np.inf)
    assert d.min() >= 2.0 - 1e-6
    near, _ = nearest_distance_km(lat, lon, ctx.station_lat, ctx.station_lon)
    assert near.min() >= 1.5 - 1e-6
    assert ctx.population[[j for j, _ in picks]].min() >= 600


def test_first_coverage_site_targets_the_unmonitored_hot_spot(test_context):
    ctx = test_context
    picks = select_sites(ctx, GapWeights(), PlacementConstraints(k=1))
    lat, lon = _coords(ctx, picks)
    assert lat[0] > 33.65 and lon[0] > 73.06


def test_placement_is_deterministic(test_context):
    c = PlacementConstraints(k=4, strategy="coverage")
    assert select_sites(test_context, GapWeights(), c) == select_sites(test_context, GapWeights(), c)
    r = PlacementConstraints(k=4, strategy="random", seed=7)
    assert select_sites(test_context, GapWeights(), r) == select_sites(test_context, GapWeights(), r)


def test_greedy_marginal_gains_are_non_increasing(test_context):
    # coverage objective is submodular -> greedy gains never increase
    picks = select_sites(test_context, GapWeights(), PlacementConstraints(k=8, min_spacing_km=0.0))
    gains = [g for _, g in picks]
    assert all(b <= a + 1e-12 for a, b in zip(gains, gains[1:]))


def test_recommend_reports_improvement_and_curve(test_context):
    res = recommend(test_context, GapWeights(), PlacementConstraints(k=3))
    assert len(res["sites"]) == 3
    before, after = res["impact"]["before"], res["impact"]["after"]
    assert after["need_weighted_coverage_pct"] > before["need_weighted_coverage_pct"]
    assert after["mean_sigma_log"] < before["mean_sigma_log"]
    assert res["impact"]["delta"]["uncertainty_reduction_pct"] > 0
    curve = [p["need_weighted_coverage_pct"] for p in res["curve"]]
    assert curve[0] == before["need_weighted_coverage_pct"]
    assert all(b >= a - 1e-9 for a, b in zip(curve, curve[1:]))
    site = res["sites"][0]
    assert site["rank"] == 1 and site["reasons"] and site["location"]["label"]


def test_variance_strategy_reduces_kriging_variance(test_context):
    ctx = test_context
    picks = select_sites(ctx, GapWeights(), PlacementConstraints(k=3, strategy="variance"))
    lat, lon = _coords(ctx, picks)
    assert ctx.rho(lat, lon).mean() < ctx.rho().mean()


def test_impossible_constraints_return_message(test_context):
    res = recommend(test_context, GapWeights(), PlacementConstraints(k=5, min_population_density=1e9))
    assert res["sites"] == [] and res["message"]


@pytest.mark.parametrize("kwargs", [dict(k=0), dict(k=99), dict(strategy="magic"), dict(min_spacing_km=-1)])
def test_invalid_constraints_rejected(kwargs):
    with pytest.raises(ValueError):
        PlacementConstraints(**kwargs).validated()


def test_simulate_custom_sites(test_context):
    res = simulate(test_context, GapWeights(), [(33.675, 73.085)])
    assert res["impact"]["after"]["population_within_radius_pct"] > res["impact"]["before"]["population_within_radius_pct"]
    assert res["sites"][0]["lat"] == pytest.approx(33.675)
    with pytest.raises(ValueError):
        simulate(test_context, GapWeights(), [(10.0, 10.0)])
