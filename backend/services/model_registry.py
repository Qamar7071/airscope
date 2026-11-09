"""Model lifecycle: load trained artifacts, detect staleness, train in the background.

A model is *up to date* when its artifact version and feature schema match the
code and its dataset fingerprint matches the current dataset. Otherwise it is
(re)trained. Training runs in one background thread, primary city first, and
reports progress that the API exposes so the UI can show what is happening.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import Settings, get_settings, load_cities
from data.dataset_service import DatasetService, get_dataset_service
from ml.features import FEATURE_SCHEMA_VERSION
from ml.predict import ARTIFACT_VERSION, CityModel
from ml.train import InsufficientDataError, train_city

logger = logging.getLogger(__name__)

READY, TRAINING, PENDING, ERROR, NO_DATA = "ready", "training", "pending", "error", "no_data"


@dataclass
class CityStatus:
    state: str = PENDING
    progress: float = 0.0
    message: str = "Waiting to train"
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    trained_at: str | None = None
    history: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "history"}


class ModelRegistry:
    def __init__(self, settings: Settings | None = None, datasets: DatasetService | None = None):
        self.settings = settings or get_settings()
        self.datasets = datasets or get_dataset_service()
        self._models: dict[str, CityModel] = {}
        self._status: dict[str, CityStatus] = {cid: CityStatus() for cid in load_cities()}
        self._lock = threading.RLock()
        self._queue: list[str] = []
        self._worker: threading.Thread | None = None

    # ----------------------------------------------------------------- status
    def status(self, city_id: str) -> CityStatus:
        with self._lock:
            return self._status.setdefault(city_id, CityStatus())

    def statuses(self) -> dict[str, dict]:
        with self._lock:
            return {cid: st.to_dict() for cid, st in self._status.items()}

    def _set(self, city_id: str, **kw) -> None:
        with self._lock:
            st = self._status.setdefault(city_id, CityStatus())
            for k, v in kw.items():
                setattr(st, k, v)

    # ----------------------------------------------------------------- models
    def _load_if_current(self, city_id: str) -> CityModel | None:
        directory = CityModel.dir_for(self.settings.models_dir, city_id)
        if not (directory / "metadata.json").exists():
            return None
        try:
            model = CityModel.load(directory)
        except Exception as exc:  # corrupt or old artifact
            logger.info("Existing model for %s not usable (%s); will retrain", city_id, exc)
            return None
        meta = model.metadata
        if meta.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
            return None
        try:
            fingerprint = self.datasets.get(city_id).fingerprint()
        except Exception as exc:
            logger.warning("Could not fingerprint dataset for %s: %s", city_id, exc)
            return None
        if meta.get("dataset_fingerprint") != fingerprint:
            logger.info("Model for %s was trained on different data; will retrain", city_id)
            return None
        return model

    def get_model(self, city_id: str) -> CityModel | None:
        with self._lock:
            if city_id in self._models:
                return self._models[city_id]
        model = self._load_if_current(city_id)
        if model is not None:
            with self._lock:
                self._models[city_id] = model
            self._set(city_id, state=READY, progress=1.0, message="Model ready", trained_at=model.metadata.get("trained_at"), error=None)
        return model

    def invalidate(self, city_id: str) -> None:
        with self._lock:
            self._models.pop(city_id, None)

    # --------------------------------------------------------------- training
    def train_now(self, city_id: str, profile: str | None = None) -> None:
        def progress(msg: str, frac: float) -> None:
            self._set(city_id, message=msg, progress=round(float(frac), 3))

        self._set(city_id, state=TRAINING, progress=0.0, message="Starting training", error=None,
                  started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
        t0 = time.time()
        try:
            train_city(city_id, profile or self.settings.training_profile, models_dir=self.settings.models_dir, progress=progress)
            self.invalidate(city_id)
            model = self._load_if_current(city_id)
            if model is None:
                raise RuntimeError("Trained model could not be reloaded")
            with self._lock:
                self._models[city_id] = model
            self._set(city_id, state=READY, progress=1.0, message=f"Model ready (trained in {time.time() - t0:.0f} s)",
                      finished_at=datetime.now(timezone.utc).isoformat(), trained_at=model.metadata.get("trained_at"))
        except InsufficientDataError as exc:
            self._set(city_id, state=NO_DATA, progress=1.0, message=str(exc), error=str(exc),
                      finished_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:  # keep the server alive; surface the error
            logger.exception("Training failed for %s", city_id)
            self._set(city_id, state=ERROR, progress=1.0, message="Training failed", error=f"{type(exc).__name__}: {exc}",
                      finished_at=datetime.now(timezone.utc).isoformat())

    def ensure_all(self, background: bool = True, force: bool = False) -> None:
        """Load current models; queue missing/stale ones for training (primary city first)."""
        for cid in load_cities():
            if not force and self.get_model(cid) is not None:
                continue
            self.enqueue(cid)
        if not background:
            self._drain()
        else:
            self._start_worker()

    def enqueue(self, city_id: str) -> None:
        with self._lock:
            if city_id not in self._queue and self.status(city_id).state != TRAINING:
                self._queue.append(city_id)
                self._set(city_id, state=PENDING, progress=0.0, message="Queued for training")

    def request_retrain(self, city_id: str) -> None:
        self.datasets.invalidate(city_id)
        self.invalidate(city_id)
        self.enqueue(city_id)
        self._start_worker()

    def _start_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._drain, name="airscope-trainer", daemon=True)
            self._worker.start()

    def _drain(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                cid = self._queue.pop(0)
            self.train_now(cid)


_registry: ModelRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ModelRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ModelRegistry()
        return _registry


def reset_registry(registry: ModelRegistry | None = None) -> None:
    """Replace the global registry (used by tests and the app factory)."""
    global _registry
    with _registry_lock:
        _registry = registry
