"""File-based disk cache with TTL (JSON, one file per cache key).

Cache entries are stored as JSON files under a configurable directory.
Each entry includes the payload and a `cached_at` timestamp.  Entries
older than `ttl_seconds` are treated as expired (stale).

Usage:
    cache = DiskCache(directory="output/.cache", ttl_seconds=3600)
    data = cache.get("reddit_MachineLearning")
    if data is None:
        data = fetch_from_reddit(...)
        cache.set("reddit_MachineLearning", data)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SAFE_CHAR = re.compile(r"[^a-zA-Z0-9_\-]")


class DiskCache:
    """Simple file-level JSON cache with TTL."""

    def __init__(
        self,
        directory: str | Path = "output/.cache",
        ttl_seconds: int = 3600,
    ) -> None:
        self._dir = Path(directory)
        self._ttl = int(ttl_seconds)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── public interface ───────────────────────────────────────────────────────
    def get(self, key: str) -> Any | None:
        """Return cached value or None if missing / expired."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.debug("[cache] corrupt entry for key %r — ignoring", key)
            return None

        cached_at = entry.get("cached_at", "")
        if cached_at and self._is_expired(cached_at):
            logger.debug("[cache] expired entry for key %r", key)
            return None

        return entry.get("payload")

    def set(self, key: str, value: Any) -> None:
        """Persist *value* under *key*."""
        entry = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "key": key,
            "payload": value,
        }
        path = self._path(key)
        try:
            path.write_text(
                json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.debug("[cache] stored key %r → %s", key, path)
        except OSError as exc:
            logger.warning("[cache] failed to write %r: %s", key, exc)

    def invalidate(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink(missing_ok=True)

    def clear(self) -> int:
        """Delete all cache files.  Returns number of files removed."""
        count = 0
        for p in self._dir.glob("*.json"):
            p.unlink(missing_ok=True)
            count += 1
        return count

    # ── internal ───────────────────────────────────────────────────────────────
    def _path(self, key: str) -> Path:
        safe = _SAFE_CHAR.sub("_", key)[:80]
        digest = hashlib.sha256(key.encode()).hexdigest()[:8]
        return self._dir / f"{safe}_{digest}.json"

    def _is_expired(self, cached_at: str) -> bool:
        try:
            ts = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            return age > self._ttl
        except (ValueError, TypeError):
            return True
