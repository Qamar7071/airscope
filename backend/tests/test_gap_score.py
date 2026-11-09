"""Monitoring Gap Index: properties that must hold for any weights and inputs."""
import numpy as np
import pytest

from ml.gaps import (
    GAP_CLASSES,
    GapWeights,
    analyze_gaps,
    blind_spots,
    classify,
    compute_components,
    coverage_probability,
    gap_index,
    network_metrics,
    scale,
)


def comps(d, u, p, pop):
    return {k: np.asarray(v, dtype=float) for k, v in
            {"coverage_deficit": d, "uncertainty": u, "pollution": p, "population": pop}.items()}


def test_gap_index_bounded_between_zero_and_one():
    rng = np.random.default_rng(0)
    c = comps(*(rng.random(500) for _ in range(4)))
    for w in [GapWeights(), GapWeights(1, 0, 0, 1, 0.3), GapWeights(0.2, 0.8, 0.9, 0.1, 0.9)]:
        mgi, obs, need = gap_index(c, w)
        assert np.all((mgi >= 0) & (mgi <= 1))
        assert np.all((obs >= 0) & (obs <= 1)) and np.all((need >= 0) & (need <= 1))


def test_well_monitored_or_empty_cells_are_not_blind_spots():
    # well monitored dense polluted cell / unmonitored empty clean cell / unmonitored dense polluted cell
    c = comps([0.0, 1.0, 1.0], [0.0, 1.0, 1.0], [1.0, 0.0, 1.0], [1.0, 0.0, 1.0])
    mgi, _, _ = gap_index(c, GapWeights())
    assert mgi[0] == pytest.approx(0.0)
    assert mgi[1] == pytest.approx(0.0)
    assert mgi[2] == pytest.approx(1.0)


@pytest.mark.parametrize("component", ["coverage_deficit", "uncertainty", "pollution", "population"])
def test_gap_index_monotonic_in_each_component(component):
    base = comps([0.5] * 11, [0.5] * 11, [0.5] * 11, [0.5] * 11)
    base[component] = np.linspace(0, 1, 11)
    mgi, _, _ = gap_index(base, GapWeights())
    assert np.all(np.diff(mgi) >= -1e-12)
    assert mgi[-1] > mgi[0]


def test_balance_extremes_select_one_stage():
    c = comps([0.9], [0.7], [0.2], [0.4])
    only_obs, obs, need = gap_index(c, GapWeights(balance=1.0))
    assert only_obs[0] == pytest.approx(obs[0]) == pytest.approx(0.8)
    only_need, _, _ = gap_index(c, GapWeights(balance=0.0))
    assert only_need[0] == pytest.approx(need[0]) == pytest.approx(0.3)


def test_zero_group_weight_falls_back_to_other_stage():
    c = comps([0.9], [0.7], [0.2], [0.4])
    mgi, obs, _ = gap_index(c, GapWeights(pollution=0, population=0))
    assert mgi[0] == pytest.approx(obs[0])


@pytest.mark.parametrize("kwargs", [dict(coverage=-1), dict(balance=1.5), dict(coverage=0, uncertainty=0, pollution=0, population=0),
                                    dict(population=float("nan"))])
def test_invalid_weights_rejected(kwargs):
    with pytest.raises(ValueError):
        GapWeights(**kwargs).validated()


def test_classify_uses_documented_thresholds():
    thr = dict(GAP_CLASSES)
    labels = classify(np.array([thr["critical"], thr["high"], thr["moderate"], 0.0, 0.999]))
    assert list(labels) == ["critical", "high", "moderate", "low", "critical"]


def test_coverage_probability_behaviour():
    lat = np.array([33.6, 33.6, 33.6])
    lon = np.array([73.0, 73.02, 73.1])
    one = coverage_probability(lat, lon, [33.6], [73.0], radius_km=2.0)
    assert one[0] == pytest.approx(1.0)
    assert one[0] > one[1] > one[2] > 0
    two = coverage_probability(lat, lon, [33.6, 33.6], [73.0, 73.1], radius_km=2.0)
    assert np.all(two >= one - 1e-12)
    assert np.all(coverage_probability(lat, lon, [], [], 2.0) == 0)


def test_scale_clips_to_unit_interval():
    out = scale([-5, 0, 5, 10, 50], (0, 10))
    assert list(out) == [0.0, 0.0, 0.5, 1.0, 1.0]


def test_hot_spot_is_detected_as_blind_spot(test_context):
    res = analyze_gaps(test_context, GapWeights())
    mgi = res["gap_index"]
    ctx = test_context
    # the highest-gap cell should be far from the south-west stations, near the north-east hot spot
    j = int(np.argmax(mgi))
    assert ctx.lat[j] > 33.65 and ctx.lon[j] > 73.06
    clusters = blind_spots(ctx, mgi, threshold=np.percentile(mgi, 90))
    assert clusters and clusters[0]["centroid"]["lat"] > 33.65
    assert clusters[0]["id"] == "A"
    # cells right next to stations are low priority
    near = ctx.nearest_station_km() < 0.5
    assert mgi[near].max() < np.percentile(mgi, 50)


def test_after_scaling_is_fixed_to_baseline(test_context):
    ctx = test_context
    before = compute_components(ctx)
    after = compute_components(ctx, [33.675], [73.085], ctx.baseline_scaling())
    # adding a station never increases coverage deficit or uncertainty anywhere
    assert np.all(after["coverage_deficit"] <= before["coverage_deficit"] + 1e-12)
    assert np.all(after["uncertainty"] <= before["uncertainty"] + 1e-9)
    m0 = network_metrics(ctx, GapWeights())
    m1 = network_metrics(ctx, GapWeights(), [33.675], [73.085])
    assert m1["population_within_radius_pct"] > m0["population_within_radius_pct"]
    assert m1["mean_gap_index"] < m0["mean_gap_index"]
