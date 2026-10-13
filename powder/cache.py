"""HTTP request caching for weather API calls."""

from pathlib import Path

import requests_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Cache location: ~/.cache/powder/http_cache.sqlite
CACHE_DIR = Path.home() / ".cache" / "powder"
CACHE_PATH = CACHE_DIR / "http_cache"

# Default TTL: 12 hours (weather data updates every 6-12 hours)
DEFAULT_TTL_HOURS = 12

# Transient-failure retry policy (rate limits and upstream hiccups).
# Honors Retry-After when the server sends it; otherwise exponential backoff.
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
RETRY_TOTAL = 5
RETRY_BACKOFF_FACTOR = 2.0  # sleeps ~2s, 4s, 8s, 16s, 32s


def _build_retry_adapter() -> HTTPAdapter:
    """Create an HTTPAdapter that retries 429/5xx responses with backoff."""
    retry = Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_CODES,
        allowed_methods=("GET", "HEAD"),
        respect_retry_after_header=True,
    )
    return HTTPAdapter(max_retries=retry)


# Module-level session (initialized lazily)
_session: requests_cache.CachedSession | None = None
_cache_enabled: bool = True


def set_cache_enabled(enabled: bool) -> None:
    """Enable or disable caching globally."""
    global _cache_enabled, _session
    _cache_enabled = enabled
    _session = None  # Reset session to pick up new setting


def get_session() -> requests_cache.CachedSession:
    """Get the cached requests session.

    Returns a CachedSession when caching is enabled, or a session
    with caching disabled when --no-cache is used.
    """
    global _session

    if _session is None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if _cache_enabled:
            _session = requests_cache.CachedSession(
                str(CACHE_PATH),
                backend="sqlite",
                expire_after=DEFAULT_TTL_HOURS * 3600,  # Convert to seconds
                allowable_codes=[200],  # Only cache successful responses
                stale_if_error=True,  # Use stale cache if API is down
            )
        else:
            # Disabled cache - still use CachedSession but with caching off
            _session = requests_cache.CachedSession(
                str(CACHE_PATH),
                backend="sqlite",
                expire_after=0,  # Don't cache new responses
            )
            # Clear any existing cache entries for this request
            _session.settings.disabled = True

        adapter = _build_retry_adapter()
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)

    return _session


def clear_cache() -> None:
    """Clear all cached responses."""
    session = get_session()
    session.cache.clear()
