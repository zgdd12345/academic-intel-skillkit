"""Source adapter ABC with built-in rate limiting, retry, and failure isolation.

All source adapters must subclass SourceAdapter and implement `_do_fetch()`.
The public `fetch()` method wraps it with:
  - token-bucket rate limiting
  - exponential-backoff retry (configurable per adapter)
  - per-source failure isolation (errors are logged, empty list returned)
  - structured logging
"""
from __future__ import annotations

import logging
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

try:
    import requests as _requests_lib
    _REQUESTS_AVAILABLE = True
except ImportError:
    _requests_lib = None  # type: ignore[assignment]
    _REQUESTS_AVAILABLE = False

from src.normalize.schema import NormalizedItem

logger = logging.getLogger(__name__)

# HTTP status codes that are worth retrying
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


# ── rate limiter ───────────────────────────────────────────────────────────────
class RateLimiter:
    """Simple token-bucket rate limiter (thread-safe).

    Ensures at most `requests_per_minute` calls per 60-second window by
    sleeping between acquisitions when the interval has not elapsed.
    """

    def __init__(self, requests_per_minute: float = 30.0) -> None:
        self._interval = 60.0 / max(requests_per_minute, 0.1)
        self._lock = threading.Lock()
        self._last_call: float = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()


# ── retry config ───────────────────────────────────────────────────────────────
@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_base: float = 2.0          # seconds; multiplied by 2^attempt
    max_backoff: float = 60.0
    retryable_codes: frozenset[int] = field(default_factory=lambda: _RETRYABLE)


# ── source error ───────────────────────────────────────────────────────────────
class SourceError(RuntimeError):
    """Raised when a source fetch fails unrecoverably."""


# ── abstract adapter ───────────────────────────────────────────────────────────
class SourceAdapter(ABC):
    """Base class for all source adapters.

    Subclass this and implement `_do_fetch(topics)`.  Call `fetch(topics)` from
    the pipeline — it wraps the implementation with retry and isolation.

    Class-level attributes:
        name        — short identifier used in NormalizedItem.source
        source_type — default SOURCE_TYPE_* for items this adapter produces
    """

    name: ClassVar[str] = "unknown"
    source_type: ClassVar[str] = "paper"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = config or {}
        rpm = float(self._config.get("requests_per_minute", 30))
        self._rate_limiter = RateLimiter(rpm)
        self._retry = RetryConfig(
            max_retries=int(self._config.get("max_retries", 3)),
            backoff_base=float(self._config.get("backoff_base", 2.0)),
            max_backoff=float(self._config.get("max_backoff", 60.0)),
        )
        if _REQUESTS_AVAILABLE:
            self._session = _requests_lib.Session()
            self._session.headers.update(
                {"User-Agent": f"academic-intel-skillkit/0.2 ({self.name})"}
            )
        else:
            self._session = None  # type: ignore[assignment]

    # ── public interface ───────────────────────────────────────────────────────
    @abstractmethod
    def _do_fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        """Implement source-specific fetch logic here.

        Should raise `SourceError` on unrecoverable errors.
        Should NOT catch network exceptions — `_http_get` handles retry.
        """

    def fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        """Fetch items with retry and failure isolation.

        Always returns a list; logs errors and returns [] on failure so the
        pipeline can continue with other sources.
        """
        try:
            items = self._do_fetch(topics)
            logger.info("[%s] fetched %d items", self.name, len(items))
            return items
        except SourceError as exc:
            logger.warning("[%s] fetch failed (isolated): %s", self.name, exc)
            return []
        except Exception:
            logger.exception("[%s] unexpected error during fetch (isolated)", self.name)
            return []

    # ── HTTP helper ────────────────────────────────────────────────────────────
    def _http_get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 20,
    ) -> Any:
        """HTTP GET with rate limiting + exponential-backoff retry.

        Returns a `requests.Response`.  Raises `SourceError` after all retries
        are exhausted.
        """
        if not _REQUESTS_AVAILABLE:
            raise SourceError(
                f"[{self.name}] 'requests' library not installed; "
                "run: pip install requests"
            )
        self._rate_limiter.acquire()
        last_exc: Exception | None = None

        for attempt in range(self._retry.max_retries + 1):
            try:
                resp = self._session.get(
                    url, params=params, headers=headers, timeout=timeout
                )
                if resp.status_code in self._retry.retryable_codes:
                    if attempt < self._retry.max_retries:
                        wait = min(
                            self._retry.backoff_base ** attempt,
                            self._retry.max_backoff,
                        )
                        logger.warning(
                            "[%s] HTTP %d — retry %d/%d in %.1fs",
                            self.name,
                            resp.status_code,
                            attempt + 1,
                            self._retry.max_retries,
                            wait,
                        )
                        time.sleep(wait)
                        self._rate_limiter.acquire()
                        continue
                resp.raise_for_status()
                return resp
            except Exception as exc:  # requests.RequestException etc.
                last_exc = exc
                if attempt < self._retry.max_retries:
                    wait = min(
                        self._retry.backoff_base ** attempt,
                        self._retry.max_backoff,
                    )
                    logger.warning(
                        "[%s] request error: %s — retry %d/%d in %.1fs",
                        self.name,
                        exc,
                        attempt + 1,
                        self._retry.max_retries,
                        wait,
                    )
                    time.sleep(wait)
                    self._rate_limiter.acquire()

        raise SourceError(
            f"[{self.name}] GET {url!r} failed after "
            f"{self._retry.max_retries} retries: {last_exc}"
        )

    # ── config helpers ─────────────────────────────────────────────────────────
    def _cfg(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def enabled(self) -> bool:
        return bool(self._config.get("enabled", True))
