"""Unit tests for mountain conditions and the snow-quality rating (powder/conditions.py)."""

from datetime import date

import pytest

from powder.conditions import (
    DayConditions,
    c_to_f,
    conditions_json,
    lapse_temp_c,
    mid_mountain_ft,
    rate_snow,
    summarize_hourly,
)

pytestmark = pytest.mark.unit

BASE_FT = 8000
PEAK_FT = 11000


def day(**kw) -> DayConditions:
    return DayConditions(date=date(2026, 1, 10), **kw)


class TestLapse:
    def test_cools_going_up(self):
        assert lapse_temp_c(0.0, 1000, 2000) == pytest.approx(-6.5)

    def test_warms_going_down(self):
        assert lapse_temp_c(-10.0, 3000, 2000) == pytest.approx(-3.5)

    def test_c_to_f(self):
        assert c_to_f(0) == 32
        assert c_to_f(-10) == pytest.approx(14)

    def test_mid_mountain(self):
        assert mid_mountain_ft(8000, 11000) == 9500
        assert mid_mountain_ft(8000, None) == 8000


class TestSummarizeHourly:
    def hourly(self):
        # Two local days, 2 hours each. Model point at the base (8000 ft = 2438.4 m).
        return {
            "time": ["2026-01-10T00:00", "2026-01-10T12:00", "2026-01-11T00:00", "2026-01-11T12:00"],
            "temperature_2m": [-5.0, -1.0, 2.0, 4.0],
            "freezing_level_height": [1500.0, 1800.0, 3000.0, 3600.0],
            "snowfall": [2.0, 0.0, 0.0, 0.0],
            "rain": [0.0, 0.0, 5.08, 0.0],
            "wind_gusts_10m": [40.0, 80.0, 16.09344, None],
        }

    def test_groups_by_local_date(self):
        result = summarize_hourly(self.hourly(), 2438.4, BASE_FT, PEAK_FT)
        assert list(result) == [date(2026, 1, 10), date(2026, 1, 11)]

    def test_temperatures_moved_to_mid_mountain(self):
        jan10 = summarize_hourly(self.hourly(), 2438.4, BASE_FT, PEAK_FT)[date(2026, 1, 10)]
        # 1500 ft up from the base is ~457 m: ~2.97 °C colder
        expected_min = c_to_f(-5.0 - 457.2 * 0.0065)
        assert jan10.temp_min_f == pytest.approx(expected_min, abs=0.05)
        assert jan10.ref_elevation_ft == 9500

    def test_snow_line_only_on_snow_days(self):
        result = summarize_hourly(self.hourly(), 2438.4, BASE_FT, PEAK_FT)
        assert result[date(2026, 1, 10)].snow_line_ft == pytest.approx(1500 * 3.28084 - 1000)
        assert result[date(2026, 1, 11)].snow_line_ft is None

    def test_rain_gusts_and_precip_freezing_level(self):
        jan11 = summarize_hourly(self.hourly(), 2438.4, BASE_FT, PEAK_FT)[date(2026, 1, 11)]
        assert jan11.rain_in == pytest.approx(0.2)
        assert jan11.gust_max_mph == pytest.approx(10.0)
        assert jan11.precip_freezing_level_ft == pytest.approx(3000 * 3.28084)

    def test_snow_temp_is_mean_over_precip_hours(self):
        jan10 = summarize_hourly(self.hourly(), 2438.4, BASE_FT, PEAK_FT)[date(2026, 1, 10)]
        assert jan10.snow_temp_f == pytest.approx(jan10.temp_min_f)  # only the snowing hour

    def test_missing_model_elevation_uses_base(self):
        a = summarize_hourly(self.hourly(), None, BASE_FT, PEAK_FT)
        b = summarize_hourly(self.hourly(), BASE_FT / 3.28084, BASE_FT, PEAK_FT)
        assert a[date(2026, 1, 10)].temp_min_f == pytest.approx(b[date(2026, 1, 10)].temp_min_f)

    def test_empty_or_short_fields(self):
        assert summarize_hourly({}, 0, BASE_FT, PEAK_FT) == {}
        only_time = summarize_hourly({"time": ["2026-01-10T00:00"]}, 0, BASE_FT, None)
        d = only_time[date(2026, 1, 10)]
        assert d.temp_min_f is None and d.freezing_level_min_ft is None and d.rain_in == 0


