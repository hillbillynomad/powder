"""Unit tests for the resorts module."""

import json
import pytest
from pathlib import Path

from powder.resorts import (
    SkiResort,
    load_resorts,
    filter_resorts,
    get_default_config_path,
    PARK_CITY,
)


@pytest.mark.unit
@pytest.mark.resorts
class TestSkiResort:
    """Tests for SkiResort dataclass."""

    def test_create_resort(self):
        """Test creating a SkiResort instance."""
        resort = SkiResort(
            name="Test Resort",
            country="US",
            region="CO",
            latitude=40.0,
            longitude=-105.0,
            elevation_base_ft=9000,
        )
        assert resort.name == "Test Resort"
        assert resort.country == "US"
        assert resort.region == "CO"
        assert resort.latitude == 40.0
        assert resort.longitude == -105.0
        assert resort.elevation_base_ft == 9000

    def test_default_values(self):
        """Test default values are set correctly."""
        resort = SkiResort(
            name="Test",
            country="US",
            region="CO",
            latitude=40.0,
            longitude=-105.0,
            elevation_base_ft=9000,
        )
        assert resort.elevation_peak_ft is None
        assert resort.lift_count == 0
        assert resort.avg_snowfall_inches is None
        assert resort.pass_type is None
        assert resort.timezone == "UTC"


@pytest.mark.unit
@pytest.mark.resorts
@pytest.mark.elevation
class TestSkiResortElevation:
    """Tests for SkiResort elevation calculations."""

    def test_vertical_drop_calculation(self):
        """Test vertical_drop_ft property calculation."""
        resort = SkiResort(
            name="Test Resort",
            country="US",
            region="CO",
            latitude=40.0,
            longitude=-105.0,
            elevation_base_ft=9000,
            elevation_peak_ft=12000,
        )
        assert resort.vertical_drop_ft == 3000

    def test_vertical_drop_none_when_no_peak(self):
        """Test vertical_drop_ft is None when peak elevation unknown."""
        resort = SkiResort(
            name="Test Resort",
            country="US",
            region="CO",
            latitude=40.0,
            longitude=-105.0,
            elevation_base_ft=9000,
        )
        assert resort.vertical_drop_ft is None

    def test_elevation_ft_backward_compatibility(self):
        """Test elevation_ft property returns base elevation."""
        resort = SkiResort(
            name="Test Resort",
            country="US",
            region="CO",
            latitude=40.0,
            longitude=-105.0,
            elevation_base_ft=9000,
        )
        assert resort.elevation_ft == 9000

    def test_state_backward_compatibility(self):
        """Test state property returns region."""
        resort = SkiResort(
            name="Test Resort",
            country="US",
            region="Colorado",
            latitude=40.0,
            longitude=-105.0,
            elevation_base_ft=9000,
        )
        assert resort.state == "Colorado"
        assert resort.state == resort.region


