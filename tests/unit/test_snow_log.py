"""Daily snow log (tools/calibrate/daily_log.py) and its scorer (daily_score.py), offline."""

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import responses

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "calibrate"))
import daily_log  # noqa: E402
import daily_score  # noqa: E402

PAYLOAD = "\n".join([
    '24:{"title":"Alta Ski Area","snow":"$27","updatedAt":"2026-11-22T14:39:14+00:00","status":"$2a",'
    '"recent":"$3d","recentStartingReportedDate":"2026-11-22T00:00:00+00:00"}',
    '27:{"base":null,"middle":111.76,"summit":null,"last24":2.54,"last48":15.24,"last72":38.1}',
    '2a:{"openFlag":2,"openingDate":"2026-11-25"}',
    '3d:["$3e","$3f"]',
    '3e:{"date":"2026-11-21","snow":12.7}',
    '3f:{"date":"2026-11-22","snow":2.54}',
    "",
])


def skireport_html(payload: str = PAYLOAD) -> str:
    """A page shaped like OnTheSnow's: the data split across Next.js flight chunks."""
    half = len(payload) // 2
    chunks = [payload[:half], payload[half:]]
    scripts = "".join(f"<script>self.__next_f.push([1,{json.dumps(c)}])</script>" for c in chunks)
    return f"<html><body><script>self.__next_f.push([0])</script>{scripts}</body></html>"


def export(generated_at: str, resorts: list[dict]) -> dict:
    return {"generated_at": generated_at, "resorts": resorts}


def resort(name="Alta", tz="America/Denver", first="2026-11-23", days=3, past=("2026-11-21", "2026-11-22")):
    cond = {"temp_min_f": 10, "temp_max_f": 20, "snow_temp_f": 15, "freezing_level_ft": [4000, 6000]}
    start = date.fromisoformat(first)
    return {
        "name": name, "country": "US", "region": "UT", "timezone": tz,
        "daily_forecasts": [{"date": (start + timedelta(days=i)).isoformat(), "avg_inches": 1.0 + i,
                             "sources": {"ECMWF": 1.0 + i, "GEM": 2.0}, "conditions": cond}
                            for i in range(days)],
        "historical_snowfall": [{"date": d, "snowfall_inches": 0.5, "conditions": cond} for d in past],
    }


@pytest.mark.unit
class TestParseReport:
    def test_reads_snow_in_inches(self):
        rep = daily_log.parse_report(skireport_html())
        assert rep["report_date"] == "2026-11-22"
        assert rep["updated_at"] == "2026-11-22T14:39:14+00:00"
        assert rep["new_24h_in"] == 1.0
        assert rep["new_48h_in"] == 6.0
        assert rep["new_72h_in"] == 15.0
        assert rep["depth_mid_in"] == 44.0
        assert rep["open_flag"] == 2
        assert rep["recent"] == {"2026-11-21": 5.0, "2026-11-22": 1.0}

    def test_missing_report_raises(self):
        with pytest.raises(ValueError):
            daily_log.parse_report(skireport_html('1:{"title":"no report here"}\n'))


@pytest.mark.unit
class TestResortRecord:
    def test_leads_from_resort_local_date(self):
        # 04:00 UTC on the 23rd is still the 22nd in Utah
        issued = datetime(2026, 11, 23, 4, tzinfo=UTC)
        rec = daily_log.resort_record(resort(), issued)
        assert rec["today"] == "2026-11-22"
        assert [d["lead"] for d in rec["forecast"]] == [1, 2, 3]
        assert [d["lead"] for d in rec["past"]] == [-1, 0]
        day = rec["forecast"][0]
        assert day["avg_in"] == 1.0 and day["sources"] == {"ECMWF": 1.0, "GEM": 2.0}
        assert day["snow_temp_f"] == 15 and day["freezing_level_ft"] == [4000, 6000]
        assert day["temp_f"] == [10, 20]

    def test_keeps_last_three_past_days(self):
        past = tuple(f"2026-11-{d}" for d in range(10, 23))
        rec = daily_log.resort_record(resort(past=past), datetime(2026, 11, 23, 18, tzinfo=UTC))
        assert [d["date"] for d in rec["past"]] == ["2026-11-20", "2026-11-21", "2026-11-22"]