class TestRateSnow:
    def test_nothing_falling(self):
        assert rate_snow(day(rain_in=0.0, snow_temp_f=10), 0.2, BASE_FT, PEAK_FT) is None

    def test_champagne(self):
        assert rate_snow(day(snow_temp_f=12, freezing_level_min_ft=3000), 8, BASE_FT, PEAK_FT) == "champagne"

    def test_powder(self):
        assert rate_snow(day(snow_temp_f=22), 5, BASE_FT, PEAK_FT) == "powder"

    def test_heavy(self):
        assert rate_snow(day(snow_temp_f=30), 5, BASE_FT, PEAK_FT) == "heavy"

    def test_boundaries(self):
        assert rate_snow(day(snow_temp_f=15), 5, BASE_FT, PEAK_FT) == "champagne"
        assert rate_snow(day(snow_temp_f=27), 5, BASE_FT, PEAK_FT) == "powder"

    def test_rain_when_freezing_level_above_peak(self):
        d = day(rain_in=0.5, precip_freezing_level_ft=12000, snow_temp_f=36)
        assert rate_snow(d, 1.0, BASE_FT, PEAK_FT) == "rain"

    def test_mixed_when_rain_below_and_snow_up_top(self):
        d = day(rain_in=0.3, precip_freezing_level_ft=9000, snow_temp_f=31)
        assert rate_snow(d, 3.0, BASE_FT, PEAK_FT) == "mixed"

    def test_mixed_even_when_model_point_saw_no_snow(self):
        # Valley model point: rain only, but the freezing level is well below the summit
        d = day(rain_in=0.25, precip_freezing_level_ft=6000)
        assert rate_snow(d, 0.0, BASE_FT, PEAK_FT) == "mixed"

    def test_rain_with_no_freezing_level(self):
        assert rate_snow(day(rain_in=0.4), 0.0, BASE_FT, PEAK_FT) == "rain"

    def test_falls_back_to_day_mean_temperature(self):
        d = day(temp_min_f=5, temp_max_f=15)
        assert rate_snow(d, 4, BASE_FT, PEAK_FT) == "champagne"

    def test_no_temperature_no_rating(self):
        assert rate_snow(day(), 4, BASE_FT, PEAK_FT) is None

    def test_no_peak_uses_base(self):
        d = day(rain_in=0.3, precip_freezing_level_ft=BASE_FT + 500)
        assert rate_snow(d, 2, BASE_FT, None) == "rain"


class TestConditionsJson:
    def test_rounds_and_keeps_shape(self):
        d = day(temp_min_f=12.4, temp_max_f=20.6, snow_temp_f=14.2, freezing_level_min_ft=4000.4,
                freezing_level_max_ft=5000.6, snow_line_ft=3000.4, rain_in=0.123, gust_max_mph=33.3,
                ref_elevation_ft=9500, quality="champagne")
        out = conditions_json(d)
        assert out == {
            "temp_min_f": 12, "temp_max_f": 21, "snow_temp_f": 14, "freezing_level_ft": [4000, 5001],
            "snow_line_ft": 3000, "rain_inches": 0.12, "gust_mph": 33, "ref_elevation_ft": 9500,
            "quality": "champagne",
        }

    def test_missing_values_are_null(self):
        out = conditions_json(day())
        assert out["temp_min_f"] is None and out["freezing_level_ft"] == [None, None]
        assert out["quality"] is None
