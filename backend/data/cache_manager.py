"""File-based JSON cache with time-to-live, used for live API responses.

Entries are stored as ``{"key", "stored_at", "data"}`` documents under
``cache/<namespace>/``. Writes are atomic (temp file + rename) so a crash never
leaves a half-written entry. Stale entries are kept on disk: when a live API
fails, AirScope can fall back to the last good response and say how old it is.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CacheManager:
    def __init__(self, root: Path, namespace: str = "live"):
        self.dir = Path(root) / namespace
        self._lock = threading.Lock()

    @staticmethod
    def make_key(*parts: Any, **params: Any) -> str:
        """Stable, human-readable cache key from positional parts and sorted params."""
        items = [str(p) for p in parts] + [f"{k}={params[k]}" for k in sorted(params)]
        return "|".join(items)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        prefix = "".join(c if c.isalnum() or c in "-_" else "_" for c in key.split("|")[0])[:40]
        return self.dir / f"{prefix}_{digest}.json"

    def get_entry(self, key: str) -> tuple[Any, datetime] | None:
        """Return ``(data, stored_at)`` regardless of age, or ``None``."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            if doc.get("key") != key:
                return None
            return doc["data"], datetime.fromisoformat(doc["stored_at"])
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Ignoring unreadable cache entry %s: %s", path.name, exc)
            return None

    def get(self, key: str, max_age_s: float | None = None) -> Any | None:
        entry = self.get_entry(key)
        if entry is None:
            return None
        data, stored_at = entry
        if max_age_s is not None and (utcnow() - stored_at).total_seconds() > max_age_s:
            return None
        return data

    def age_seconds(self, key: str) -> float | None:
        entry = self.get_entry(key)
        return None if entry is None else (utcnow() - entry[1]).total_seconds()

    def set(self, key: str, data: Any) -> Path:
        path = self._path(key)
        doc = {"key": key, "stored_at": utcnow().isoformat(), "data": data}
        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, separators=(",", ":"), default=str)
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise
        return path

    def invalidate(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def clear(self) -> int:
        if not self.dir.exists():
            return 0
        n = 0
        for p in self.dir.glob("*.json"):
            p.unlink()
            n += 1
        return n