@pytest.mark.unit
class TestLoggerMain:
    @responses.activate
    def test_writes_day_file_with_reports(self, tmp_path, monkeypatch):
        monkeypatch.setattr(daily_log, "SLUGS", {"Alta": "utah/alta-ski-area", "Nowhere": "x/nowhere"})
        monkeypatch.setattr(daily_log.time, "sleep", lambda s: None)
        responses.get(f"{daily_log.SITE}/robots.txt", body="User-agent: *\nAllow: /\n")
        responses.get(f"{daily_log.SITE}/utah/alta-ski-area/skireport", body=skireport_html())
        now = datetime.now(UTC)
        src = tmp_path / "forecasts.json"
        src.write_text(json.dumps(export(now.isoformat().replace("+00:00", "Z"),
                                         [resort(first=now.date().isoformat()), resort("Elsewhere")])))
        out = tmp_path / "log"

        assert daily_log.main(["--forecasts", str(src), "--out", str(out)]) == 0
        lines = [json.loads(x) for x in (out / f"{now.date()}.jsonl").read_text().splitlines()]
        assert [x["resort"] for x in lines] == ["Alta", "Elsewhere"]
        assert lines[0]["report"]["new_24h_in"] == 1.0
        assert lines[0]["report"]["slug"] == "utah/alta-ski-area"
        assert "report" not in lines[1]

    @responses.activate
    def test_scrape_failure_still_records_error(self, monkeypatch):
        monkeypatch.setattr(daily_log.time, "sleep", lambda s: None)
        responses.get(f"{daily_log.SITE}/robots.txt", body="User-agent: *\nAllow: /\n")
        responses.get(f"{daily_log.SITE}/a/b/skireport", body="<html>maintenance</html>")
        responses.get(f"{daily_log.SITE}/c/d/skireport", status=404)
        out = daily_log.scrape_reports({"A": "a/b", "C": "c/d"}, delay=0)
        assert "no snow report" in out["A"]["error"]
        assert "404" in out["C"]["error"]

    @responses.activate
    def test_unreadable_robots_means_no_scraping(self, monkeypatch):
        monkeypatch.setattr(daily_log.time, "sleep", lambda s: None)
        responses.get(f"{daily_log.SITE}/robots.txt", status=503)
        out = daily_log.scrape_reports({"A": "a/b"}, delay=0)
        assert out["A"]["error"].startswith("robots.txt unreadable")
        assert all("robots.txt" in c.request.url for c in responses.calls)

    @responses.activate
    def test_respects_robots(self, monkeypatch):
        responses.get(f"{daily_log.SITE}/robots.txt", body="User-agent: *\nDisallow: /\n")
        out = daily_log.scrape_reports({"A": "a/b"}, delay=0)
        assert out["A"]["error"] == "disallowed by robots.txt"
        assert len(responses.calls) == 1

    def test_does_not_overwrite_or_log_stale(self, tmp_path):
        now = datetime.now(UTC)
        src = tmp_path / "forecasts.json"
        src.write_text(json.dumps(export(now.isoformat(), [resort()])))
        day = tmp_path / f"{now.date()}.jsonl"
        day.write_text("keep\n")
        assert daily_log.main(["--forecasts", str(src), "--out", str(tmp_path), "--no-reports"]) == 0
        assert day.read_text() == "keep\n"

        old = (now - timedelta(days=3)).isoformat()
        src.write_text(json.dumps(export(old, [resort()])))
        assert daily_log.main(["--forecasts", str(src), "--out", str(tmp_path), "--no-reports"]) == 1


def log_line(issue: str, forecast: dict, report=None, past=None, temp=15):
    """A log line issued on `issue` with {date: inches} forecasts."""
    cond = {"snow_temp_f": temp, "freezing_level_ft": [0, 0], "temp_f": [temp - 5, temp + 5]}
    line = {
        "resort": "Alta", "today": issue,
        "forecast": [{"date": d, "avg_in": v, "sources": {"ECMWF": v * 2}, **cond} for d, v in forecast.items()],
        "past": [{"date": d, "snow_in": v, **cond} for d, v in (past or {}).items()],
    }
    if report:
        line["report"] = report
    return line


