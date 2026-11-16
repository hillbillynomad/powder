"""Snow ratio, storm rate, calibration and mid-mountain requests shared by the Open-Meteo providers."""

from datetime import date

import numpy as np
import pytest
import responses

from powder.providers import open_meteo_common as omc
from powder.providers.ecmwf import ECMWFProvider
from powder.providers.gem import GEMProvider
from powder.providers.open_meteo import OpenMeteoProvider
from powder.providers.open_meteo_common import (
    MAX_SLR,
    MIN_SLR,
    calibration_factor,
    daily_snowfall,
    mid_mountain_m,
    request_params,
    snow_ratio,
    storm_rates,
)
from powder.resorts import SkiResort


@pytest.mark.unit
@pytest.mark.providers
class TestSnowRatio:
    def test_pivot_at_one_mm_per_hour(self):
        assert snow_ratio(-2.0, 1.0) == pytest.approx(0.84 * 12)

    def test_colder_snow_is_fluffier(self):
        assert snow_ratio(-10.0) > snow_ratio(-5.0) > snow_ratio(-2.0) > snow_ratio(0.0)

    def test_heavy_storms_pack_denser(self):
        assert snow_ratio(-5.0, 3.0) < snow_ratio(-5.0, 1.0) < snow_ratio(-5.0, 0.3)

    def test_clamped(self):
        assert snow_ratio(5.0, 5.0) == MIN_SLR
        assert snow_ratio(-30.0, 0.01) == MAX_SLR

    def test_missing_temperature_assumes_minus_5(self):
        assert snow_ratio(None, 1.0) == snow_ratio(-5.0, 1.0)


@pytest.mark.unit
@pytest.mark.providers
class TestStormRates:
    def test_matches_numpy_same_convolution(self):
        water = [0, 0, 3, 6, 0, 1, 0, 0, 2, 0]
        expected = np.convolve(water, np.ones(6) / 6, mode="same")
        assert storm_rates(water) == pytest.approx(list(expected))


@pytest.mark.unit
@pytest.mark.providers
class TestDailySnowfall:
    def test_water_times_ratio(self):
        # 7 cm of Open-Meteo snow = 10 mm of water; alone in a 6 h window -> rate 10/6 mm/h
        data = {"hourly": {"time": ["2024-01-15T03:00"], "snowfall": [7.0], "temperature_2m": [-2.0]}}
        [day] = daily_snowfall(data, "X")
        assert day.snowfall_inches == pytest.approx(10 / 25.4 * snow_ratio(-2.0, 10 / 6), abs=0.05)

    def test_groups_hours_into_local_days(self):
        data = {"hourly": {"time": ["2024-01-15T00:00", "2024-01-15T23:00", "2024-01-16T00:00"],
                           "snowfall": [1.0, 1.0, None], "temperature_2m": [-3, -3, None]}}
        days = daily_snowfall(data, "X")
        assert [d.date for d in days] == [date(2024, 1, 15), date(2024, 1, 16)]
        assert days[1].snowfall_inches == 0.0

    def test_falls_back_to_daily_sum(self):
        days = daily_snowfall({"daily": {"time": ["2024-01-15"], "snowfall_sum": [10.0]}}, "X")
        assert days[0].snowfall_inches == pytest.approx(3.9, abs=0.1)

    def test_empty(self):
        assert daily_snowfall(None, "X") == []
        assert daily_snowfall({}, "X") == []


@pytest.mark.unit
@pytest.mark.providers
class TestCalibration:
    TABLE = {"ECMWF": {"default": 1.1, "regions": {"US-UT": 1.4}}}

    def test_region_then_default_then_one(self, monkeypatch, sample_resort, european_resort):
        monkeypatch.setattr(omc, "_calibration", lambda: self.TABLE)
        assert calibration_factor("ECMWF", sample_resort) == 1.4  # Park City, UT
        assert calibration_factor("ECMWF", european_resort) == 1.1
        assert calibration_factor("ICON", european_resort) == 1.0

    def test_applied_to_daily_snowfall(self, monkeypatch, sample_resort):
        monkeypatch.setattr(omc, "_calibration", lambda: self.TABLE)
        data = {"daily": {"time": ["2024-01-15"], "snowfall_sum": [10.0]}}
        [day] = daily_snowfall(data, "ECMWF", sample_resort)
        assert day.snowfall_inches == pytest.approx(3.937 * 1.4, abs=0.06)

    def test_resort_factor_stacks_on_region(self, monkeypatch, sample_resort):
        table = dict(self.TABLE, resorts={sample_resort.name: 0.5})
        monkeypatch.setattr(omc, "_calibration", lambda: table)
        data = {"daily": {"time": ["2024-01-15"], "snowfall_sum": [10.0]}}
        [day] = daily_snowfall(data, "ECMWF", sample_resort)
        assert day.snowfall_inches == pytest.approx(3.937 * 1.4 * 0.5, abs=0.06)
        [raw] = daily_snowfall(data, "ECMWF", sample_resort, use_resort_factor=False)
        assert raw.snowfall_inches == pytest.approx(3.937 * 1.4, abs=0.06)
        # uncalibrated providers (ICON, NWS...) never take the resort factor
        assert omc.resort_factor("ICON", sample_resort) == 1.0

    def test_shipped_table_covers_calibrated_providers(self):
        omc._calibration.cache_clear() if hasattr(omc._calibration, "cache_clear") else None
        import json
        table = json.loads(omc.CALIBRATION_FILE.read_text())
        for source in ("Open-Meteo", "ECMWF", "GEM"):
            assert table[source]["default"] > 0
            assert all(v > 0 for v in table[source]["regions"].values())


@pytest.mark.unit
@pytest.mark.providers
class TestMidMountainRequests:
    def test_params_carry_mid_mountain_elevation(self, sample_resort):
        params = request_params(sample_resort, 7)
        mid_ft = (sample_resort.elevation_base_ft + sample_resort.elevation_peak_ft) / 2
        assert params["elevation"] == round(mid_ft / 3.28084) == mid_mountain_m(sample_resort)
        assert "temperature_2m" in params["hourly"] and "snowfall" in params["hourly"]

    @responses.activate
    @pytest.mark.parametrize("provider,model", [
        (OpenMeteoProvider(), "gfs_seamless"),
        (ECMWFProvider(), "ecmwf_ifs"),
        (GEMProvider(), "gem_seamless"),
    ])
    def test_providers_send_elevation_and_model(self, provider, model, sample_resort):
        responses.add(responses.GET, "https://api.open-meteo.com/v1/forecast",
                      json={"daily": {"time": [], "snowfall_sum": []}})
        provider.get_snowfall_forecast(sample_resort, days=7)
        url = responses.calls[0].request.url
        assert f"elevation={mid_mountain_m(sample_resort)}" in url
        assert f"models={model}" in url

    def test_gem_name(self):
        assert GEMProvider().name == "GEM"


def test_falls_back_from_state_to_country(monkeypatch):
    monkeypatch.setattr(omc, "_calibration", lambda: {"GEM": {"default": 1.5, "regions": {"JP": 2.0}}})
    r = SkiResort(name="X", country="JP", region="Hokkaido", latitude=43, longitude=141, elevation_base_ft=1000)
    assert calibration_factor("GEM", r) == 2.0
    r.country = "KR"
    assert calibration_factor("GEM", r) == 1.5
