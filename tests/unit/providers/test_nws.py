"""Unit tests for NWSProvider - the most complex provider with two-step API."""

import pytest
import responses
from datetime import date
from freezegun import freeze_time

from powder.providers.nws import ELEVATION_URL, NWSProvider, candidate_points, pick_point
from powder.resorts import SkiResort


@pytest.fixture
def provider():
    """Create NWSProvider instance."""
    return NWSProvider()


@pytest.fixture
def us_resort():
    """A sample US resort for NWS tests."""
    return SkiResort(
        name="Park City",
        country="US",
        region="UT",
        latitude=40.6514,
        longitude=-111.5080,
        elevation_base_ft=6800,
        timezone="America/Denver",
    )


@pytest.mark.unit
@pytest.mark.providers
class TestNWSProvider:
    """Tests for NWSProvider."""

    def test_provider_name(self, provider):
        """Test provider name property."""
        assert provider.name == "NWS"

    @responses.activate
    @freeze_time("2024-01-15")
    def test_two_step_api_lookup(
        self, provider, us_resort, nws_grid_response, nws_forecast_response
    ):
        """Test grid point lookup followed by forecast fetch."""
        # Step 1: Grid point lookup
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        # Step 2: Forecast fetch
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json=nws_forecast_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        assert len(responses.calls) == 2
        assert len(forecasts) <= 7
        assert all(f.source == "NWS" for f in forecasts)

    @responses.activate
    @freeze_time("2024-01-15")
    def test_hourly_to_daily_aggregation(self, provider, us_resort, nws_grid_response):
        """Test that hourly snowfall values are correctly summed to daily totals."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        # Multiple hourly values for same day (2024-01-15)
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={
                "properties": {
                    "snowfallAmount": {
                        "values": [
                            {"validTime": "2024-01-15T12:00:00+00:00/PT1H", "value": 10},
                            {"validTime": "2024-01-15T15:00:00+00:00/PT1H", "value": 15},
                            {"validTime": "2024-01-15T18:00:00+00:00/PT1H", "value": 5},
                            {"validTime": "2024-01-15T21:00:00+00:00/PT1H", "value": 10},
                        ]
                    }
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        # 40mm total = ~1.57 inches
        assert len(forecasts) >= 1
        jan_15 = next((f for f in forecasts if f.date == date(2024, 1, 15)), None)
        assert jan_15 is not None
        # 40mm * 0.0393701 ≈ 1.6 inches
        assert jan_15.snowfall_inches == pytest.approx(1.6, abs=0.1)

    @responses.activate
    @freeze_time("2024-01-15")
    def test_mm_to_inches_conversion(self, provider, us_resort, nws_grid_response):
        """Test millimeters to inches conversion accuracy."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        # 25.4mm = 1 inch exactly
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={
                "properties": {
                    "snowfallAmount": {
                        "values": [
                            {"validTime": "2024-01-15T18:00:00+00:00/PT6H", "value": 25.4},
                        ]
                    }
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        assert len(forecasts) == 1
        assert forecasts[0].snowfall_inches == pytest.approx(1.0, abs=0.1)

    @responses.activate
    def test_grid_point_error_returns_empty(self, provider, us_resort):
        """Test that grid point error returns empty list."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            status=404,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        assert forecasts == []
        assert len(responses.calls) == 1  # Should not make second call

    @responses.activate
    def test_grid_point_success_forecast_failure(
        self, provider, us_resort, nws_grid_response
    ):
        """Test that grid point success but forecast failure returns empty."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            status=500,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        assert forecasts == []

    @responses.activate
    @freeze_time("2024-01-15")
    def test_iso_8601_duration_parsing(self, provider, us_resort, nws_grid_response):
        """Test parsing of ISO 8601 duration format in validTime."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        # Test different ISO 8601 formats
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={
                "properties": {
                    "snowfallAmount": {
                        "values": [
                            # Standard format with duration
                            {"validTime": "2024-01-15T06:00:00+00:00/PT6H", "value": 10},
                            # Different timezone offset
                            {"validTime": "2024-01-15T14:00:00-07:00/PT6H", "value": 5},
                        ]
                    }
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        # Both should be parsed and aggregated for Jan 15
        assert len(forecasts) >= 1
        jan_15 = next((f for f in forecasts if f.date == date(2024, 1, 15)), None)
        assert jan_15 is not None

    @responses.activate
    @freeze_time("2024-01-15")
    def test_filters_past_dates(self, provider, us_resort, nws_grid_response):
        """Test that past dates are filtered out."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={
                "properties": {
                    "snowfallAmount": {
                        "values": [
                            # Yesterday - should be filtered
                            {"validTime": "2024-01-14T06:00:00+00:00/PT6H", "value": 50},
                            # Today - should be included
                            {"validTime": "2024-01-15T18:00:00+00:00/PT6H", "value": 10},
                            # Tomorrow - should be included
                            {"validTime": "2024-01-16T18:00:00+00:00/PT6H", "value": 20},
                        ]
                    }
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        dates = [f.date for f in forecasts]
        assert date(2024, 1, 14) not in dates
        assert date(2024, 1, 15) in dates
        assert date(2024, 1, 16) in dates

    @responses.activate
    @freeze_time("2024-01-15")
    def test_limits_to_requested_days(self, provider, us_resort, nws_grid_response):
        """Test that results are limited to requested number of days."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        # Return 14 days of data
        values = [
            {"validTime": f"2024-01-{15+i:02d}T06:00:00+00:00/PT6H", "value": 10}
            for i in range(14)
        ]
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={"properties": {"snowfallAmount": {"values": values}}},
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=3)

        assert len(forecasts) <= 3

    @responses.activate
    @freeze_time("2024-01-15")
    def test_handles_null_values(self, provider, us_resort, nws_grid_response):
        """Test handling of null snowfall values."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={
                "properties": {
                    "snowfallAmount": {
                        "values": [
                            {"validTime": "2024-01-15T06:00:00+00:00/PT6H", "value": None},
                            {"validTime": "2024-01-15T12:00:00+00:00/PT6H", "value": 10},
                        ]
                    }
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        # Should handle None gracefully (treat as 0)
        assert len(forecasts) >= 1

    @responses.activate
    @freeze_time("2024-01-15")
    def test_handles_malformed_validtime(self, provider, us_resort, nws_grid_response):
        """Test handling of malformed validTime entries."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={
                "properties": {
                    "snowfallAmount": {
                        "values": [
                            # Valid entry
                            {"validTime": "2024-01-15T18:00:00+00:00/PT6H", "value": 10},
                            # Malformed - should be skipped
                            {"validTime": "invalid-date", "value": 50},
                            # Missing validTime - should be skipped
                            {"value": 50},
                        ]
                    }
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        # Should process valid entry and skip malformed ones
        assert len(forecasts) >= 1

    @responses.activate
    @freeze_time("2024-01-15")
    def test_results_sorted_by_date(self, provider, us_resort, nws_grid_response):
        """Test that results are sorted chronologically."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        # Return dates out of order
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={
                "properties": {
                    "snowfallAmount": {
                        "values": [
                            {"validTime": "2024-01-17T06:00:00+00:00/PT6H", "value": 10},
                            {"validTime": "2024-01-15T06:00:00+00:00/PT6H", "value": 20},
                            {"validTime": "2024-01-16T06:00:00+00:00/PT6H", "value": 15},
                        ]
                    }
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        dates = [f.date for f in forecasts]
        assert dates == sorted(dates)

    @responses.activate
    def test_handles_empty_snowfall_data(
        self, provider, us_resort, nws_grid_response, nws_forecast_empty_response
    ):
        """Test handling of empty snowfall data."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json=nws_forecast_empty_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(us_resort, days=7)

        assert forecasts == []

    @responses.activate
    @freeze_time("2024-01-15")
    def test_groups_into_resort_local_days(self, provider, us_resort, nws_grid_response):
        """04:00 UTC on the 16th is still the evening of the 15th in Denver."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json=nws_grid_response,
        )
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={"properties": {"snowfallAmount": {"values": [
                {"validTime": "2024-01-15T18:00:00+00:00/PT6H", "value": 10},
                {"validTime": "2024-01-16T04:00:00+00:00/PT6H", "value": 15},
            ]}}},
        )
        forecasts = provider.get_snowfall_forecast(us_resort, days=7)
        assert [f.date for f in forecasts] == [date(2024, 1, 15)]
        assert forecasts[0].snowfall_inches == pytest.approx(1.0, abs=0.05)

    def test_query_point_without_peak_is_resort_point(self, provider, us_resort):
        assert provider.query_point(us_resort) == (us_resort.latitude, us_resort.longitude)

    @responses.activate
    def test_query_point_moves_to_mid_mountain(self, provider, sample_resort):
        """Of the candidates, the one at mid-mountain elevation (8,413 ft) wins."""
        points = candidate_points(sample_resort.latitude, sample_resort.longitude)
        elevations = [6800 / 3.28084] * len(points)
        elevations[3] = 8400 / 3.28084  # a 1 km point near mid-mountain
        elevations[-1] = 8413 / 3.28084  # a 3 km point at exactly mid, but further away
        responses.add(responses.GET, ELEVATION_URL, json={"elevation": elevations})
        assert provider.query_point(sample_resort) == points[3][:2]

    @responses.activate
    def test_query_point_falls_back_on_error(self, provider, sample_resort):
        responses.add(responses.GET, ELEVATION_URL, status=500)
        assert provider.query_point(sample_resort) == (sample_resort.latitude, sample_resort.longitude)

    def test_pick_point_skips_missing_elevations(self):
        points = [(1.0, 1.0, 0.0), (2.0, 2.0, 1000.0)]
        assert pick_point(points, [None, 2000.0], 6500) == (2.0, 2.0)

    @responses.activate
    def test_uses_correct_headers(self, provider, us_resort):
        """Test that NWS-required headers are sent."""
        responses.add(
            responses.GET,
            f"https://api.weather.gov/points/{us_resort.latitude},{us_resort.longitude}",
            json={
                "properties": {
                    "gridId": "SLC",
                    "gridX": 97,
                    "gridY": 175,
                }
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.weather.gov/gridpoints/SLC/97,175",
            json={"properties": {"snowfallAmount": {"values": []}}},
            status=200,
        )

        provider.get_snowfall_forecast(us_resort, days=7)

        # Check headers on first request
        request = responses.calls[0].request
        assert "User-Agent" in request.headers
        assert "Accept" in request.headers