@pytest.mark.unit
class TestScore:
    def test_joins_report_to_forecast_by_lead(self):
        lines = [
            log_line("2026-11-20", {"2026-11-20": 0, "2026-11-21": 8, "2026-11-22": 4}),
            log_line("2026-11-21", {"2026-11-21": 6, "2026-11-22": 2}),
            log_line("2026-11-22", {"2026-11-22": 0}, report={"report_date": "2026-11-22", "new_24h_in": 10.0},
                     past={"2026-11-21": 7}),
        ]
        forecasts, reports = daily_score.index(lines)
        assert reports == {("Alta", "2026-11-22"): 10.0}
        rows = daily_score.pairs(forecasts, reports, [1, 2, 3], daily_score.ALIGN["blend"], 1.0)
        # lead 1: issued the 21st, 0.75 x 6 + 0.25 x 2; lead 2: issued the 20th, 0.75 x 8 + 0.25 x 4
        assert sorted(rows) == [(1, "cold", 5.0, 10.0), (2, "cold", 7.0, 10.0)]
        prev = daily_score.pairs(forecasts, reports, [1], daily_score.ALIGN["prev"], 1.0)
        assert prev == [(1, "cold", 6.0, 10.0)]
        src = daily_score.pairs(forecasts, reports, [1], daily_score.ALIGN["blend"], 1.0, key="ECMWF")
        assert src == [(1, "cold", 10.0, 10.0)]

    def test_dry_days_drop_out(self):
        lines = [log_line("2026-11-21", {"2026-11-21": 0.2, "2026-11-22": 0}),
                 log_line("2026-11-22", {"2026-11-22": 0}, report={"report_date": "2026-11-22", "new_24h_in": 0.0})]
        forecasts, reports = daily_score.index(lines)
        assert daily_score.pairs(forecasts, reports, [1], daily_score.ALIGN["blend"], 1.0) == []

    @pytest.mark.parametrize("temp,band", [(5, "cold"), (17.9, "cold"), (18, "mid"), (27, "mid"),
                                           (28, "warm"), (None, "unknown")])
    def test_bands(self, temp, band):
        assert daily_score.band_of(temp) == band

    def test_storm_temp_prefers_latest_log_and_weights_by_snow(self):
        forecasts, _ = daily_score.index([
            log_line("2026-11-20", {"2026-11-21": 5, "2026-11-22": 5}, temp=30),
            log_line("2026-11-22", {"2026-11-22": 1}, past={"2026-11-21": 9}, temp=10),
        ])
        assert daily_score.storm_temp(forecasts["Alta"], "2026-11-22", daily_score.ALIGN["blend"]) == 10

    def test_empty_last24_falls_back_to_same_report_in_recent(self):
        lines = [log_line("2026-11-22", {"2026-11-22": 0},
                          report={"report_date": "2026-11-21", "new_24h_in": None,
                                  "recent": {"2026-11-20": 1.0, "2026-11-21": 8.0}})]
        assert daily_score.index(lines)[1] == {("Alta", "2026-11-21"): 8.0}

    def test_backfill_from_recent(self):
        lines = [log_line("2026-11-22", {"2026-11-22": 0},
                          report={"report_date": "2026-11-22", "new_24h_in": 1.0,
                                  "recent": {"2026-11-21": 4.0, "2026-11-22": 1.0}})]
        assert daily_score.index(lines)[1] == {("Alta", "2026-11-22"): 1.0}
        assert daily_score.index(lines, backfill=True)[1] == {("Alta", "2026-11-21"): 4.0,
                                                              ("Alta", "2026-11-22"): 1.0}

    def test_main_runs_on_one_day(self, tmp_path, capsys):
        (tmp_path / "2026-11-22.jsonl").write_text(json.dumps(log_line("2026-11-22", {"2026-11-22": 3})) + "\n")
        assert daily_score.main([str(tmp_path)]) == 0
        assert "needs more days" in capsys.readouterr().out

    def test_main_prints_tables(self, tmp_path, capsys):
        days = {
            "2026-11-21": log_line("2026-11-21", {"2026-11-21": 6, "2026-11-22": 2}),
            "2026-11-22": log_line("2026-11-22", {"2026-11-22": 0},
                                   report={"report_date": "2026-11-22", "new_24h_in": 10.0}),
        }
        for d, line in days.items():
            (tmp_path / f"{d}.jsonl").write_text(json.dumps(line) + "\n")
        assert daily_score.main([str(tmp_path), "--sources"]) == 0
        out = capsys.readouterr().out
        assert "Forecast average" in out and "ECMWF" in out
        assert "-5.0\"" in out  # 5" forecast vs 10" reported
