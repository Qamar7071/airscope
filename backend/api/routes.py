"""HTTP API (Flask blueprint mounted at /api). See docs/api.md for examples."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from config import APP_VERSION, get_city, get_settings
from data.sources import DATA_SOURCES, STANDARDS
from ml.gaps import GAP_CLASSES
from ml.sensor_placement import STRATEGIES
from services.analysis_service import get_analysis_service
from services.model_registry import get_registry
from .schemas import NotReadyError, ValidationError, parse_constraints, parse_sites, parse_time, parse_weights

logger = logging.getLogger(__name__)
api = Blueprint("api", __name__, url_prefix="/api")


def _city(city_id: str) -> str:
    try:
        return get_city(city_id).id
    except KeyError:
        raise LookupError(f"Unknown city '{city_id}'")


def _body() -> dict:
    body = request.get_json(silent=True)
    if body is None:
        raise ValidationError("Request body must be valid JSON")
    return body


# ----------------------------------------------------------------------- errors


@api.errorhandler(ValidationError)
def _validation(exc):
    return jsonify({"error": "invalid_request", "message": str(exc)}), 400


@api.errorhandler(LookupError)
def _lookup(exc):
    msg = exc.args[0] if exc.args else "Not found"
    return jsonify({"error": "not_found", "message": str(msg)}), 404


@api.errorhandler(NotReadyError)
def _not_ready(exc: NotReadyError):
    resp = jsonify({"error": "model_not_ready", "message": str(exc), "status": exc.status})
    resp.headers["Retry-After"] = "3"
    return resp, 503


# ----------------------------------------------------------------------- meta


@api.get("/health")
def health():
    settings = get_settings()
    svc = get_analysis_service()
    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "data_mode": svc.datasets.requested_mode(),
        "configured_mode": settings.data_mode,
        "live_enabled": settings.live_enabled,
        "openaq_key_configured": bool(settings.openaq_api_key),
        "models": get_registry().statuses(),
    })


@api.get("/sources")
def sources():
    return jsonify({"sources": DATA_SOURCES, "standards": STANDARDS})


@api.get("/config")
def ui_config():
    """Static options the UI needs (strategies, gap classes, defaults)."""
    return jsonify({
        "strategies": [{"id": k, "label": v} for k, v in STRATEGIES.items()],
        "gap_classes": [{"name": n, "threshold": t} for n, t in GAP_CLASSES],
        "defaults": {
            "weights": {"coverage": 0.5, "uncertainty": 0.5, "pollution": 0.5, "population": 0.5, "balance": 0.5},
            "placement": {"k": 5, "strategy": "coverage", "min_spacing_km": 2.0, "min_station_distance_km": 1.5,
                          "min_population_density": 200},
        },
    })


@api.get("/cities")
def cities():
    return jsonify({"cities": get_analysis_service().cities_payload()})


@api.get("/cities/<city_id>")
def city(city_id):
    return jsonify(get_analysis_service().city_payload(_city(city_id)))


@api.get("/cities/<city_id>/status")
def city_status(city_id):
    return jsonify(get_registry().status(_city(city_id)).to_dict())


@api.post("/cities/<city_id>/train")
def retrain(city_id):
    cid = _city(city_id)
    get_registry().request_retrain(cid)
    return jsonify({"status": "queued", "city": cid}), 202


# ----------------------------------------------------------------------- data


@api.get("/cities/<city_id>/stations")
def stations(city_id):
    time_param = parse_time({"time": request.args.get("time", "latest")})
    return jsonify(get_analysis_service().stations_payload(_city(city_id), time_param))


@api.get("/cities/<city_id>/stations/<station_id>/timeseries")
def station_timeseries(city_id, station_id):
    try:
        hours = int(request.args.get("hours", 168))
    except ValueError:
        raise ValidationError("'hours' must be an integer")
    if not 1 <= hours <= 24 * 92:
        raise ValidationError("'hours' must be between 1 and 2208")
    try:
        return jsonify(get_analysis_service().station_timeseries(_city(city_id), station_id, hours))
    except KeyError:
        raise LookupError(f"Unknown station '{station_id}'")


@api.get("/cities/<city_id>/timesteps")
def timesteps(city_id):
    return jsonify(get_analysis_service().timesteps_payload(_city(city_id)))


@api.get("/cities/<city_id>/weather")
def weather(city_id):
    try:
        hours = int(request.args.get("hours", 168))
    except ValueError:
        raise ValidationError("'hours' must be an integer")
    return jsonify(get_analysis_service().weather_payload(_city(city_id), max(1, min(hours, 24 * 92))))


# ----------------------------------------------------------------------- analyses


@api.get("/cities/<city_id>/grid")
def grid(city_id):
    return jsonify(get_analysis_service().grid_payload(_city(city_id), parse_time(request.args)))


@api.get("/cities/<city_id>/gaps")
def gaps(city_id):
    return jsonify(get_analysis_service().gaps_payload(_city(city_id), parse_time(request.args), parse_weights(request.args)))


@api.get("/cities/<city_id>/recommendations")
def recommendations(city_id):
    args = request.args
    return jsonify(get_analysis_service().recommendations_payload(
        _city(city_id), parse_time(args), parse_weights(args), parse_constraints(args)))


@api.post("/cities/<city_id>/simulate")
def simulate(city_id):
    body = _body()
    sites = parse_sites(body)
    time_param = parse_time(body)
    weights = parse_weights(body.get("weights") or {})
    return jsonify(get_analysis_service().simulate_payload(_city(city_id), time_param, weights, sites))


@api.post("/cities/<city_id>/osse")
def osse(city_id):
    sites = parse_sites(_body(), max_sites=10)
    return jsonify(get_analysis_service().osse_payload(_city(city_id), sites))


@api.get("/cities/<city_id>/metrics")
def metrics(city_id):
    return jsonify(get_analysis_service().metrics_payload(_city(city_id)))
