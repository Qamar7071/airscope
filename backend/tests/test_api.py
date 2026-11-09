"""HTTP API contract tests (offline demo mode, fast-trained model)."""
from conftest import TEST_CITY


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok" and body["data_mode"] == "demo"
    assert body["live_enabled"] is False


def test_sources_and_config(client):
    sources = client.get("/api/sources").get_json()
    ids = {s["id"] for s in sources["sources"]}
    assert {"openaq", "open-meteo", "carto", "airscope-synthetic"} <= ids
    cfg = client.get("/api/config").get_json()
    assert {s["id"] for s in cfg["strategies"]} == {"coverage", "variance", "population", "random"}


def test_cities_list_labels_demo_data_as_synthetic(client):
    cities = client.get("/api/cities").get_json()["cities"]
    assert [c["id"] for c in cities][0] == "islamabad"  # primary city first
    for c in cities:
        assert c["synthetic"] is True and c["data_mode"] == "demo"
        assert c["boundary"]["type"] == "Polygon"


def test_city_detail_and_unknown_city(client):
    r = client.get(f"/api/cities/{TEST_CITY}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["provenance"]["synthetic"] is True
    assert body["dataset"]["qc"]["observations"]["out_of_range"] > 0  # injected faults were caught
    assert client.get("/api/cities/atlantis").status_code == 404
    assert client.get("/api/cities/atlantis/grid").status_code == 404


def test_grid_payload_shapes(client):
    body = client.get(f"/api/cities/{TEST_CITY}/grid?time=period").get_json()
    geom = body["geometry"]
    n = geom["nrows"] * geom["ncols"]
    for layer in ("pm25", "lower", "upper", "uncertainty", "coverage", "population"):
        assert len(body["layers"][layer]) == n
    inside = [i for i, m in enumerate(geom["mask"]) if m]
    pm = body["layers"]["pm25"]
    assert all(pm[i] is not None and pm[i] >= 0 for i in inside)
    assert all(pm[i] is None for i in range(n) if not geom["mask"][i])
    lo, hi = body["layers"]["lower"], body["layers"]["upper"]
    assert all(lo[i] <= pm[i] <= hi[i] for i in inside)
    assert body["stats"]["pm25"]["min"] <= body["stats"]["pm25"]["mean"] <= body["stats"]["pm25"]["max"]
    assert body["provenance"]["synthetic"] is True


def test_snapshot_time_selection(client):
    steps = client.get(f"/api/cities/{TEST_CITY}/timesteps").get_json()
    assert steps["latest"] == steps["timestamps"][-1]
    t = steps["timestamps"][100]
    r = client.get(f"/api/cities/{TEST_CITY}/grid", query_string={"time": t})
    assert r.status_code == 200 and r.get_json()["mode"] == "snapshot"
    assert client.get(f"/api/cities/{TEST_CITY}/grid?time=latest").status_code == 200
    assert client.get(f"/api/cities/{TEST_CITY}/grid?time=1990-01-01T00:00:00Z").status_code == 400
    assert client.get(f"/api/cities/{TEST_CITY}/grid?time=not-a-time").status_code == 400


def test_gaps_and_weights(client):
    body = client.get(f"/api/cities/{TEST_CITY}/gaps").get_json()
    vals = [v for v in body["gap_index"] if v is not None]
    assert vals and min(vals) >= 0 and max(vals) <= 1
    assert set(body["summary"]["by_class"]) == {"critical", "high", "moderate", "low"}
    shifted = client.get(f"/api/cities/{TEST_CITY}/gaps?balance=1&w_uncertainty=0").get_json()
    assert shifted["weights"]["balance"] == 1.0
    assert client.get(f"/api/cities/{TEST_CITY}/gaps?w_coverage=-1").status_code == 400
    assert client.get(f"/api/cities/{TEST_CITY}/gaps?balance=abc").status_code == 400


def test_recommendations(client):
    r = client.get(f"/api/cities/{TEST_CITY}/recommendations?k=3&strategy=coverage")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["sites"]) == 3
    assert body["impact"]["after"]["need_weighted_coverage_pct"] >= body["impact"]["before"]["need_weighted_coverage_pct"]
    assert body["curve"][0]["k"] == 0
    assert client.get(f"/api/cities/{TEST_CITY}/recommendations?strategy=magic").status_code == 400
    assert client.get(f"/api/cities/{TEST_CITY}/recommendations?k=0").status_code == 400


def test_simulate_validation_and_result(client):
    rec = client.get(f"/api/cities/{TEST_CITY}/recommendations?k=1").get_json()
    site = rec["sites"][0]
    r = client.post(f"/api/cities/{TEST_CITY}/simulate", json={"sites": [{"lat": site["lat"], "lon": site["lon"]}]})
    assert r.status_code == 200
    assert r.get_json()["impact"]["delta"]["stations"] == 1
    assert client.post(f"/api/cities/{TEST_CITY}/simulate", json={"sites": [{"lat": 0, "lon": 0}]}).status_code == 400
    assert client.post(f"/api/cities/{TEST_CITY}/simulate", json={"sites": "nope"}).status_code == 400
    assert client.post(f"/api/cities/{TEST_CITY}/simulate", data="not json", content_type="application/json").status_code == 400


def test_stations_timeseries_and_weather(client):
    st = client.get(f"/api/cities/{TEST_CITY}/stations").get_json()["stations"]
    assert st and all(s["synthetic"] for s in st)
    sid = st[0]["id"]
    ts = client.get(f"/api/cities/{TEST_CITY}/stations/{sid}/timeseries?hours=24").get_json()
    assert len(ts["timestamps"]) == len(ts["observed"]) == len(ts["predicted"]) == 24
    assert client.get(f"/api/cities/{TEST_CITY}/stations/NOPE/timeseries").status_code == 404
    w = client.get(f"/api/cities/{TEST_CITY}/weather?hours=24").get_json()
    assert len(w["temperature_c"]) == 24


def test_metrics_are_computed_and_labelled(client):
    m = client.get(f"/api/cities/{TEST_CITY}/metrics").get_json()
    assert "SYNTHETIC" in m["honesty_note"]
    models = {row["model"]: row for row in m["loso"]["models"]}
    assert "AirScope ensemble" in models and "Baseline: inverse distance weighting" in models
    assert models["AirScope ensemble"]["rmse"] > 0
    cov = m["calibration"]["empirical_coverage"]
    assert all(0 <= c <= 1 for c in cov)


def test_model_not_ready_returns_503(app):
    """A city whose model is not trained yet answers 503 with its training status."""
    from services.analysis_service import get_analysis_service

    svc = get_analysis_service()
    other = "lahore" if TEST_CITY != "lahore" else "islamabad"
    svc.registry._models.pop(other, None)  # make sure nothing is cached
    client = app.test_client()
    r = client.get(f"/api/cities/{other}/grid")  # tests use a temporary, otherwise empty models dir
    assert r.status_code == 503
    assert r.get_json()["error"] == "model_not_ready"
