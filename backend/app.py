"""AirScope backend entry point.

    python app.py                 # API on http://localhost:8000 (trains missing models in the background)
    AIRSCOPE_PORT=9000 python app.py

If ``frontend/dist`` exists (``npm run build``), the built UI is served from the
same origin, so a single process runs the whole application.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from config import APP_VERSION, Settings, get_settings
from services.model_registry import get_registry


def create_app(settings: Settings | None = None, start_training: bool | None = None) -> Flask:
    settings = settings or get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Flask(__name__, static_folder=None)
    app.config["JSON_SORT_KEYS"] = False
    app.json.sort_keys = False
    app.json.ensure_ascii = False
    CORS(app, resources={r"/api/*": {"origins": list(settings.cors_origins)}})

    from api.routes import api

    app.register_blueprint(api)

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        if exc.code == 404 and not _is_api_path():
            index = _spa_index(settings)
            if index is not None:
                return send_from_directory(index.parent, index.name)
        return jsonify({"error": exc.name.lower().replace(" ", "_"), "message": exc.description}), exc.code

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):
        logging.getLogger("airscope").exception("Unhandled error")
        return jsonify({"error": "internal_error", "message": f"{type(exc).__name__}: {exc}"}), 500

    dist = Path(settings.frontend_dist)

    @app.get("/")
    def root():
        index = _spa_index(settings)
        if index is not None:
            return send_from_directory(index.parent, index.name)
        return jsonify({"name": "AirScope API", "version": APP_VERSION, "docs": "/api/health",
                        "hint": "Run the frontend with `npm run dev` in frontend/, or `npm run build` to serve it from here."})

    @app.get("/<path:path>")
    def static_files(path: str):
        if dist.exists() and (dist / path).is_file():
            return send_from_directory(dist, path)
        index = _spa_index(settings)
        if index is not None and not path.startswith("api/"):
            return send_from_directory(index.parent, index.name)
        return jsonify({"error": "not_found", "message": f"/{path} not found"}), 404

    should_train = settings.train_on_startup if start_training is None else start_training
    if should_train:
        get_registry().ensure_all(background=True)
    return app


def _is_api_path() -> bool:
    from flask import request

    return request.path.startswith("/api/")


def _spa_index(settings: Settings) -> Path | None:
    index = Path(settings.frontend_dist) / "index.html"
    return index if index.exists() else None


if __name__ == "__main__":
    port = int(os.environ.get("AIRSCOPE_PORT", "8000"))
    host = os.environ.get("AIRSCOPE_HOST", "127.0.0.1")
    create_app().run(host=host, port=port, debug=False, threaded=True)
