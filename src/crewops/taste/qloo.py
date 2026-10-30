"""Client for the Qloo Taste AI API.

Only the server calls Qloo, never a browser, and only with aggregate signals: Qloo entity and
tag ids, a map point, a radius. No traveller or crew id, name, username or email is ever
sent: a person's picks reach Qloo only as the ids of the things they love. ``guard`` enforces
this on every request: a parameter outside the allow-list, or a value that looks like a
traveller or crew id or an email address, is refused before anything leaves the process.

Calls are bounded: one timeout, one retry for a rate limit or a server error, and a short
pause after repeated failures, so a slow Qloo never holds up a waiting passenger. Errors carry
a code (``QLOO_AUTH``, ``QLOO_RATE_LIMIT``, ``QLOO_UNAVAILABLE``, ``QLOO_BAD_RESPONSE``,
``QLOO_REFUSED``) that the tools pass on as they are.

The key comes from ``QLOO_API_KEY`` for local runs, and from a SecureString in Parameter Store
on the deployed server. It is sent only as the ``X-Api-Key`` header and never logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)

ALLOWED_PARAM = re.compile(
    r"^(filter|signal|bias|operator|feature)\.[a-z_.]+$|^(query|types|take|page|sort_by)$"
)
"""The request parameters any Groundtime feature needs. Anything else is a bug or an injection."""

PERSONAL = re.compile(
    r"\bC-\d{3,5}\b|\bTR-\d{3,6}\b|[\w.+-]+@[\w-]+\.[\w.]+|\bu-\d+\b", re.IGNORECASE
)
"""Crew ids (C-1042), traveller ids (TR-1001), email addresses and user ids. None of these
may reach Qloo."""

MAX_TAKE = 25
TIMEOUT_SECONDS = 12.0
FAILURES_BEFORE_PAUSE = 3
PAUSE_SECONDS = 60.0


class QlooError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after: str | None = None


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...

    def put(self, key: str, value: Any, ttl_seconds: int) -> None: ...


class MemoryCache:
    """Per-process cache, enough for tests and local runs. Oldest entries go first."""

    def __init__(self, size: int = 256) -> None:
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._size = size
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            found = self._items.get(key)
            if found is None:
                return None
            expires, value = found
            if expires < time.time():
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value

    def put(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            self._items[key] = (time.time() + ttl_seconds, value)
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)


Transport = Callable[[str, Mapping[str, str], float], tuple[int, bytes, Mapping[str, str]]]
"""``(url, headers, timeout) -> (status, body, response headers)``."""


def urllib_transport(
    url: str, headers: Mapping[str, str], timeout: float
) -> tuple[int, bytes, Mapping[str, str]]:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read() or b"", dict(err.headers or {})


def guard(params: Mapping[str, Any]) -> dict[str, str]:
    """The request as Qloo will see it, or ``QLOO_REFUSED`` if it could carry personal data."""
    out: dict[str, str] = {}
    for key, value in params.items():
        if value is None or value == "":
            continue
        if not ALLOWED_PARAM.match(key):
            raise QlooError("QLOO_REFUSED", f"parameter {key!r} is not one Groundtime sends")
        text = ",".join(str(v) for v in value) if isinstance(value, list | tuple) else str(value)
        if PERSONAL.search(text):
            raise QlooError("QLOO_REFUSED", f"{key} looks like it carries personal data")
        out[key] = text
    take = out.get("take")
    if take is not None and (not take.isdigit() or not 1 <= int(take) <= MAX_TAKE):
        raise QlooError("QLOO_REFUSED", f"take must be 1 to {MAX_TAKE}")
    return out


def cache_key(path: str, params: Mapping[str, str]) -> str:
    canonical = json.dumps([path, sorted(params.items())], separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class _Health:
    failures: int = 0
    paused_until: float = 0.0


class QlooClient:
    def __init__(
        self,
        base_url: str,
        key: Callable[[], str | None],
        *,
        transport: Transport = urllib_transport,
        cache: Cache | None = None,
        cache_seconds: int = 24 * 3600,
        timeout: float = TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = key
        self._transport = transport
        self._cache = cache if cache is not None else MemoryCache()
        self._cache_seconds = cache_seconds
        self._timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._health = _Health()
        self.calls = 0
        """Requests actually sent to Qloo (cache hits excluded)."""

    # -- Endpoints -----------------------------------------------------------

    def search(self, query: str, types: str, take: int = 5) -> dict[str, Any]:
        """Entities by name, e.g. an artist or a film a crew member loves."""
        return self.get("/search", {"query": query, "types": types, "take": take})

    def tags(self, query: str, parent_type: str | None = None, take: int = 5) -> dict[str, Any]:
        return self.get(
            "/v2/tags",
            {"filter.query": query, "filter.parents.types": parent_type, "take": take},
        )

    def insights(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Recommendations of one entity type, ranked by taste affinity to the signals."""
        return self.get("/v2/insights", params)

    # -- Plumbing ------------------------------------------------------------

    def get(self, path: str, params: Mapping[str, Any]) -> dict[str, Any]:
        sent = guard(params)
        key = cache_key(path, sent)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        body = self._fetch(path, sent)
        try:
            self._cache.put(key, body, self._cache_seconds)
        except Exception:  # a cache that can't store must not lose the answer
            log.warning("Qloo answer not cached", exc_info=True)
        return body

    def _fetch(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        if self._clock() < self._health.paused_until:
            raise QlooError("QLOO_UNAVAILABLE", "Qloo is paused after repeated failures", True)
        api_key = self._key()
        if not api_key:
            raise QlooError("QLOO_AUTH", "no Qloo API key is configured")
        url = f"{self._base}{path}?{urllib.parse.urlencode(params)}"
        headers = {"X-Api-Key": api_key, "Accept": "application/json"}
        error = QlooError("QLOO_UNAVAILABLE", "Qloo was not called", True)
        for attempt in (1, 2):
            try:
                self.calls += 1
                status, raw, response_headers = self._transport(url, headers, self._timeout)
            except (TimeoutError, OSError) as err:
                error = QlooError("QLOO_UNAVAILABLE", f"Qloo did not answer: {err}", True)
            else:
                found = self._error_for(status, response_headers)
                if found is None:
                    try:
                        body = json.loads(raw)
                    except ValueError:
                        found = QlooError("QLOO_BAD_RESPONSE", "Qloo answered with no JSON")
                    else:
                        if isinstance(body, dict):
                            self._health = _Health()
                            return body
                        found = QlooError("QLOO_BAD_RESPONSE", "Qloo answered with no object")
                error = found
            if not error.retryable or attempt == 2:
                break
            self._sleep(self._backoff(error))
        self._failed()
        raise error

    @staticmethod
    def _error_for(status: int, headers: Mapping[str, str]) -> QlooError | None:
        if 200 <= status < 300:
            return None
        if status in (401, 403):
            return QlooError("QLOO_AUTH", "Qloo refused the API key")
        if status == 429:
            error = QlooError("QLOO_RATE_LIMIT", "Qloo rate limit reached", True)
            error.retry_after = headers.get("Retry-After")
            return error
        if status >= 500:
            return QlooError("QLOO_UNAVAILABLE", f"Qloo error {status}", True)
        return QlooError("QLOO_BAD_RESPONSE", f"Qloo refused the request ({status})")

    @staticmethod
    def _backoff(error: QlooError) -> float:
        try:
            return min(2.0, max(0.2, float(error.retry_after))) if error.retry_after else 0.5
        except ValueError:
            return 0.5

    def _failed(self) -> None:
        self._health.failures += 1
        if self._health.failures >= FAILURES_BEFORE_PAUSE:
            self._health.paused_until = self._clock() + PAUSE_SECONDS
            self._health.failures = 0


def key_from_settings(settings: Any, session: Any | None = None) -> Callable[[], str | None]:
    """The key from the environment, or else read once from Parameter Store."""
    if settings.qloo_api_key:
        return lambda: settings.qloo_api_key
    found: dict[str, str] = {}

    def read() -> str | None:
        if "key" not in found:
            import boto3

            ssm = (session or boto3.Session(region_name=settings.aws_region)).client("ssm")
            try:
                found["key"] = ssm.get_parameter(
                    Name=settings.qloo_key_parameter, WithDecryption=True
                )["Parameter"]["Value"]
            except Exception:
                log.warning("Qloo API key not readable from %s", settings.qloo_key_parameter)
                return None
        return found["key"]

    return read


def client_from_settings(
    settings: Any, cache: Cache | None = None, session: Any | None = None
) -> QlooClient:
    return QlooClient(
        settings.qloo_api_url,
        key_from_settings(settings, session),
        cache=cache,
        cache_seconds=settings.qloo_cache_hours * 3600,
    )