@pytest.mark.unit
@pytest.mark.resorts
class TestLoadResorts:
    """Tests for load_resorts function."""

    def test_load_from_sample_file(self, sample_resorts_path):
        """Test loading resorts from sample JSON file."""
        resorts = load_resorts(sample_resorts_path)
        assert len(resorts) == 5
        assert all(isinstance(r, SkiResort) for r in resorts)

    def test_load_default_path(self):
        """Test loading from default config path."""
        resorts = load_resorts()
        assert len(resorts) > 0
        assert all(isinstance(r, SkiResort) for r in resorts)

    def test_load_nonexistent_file_raises(self):
        """Test that loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_resorts(Path("/nonexistent/path.json"))

    def test_load_handles_legacy_state_field(self, tmp_path):
        """Test backward compatibility with 'state' instead of 'region'."""
        legacy_file = tmp_path / "legacy.json"
        legacy_data = {
            "resorts": [
                {
                    "name": "Legacy Resort",
                    "country": "US",
                    "state": "Utah",  # Old field name
                    "latitude": 40.0,
                    "longitude": -111.0,
                    "elevation_ft": 8000,  # Old field name
                }
            ]
        }
        legacy_file.write_text(json.dumps(legacy_data))

        resorts = load_resorts(legacy_file)
        assert len(resorts) == 1
        assert resorts[0].region == "Utah"
        assert resorts[0].elevation_base_ft == 8000

    def test_load_handles_missing_optional_fields(self, tmp_path):
        """Test loading with missing optional fields."""
        minimal_file = tmp_path / "minimal.json"
        minimal_data = {
            "resorts": [
                {
                    "name": "Minimal Resort",
                    "latitude": 40.0,
                    "longitude": -111.0,
                    "elevation_base_ft": 8000,
                }
            ]
        }
        minimal_file.write_text(json.dumps(minimal_data))

        resorts = load_resorts(minimal_file)
        assert len(resorts) == 1
        assert resorts[0].country == "US"  # Default
        assert resorts[0].region == ""
        assert resorts[0].lift_count == 0

    def test_load_preserves_all_fields(self, sample_resorts_path):
        """Test that all fields are correctly loaded."""
        resorts = load_resorts(sample_resorts_path)

        # Find the EPIC resort
        epic_resort = next((r for r in resorts if r.name == "Test Mountain"), None)
        assert epic_resort is not None
        assert epic_resort.pass_type == "EPIC"
        assert epic_resort.elevation_peak_ft == 10026
        assert epic_resort.timezone == "America/Denver"


@pytest.mark.unit
@pytest.mark.resorts
class TestFilterResorts:
    """Tests for filter_resorts function."""

    def test_no_filter_returns_all(self, sample_resorts):
        """Test that no filters returns all resorts."""
        result = filter_resorts(sample_resorts)
        assert len(result) == len(sample_resorts)

    def test_filter_by_country(self, sample_resorts):
        """Test filtering by country code."""
        us_resorts = filter_resorts(sample_resorts, country_filter="US")
        assert len(us_resorts) == 3
        assert all(r.country == "US" for r in us_resorts)

    def test_filter_by_country_case_insensitive(self, sample_resorts):
        """Test that country filter is case-insensitive."""
        us_resorts_lower = filter_resorts(sample_resorts, country_filter="us")
        us_resorts_upper = filter_resorts(sample_resorts, country_filter="US")
        assert len(us_resorts_lower) == len(us_resorts_upper)

    def test_filter_by_name_partial_match(self, sample_resorts):
        """Test partial name matching."""
        results = filter_resorts(sample_resorts, name_filter="Valley")
        # Should match "Deer Valley"
        assert len(results) == 1
        assert results[0].name == "Deer Valley"

    def test_filter_by_name_matches_vail(self, sample_resorts):
        """Test partial name matching for Vail."""
        results = filter_resorts(sample_resorts, name_filter="Vail")
        assert len(results) == 1
        assert results[0].name == "Vail"

    def test_filter_by_name_case_insensitive(self, sample_resorts):
        """Test that name filter is case-insensitive."""
        results_lower = filter_resorts(sample_resorts, name_filter="vail")
        results_upper = filter_resorts(sample_resorts, name_filter="VAIL")
        assert len(results_lower) == len(results_upper)

    def test_filter_by_region(self, sample_resorts):
        """Test filtering by region."""
        ut_resorts = filter_resorts(sample_resorts, region_filter="UT")
        assert len(ut_resorts) == 2
        assert all(r.region == "UT" for r in ut_resorts)

    def test_filter_by_pass_type(self, sample_resorts):
        """Test filtering by pass type."""
        epic_resorts = filter_resorts(sample_resorts, pass_filter="EPIC")
        assert len(epic_resorts) == 3
        assert all(r.pass_type == "EPIC" for r in epic_resorts)

    def test_filter_by_ikon_pass(self, sample_resorts):
        """Test filtering by IKON pass."""
        ikon_resorts = filter_resorts(sample_resorts, pass_filter="IKON")
        assert len(ikon_resorts) == 1
        assert ikon_resorts[0].name == "Deer Valley"

    def test_filter_multiple_criteria(self, sample_resorts):
        """Test combining multiple filters."""
        results = filter_resorts(
            sample_resorts,
            country_filter="US",
            region_filter="UT",
            pass_filter="EPIC",
        )
        # Only Test Mountain matches US + UT + EPIC
        assert len(results) == 1
        assert results[0].name == "Test Mountain"

    def test_state_filter_deprecated_alias(self, sample_resorts):
        """Test deprecated state_filter works as region_filter alias."""
        results_region = filter_resorts(sample_resorts, region_filter="UT")
        results_state = filter_resorts(sample_resorts, state_filter="UT")
        assert len(results_region) == len(results_state)

    def test_filter_no_matches_returns_empty(self, sample_resorts):
        """Test that no matches returns empty list."""
        results = filter_resorts(sample_resorts, country_filter="XX")
        assert results == []

    def test_filter_pass_type_none_excluded(self, sample_resorts):
        """Test that resorts without pass_type are excluded from pass filter."""
        # Chamonix has no pass_type
        results = filter_resorts(sample_resorts, pass_filter="EPIC")
        names = [r.name for r in results]
        assert "Chamonix" not in names


@pytest.mark.unit
@pytest.mark.resorts
class TestGetDefaultConfigPath:
    """Tests for get_default_config_path function."""

    def test_returns_path_object(self):
        """Test that function returns a Path object."""
        path = get_default_config_path()
        assert isinstance(path, Path)

    def test_path_points_to_resorts_json(self):
        """Test that path ends with resorts.json."""
        path = get_default_config_path()
        assert path.name == "resorts.json"
        assert path.parent.name == "data"


@pytest.mark.unit
@pytest.mark.resorts
class TestParkCityConstant:
    """Tests for the PARK_CITY constant."""

    def test_park_city_exists(self):
        """Test that PARK_CITY constant is defined."""
        assert PARK_CITY is not None
        assert isinstance(PARK_CITY, SkiResort)

    def test_park_city_properties(self):
        """Test PARK_CITY has correct values."""
        assert PARK_CITY.name == "Park City Mountain"
        assert PARK_CITY.country == "US"
        assert PARK_CITY.region == "UT"
        assert PARK_CITY.pass_type == "EPIC"
        assert PARK_CITY.elevation_base_ft == 6800
        assert PARK_CITY.elevation_peak_ft == 10026
