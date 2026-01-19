"""HTTP request caching for weather API calls."""

from pathlib import Path

import requests_cache

# Cache location: ~/.cache/powder/http_cache.sqlite
CACHE_DIR = Path.home() / ".cache" / "powder"
CACHE_PATH = CACHE_DIR / "http_cache"

# Default TTL: 12 hours (weather data updates every 6-12 hours)
DEFAULT_TTL_HOURS = 12

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

    return _session


def clear_cache() -> None:
    """Clear all cached responses."""
    session = get_session()
    session.cache.clear()
