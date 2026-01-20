"""Unit tests for the cache module."""

import pytest
from unittest.mock import patch, MagicMock

from powder.cache import (
    get_session,
    set_cache_enabled,
    clear_cache,
    CACHE_DIR,
    CACHE_PATH,
    DEFAULT_TTL_HOURS,
)


@pytest.fixture(autouse=True)
def reset_cache_state():
    """Reset cache state before and after each test."""
    # Import the module to access private vars
    import powder.cache as cache_module

    # Store original state
    original_session = cache_module._session
    original_enabled = cache_module._cache_enabled

    # Reset to initial state
    cache_module._session = None
    cache_module._cache_enabled = True

    yield

    # Restore original state
    cache_module._session = original_session
    cache_module._cache_enabled = original_enabled


@pytest.mark.unit
@pytest.mark.cache
class TestCacheConfiguration:
    """Tests for cache configuration constants."""

    def test_cache_dir_in_user_home(self):
        """Test that cache directory is in user's home."""
        assert ".cache" in str(CACHE_DIR)
        assert "powder" in str(CACHE_DIR)

    def test_default_ttl_is_12_hours(self):
        """Test default TTL is 12 hours."""
        assert DEFAULT_TTL_HOURS == 12


@pytest.mark.unit
@pytest.mark.cache
class TestGetSession:
    """Tests for get_session function."""

    @patch("powder.cache.requests_cache.CachedSession")
    @patch("powder.cache.CACHE_DIR")
    def test_creates_cached_session_when_enabled(
        self, mock_cache_dir, mock_cached_session
    ):
        """Test that get_session creates a CachedSession when caching enabled."""
        mock_cache_dir.mkdir = MagicMock()

        session = get_session()

        mock_cached_session.assert_called_once()
        call_kwargs = mock_cached_session.call_args[1]
        assert call_kwargs["backend"] == "sqlite"
        assert call_kwargs["expire_after"] == DEFAULT_TTL_HOURS * 3600
        assert call_kwargs["allowable_codes"] == [200]
        assert call_kwargs["stale_if_error"] is True

    @patch("powder.cache.requests_cache.CachedSession")
    @patch("powder.cache.CACHE_DIR")
    def test_returns_same_session_on_subsequent_calls(
        self, mock_cache_dir, mock_cached_session
    ):
        """Test that get_session returns the same session instance."""
        mock_cache_dir.mkdir = MagicMock()

        session1 = get_session()
        session2 = get_session()

        # CachedSession should only be called once
        assert mock_cached_session.call_count == 1
        assert session1 is session2

    @patch("powder.cache.requests_cache.CachedSession")
    @patch("powder.cache.CACHE_DIR")
    def test_creates_cache_directory(self, mock_cache_dir, mock_cached_session):
        """Test that cache directory is created."""
        mock_cache_dir.mkdir = MagicMock()

        get_session()

        mock_cache_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)


@pytest.mark.unit
@pytest.mark.cache
class TestSetCacheEnabled:
    """Tests for set_cache_enabled function."""

    def test_disabling_cache_resets_session(self):
        """Test that disabling cache resets the session."""
        import powder.cache as cache_module

        # Create a mock session
        cache_module._session = MagicMock()

        set_cache_enabled(False)

        assert cache_module._session is None
        assert cache_module._cache_enabled is False

    def test_enabling_cache_resets_session(self):
        """Test that enabling cache resets the session."""
        import powder.cache as cache_module

        cache_module._session = MagicMock()
        cache_module._cache_enabled = False

        set_cache_enabled(True)

        assert cache_module._session is None
        assert cache_module._cache_enabled is True

    @patch("powder.cache.requests_cache.CachedSession")
    @patch("powder.cache.CACHE_DIR")
    def test_disabled_cache_creates_session_with_zero_expire(
        self, mock_cache_dir, mock_cached_session
    ):
        """Test that disabled cache creates session with expire_after=0."""
        mock_cache_dir.mkdir = MagicMock()
        mock_session = MagicMock()
        mock_cached_session.return_value = mock_session

        set_cache_enabled(False)
        get_session()

        call_kwargs = mock_cached_session.call_args[1]
        assert call_kwargs["expire_after"] == 0


@pytest.mark.unit
@pytest.mark.cache
class TestClearCache:
    """Tests for clear_cache function."""

    @patch("powder.cache.get_session")
    def test_clear_cache_calls_cache_clear(self, mock_get_session):
        """Test that clear_cache clears the cache."""
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        clear_cache()

        mock_session.cache.clear.assert_called_once()
