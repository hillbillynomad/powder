"""Unit tests for the GFS weather overlay export (powder.overlays).

GRIB2 messages are generated in-memory with eccodes so decoding runs against the real
format; HTTP (the .idx index and byte-range reads) is mocked with `responses`.
"""

import json
import re
from datetime import UTC, datetime

import eccodes
import numpy as np
import pytest
import requests
import responses
from PIL import Image

from powder import overlays
from powder.overlays import (
    ENCODINGS,
    GRID,
    byte_ranges,
    decode,
    decode_message,
    derive_outputs,
    encode,
    export_overlays,
    file_url,
    find_latest_run,
    floor_to_run,
    frame_source,
    frame_times,
)

pytestmark = [pytest.mark.unit, pytest.mark.overlays]

RUN = datetime(2026, 10, 14, 12, tzinfo=UTC)
GFS_NI, GFS_NJ = 1440, 721  # 0.25 degree global grid, lon 0..359.75, lat 90..-90


def gfs_message(values: np.ndarray, missing_mask: np.ndarray | None = None) -> bytes:
    """A global 0.25 degree GRIB2 message laid out like GFS (north->south, lon from 0)."""
    gid = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        for key, value in {
            "Ni": GFS_NI, "Nj": GFS_NJ,
            "latitudeOfFirstGridPointInDegrees": 90.0, "latitudeOfLastGridPointInDegrees": -90.0,
            "longitudeOfFirstGridPointInDegrees": 0.0, "longitudeOfLastGridPointInDegrees": 359.75,
            "iDirectionIncrementInDegrees": 0.25, "jDirectionIncrementInDegrees": 0.25,
        }.items():
            eccodes.codes_set(gid, key, value)
        flat = values.astype(np.float64).ravel().copy()
        if missing_mask is not None:
            eccodes.codes_set(gid, "bitmapPresent", 1)
            flat[missing_mask.ravel()] = eccodes.codes_get(gid, "missingValue")
        eccodes.codes_set_values(gid, flat)
        return eccodes.codes_get_message(gid)
    finally:
        eccodes.codes_release(gid)


def lon_grid() -> np.ndarray:
    """GFS longitudes (0..359.75) for every point."""
    return np.tile(np.arange(GFS_NI) * 0.25, (GFS_NJ, 1))


# ---- Encoding ---------------------------------------------------------------------------

class TestEncoding:
    @pytest.mark.parametrize("field,values", [
        ("temp_f", np.array([-80.0, -12.4, 0.0, 32.0, 71.3, 120.0])),
        ("depth_in", np.array([0.0, 0.5, 3.0, 24.0, 120.0, 200.0])),
        ("new_in", np.array([0.0, 0.2, 1.0, 8.0, 30.0, 60.0])),
        ("density", np.array([0.0, 100.0, 250.0, 500.0])),
    ])
    def test_round_trip_within_one_code_step(self, field, values):
        codes = encode(field, values)
        assert codes.dtype == np.uint8
        back = decode(field, codes)
        # Worst-case error is half a code step at the top of the range
        enc = ENCODINGS[field]
        if enc["kind"] == "linear":
            tolerance = enc["scale"] / 2 + 1e-9
        else:
            tolerance = enc["max"] * (1 - (254.5 / 255) ** 2) + 1e-9
        assert np.all(np.abs(back - values) <= tolerance)

    def test_sqrt_encoding_keeps_small_snow_amounts_precise(self):
        back = decode("depth_in", encode("depth_in", np.array([0.5])))
        assert abs(back[0] - 0.5) < 0.05

    def test_out_of_range_and_nan_are_clamped(self):
        assert list(encode("temp_f", np.array([-200.0, 500.0, np.nan]))) == [0, 255, 0]
        assert list(encode("depth_in", np.array([-3.0, 1e6]))) == [0, 255]


# ---- Run / frame planning ---------------------------------------------------------------

class TestRunPlanning:
    def test_floor_to_run(self):
        assert floor_to_run(datetime(2026, 10, 14, 17, 59, tzinfo=UTC)) == RUN
        assert floor_to_run(datetime(2026, 10, 14, 12, 0, tzinfo=UTC)) == RUN
        assert floor_to_run(datetime(2026, 10, 15, 3, 30, tzinfo=UTC)) == datetime(2026, 10, 15, 0, tzinfo=UTC)

    def test_frames_from_the_run_use_its_forecast_hours(self):
        assert frame_source(RUN, RUN) == (RUN, 0)
        assert frame_source(datetime(2026, 10, 16, 18, tzinfo=UTC), RUN) == (RUN, 54)

    def test_past_frames_use_the_earlier_cycle_that_covers_them(self):
        assert frame_source(datetime(2026, 10, 14, 11, tzinfo=UTC), RUN) == (
            datetime(2026, 10, 14, 6, tzinfo=UTC), 5)
        assert frame_source(datetime(2026, 10, 13, 12, tzinfo=UTC), RUN) == (
            datetime(2026, 10, 13, 12, tzinfo=UTC), 0)

    def test_frame_times_are_hourly_around_the_run(self):
        times = frame_times(RUN)
        assert len(times) == overlays.PAST_HOURS + overlays.FUTURE_HOURS + 1
        assert times[0] == datetime(2026, 10, 13, 12, tzinfo=UTC)
        assert all((b - a).total_seconds() == 3600 for a, b in zip(times, times[1:]))

    def test_file_url(self):
        assert file_url(RUN, 7) == (
            "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20261014/12/atmos/gfs.t12z.pgrb2.0p25.f007")

    @responses.activate
    def test_find_latest_run_falls_back_to_the_previous_complete_cycle(self):
        last = overlays.FUTURE_HOURS
        responses.add(responses.HEAD, f"{file_url(datetime(2026, 10, 14, 18, tzinfo=UTC), last)}.idx", status=404)
        responses.add(responses.HEAD, f"{file_url(RUN, last)}.idx", status=200)
        assert find_latest_run(requests.Session(), datetime(2026, 10, 14, 21, tzinfo=UTC)) == RUN

    @responses.activate
    def test_find_latest_run_gives_up_after_lookback(self):
        responses.add(responses.HEAD, re.compile(r".*\.idx$"), status=404)
        with pytest.raises(RuntimeError, match="No complete GFS run"):
            find_latest_run(requests.Session(), datetime(2026, 10, 14, 21, tzinfo=UTC))


# ---- Download + decode ------------------------------------------------------------------

class TestDecoding:
    def test_byte_ranges_from_idx(self):
        idx = ("1:0:d=2026101412:PRMSL:mean sea level:anl:\n"
               "2:100:d=2026101412:SNOD:surface:anl:\n"
               "3:250:d=2026101412:TMP:2 m above ground:anl:\n")
        ranges = byte_ranges(idx, {"SNOD": ":SNOD:surface:", "TMP": ":TMP:2 m above ground:"})
        assert ranges == {"SNOD": (100, 249), "TMP": (250, None)}

    def test_byte_ranges_missing_field(self):
        with pytest.raises(KeyError):
            byte_ranges("1:0:d=x:TMP:2 m above ground:anl:\n", {"SNOD": ":SNOD:surface:"})

    def test_decode_rolls_to_minus_180_and_downsamples_to_half_degree(self):
        grid = decode_message(gfs_message(lon_grid()))
        assert grid.shape == (GRID.nj, GRID.ni)
        assert grid.dtype == np.float32
        # Column 0 is now 180 W (GFS longitude 180), the middle column is 0 degrees
        assert grid[0, 0] == pytest.approx(180.0, abs=0.01)
        assert grid[0, GRID.ni // 2] == pytest.approx(0.0, abs=0.01)
        assert grid[0, GRID.ni // 2 + 1] == pytest.approx(0.5, abs=0.01)

    def test_decode_turns_missing_points_into_zero(self):
        values = np.full((GFS_NJ, GFS_NI), 2.5)
        mask = np.zeros_like(values, dtype=bool)
        mask[:, : GFS_NI // 2] = True  # 0..180 E missing (e.g. open ocean for snow depth)
        grid = decode_message(gfs_message(values, mask))
        assert np.all(grid[:, GRID.ni // 2:] == 0)  # 0..180 E after the roll
        assert np.allclose(grid[:, : GRID.ni // 2], 2.5, atol=0.01)


class TestDeriveOutputs:
    def test_units_density_and_new_snow(self):
        shape = (2, 2)
        fields = {
            "TMP": np.full(shape, 273.15, dtype=np.float32),
            "SNOD": np.array([[0.0, 0.5], [1.0, 0.001]], dtype=np.float32),
            "WEASD": np.array([[0.0, 100.0], [300.0, 0.5]], dtype=np.float32),
        }
        earlier = np.array([[0.2, 0.25], [1.2, 0.0]], dtype=np.float32)
        out = derive_outputs(fields, earlier)
        assert np.allclose(out["temp_f"], 32.0, atol=1e-3)
        assert out["depth_in"][0, 1] == pytest.approx(0.5 * 39.3701, rel=1e-5)
        assert out["density"][0, 1] == pytest.approx(200.0)
        assert out["density"][1, 0] == pytest.approx(300.0)
        assert out["density"][1, 1] == 0  # too shallow to have a meaningful density
        assert out["density"][0, 0] == 0  # bare ground, no divide-by-zero
        # Gains count as new snow; melt/settling (1.2 -> 1.0, 0.2 -> 0) does not
        assert out["new_in"][0, 1] == pytest.approx(0.25 * 39.3701, rel=1e-5)
        assert out["new_in"][1, 0] == 0
        assert out["new_in"][0, 0] == 0


# ---- End to end (mocked HTTP) ---------------------------------------------------------------

def mock_gfs_bucket():
    """Serve the same three-message GRIB file for every cycle/hour, via idx + Range reads."""
    lat = np.repeat(np.linspace(90, -90, GFS_NJ)[:, None], GFS_NI, axis=1)
    messages = [
        (":TMP:2 m above ground:", gfs_message(np.full((GFS_NJ, GFS_NI), 268.15))),  # 23 F
        (":SNOD:surface:", gfs_message(np.where(lat > 60, 0.5, 0.0))),  # 0.5 m in the Arctic
        (":WEASD:surface:", gfs_message(np.where(lat > 60, 125.0, 0.0))),  # 250 kg/m3
    ]
    body = b""
    idx_lines = []
    for i, (selector, msg) in enumerate(messages, 1):
        idx_lines.append(f"{i}:{len(body)}:d=2026101412{selector}anl:")
        body += msg
    idx_text = "\n".join(idx_lines) + "\n"

    def serve_range(request):
        start, end = request.headers["Range"].removeprefix("bytes=").split("-")
        stop = int(end) + 1 if end else len(body)
        return 206, {}, body[int(start):stop]

    responses.add(responses.HEAD, re.compile(r".*\.idx$"), status=200)
    responses.add(responses.GET, re.compile(r".*\.idx$"), body=idx_text)
    responses.add_callback(responses.GET, re.compile(r".*pgrb2\.0p25\.f\d{3}$"), callback=serve_range)


class TestExportOverlays:
    @pytest.fixture(autouse=True)
    def small_window(self, monkeypatch):
        monkeypatch.setattr(overlays, "PAST_HOURS", 2)
        monkeypatch.setattr(overlays, "FUTURE_HOURS", 3)
        monkeypatch.setattr(overlays, "NEW_SNOW_WINDOW_HOURS", 2)
        monkeypatch.setattr(overlays, "DOWNLOAD_WORKERS", 2)

    @responses.activate
    def test_writes_frames_and_manifest(self, tmp_path):
        mock_gfs_bucket()
        (tmp_path / "20261013T00").mkdir()  # a stale run directory from an earlier build
        manifest = export_overlays(tmp_path, now=datetime(2026, 10, 14, 16, tzinfo=UTC))

        assert manifest["run"] == "2026-10-14T12:00:00Z"
        assert manifest["dir"] == "20261014T12"
        assert [f["time"] for f in manifest["frames"]] == [
            "2026-10-14T10:00:00Z", "2026-10-14T11:00:00Z", "2026-10-14T12:00:00Z",
            "2026-10-14T13:00:00Z", "2026-10-14T14:00:00Z", "2026-10-14T15:00:00Z"]
        assert manifest["fields"] == ENCODINGS
        assert manifest["grid"] == {"ni": 720, "nj": 361, "lat0": 90.0, "lon0": -180.0, "step": 0.5}

        on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert on_disk["frames"] == manifest["frames"]
        assert not (tmp_path / "20261013T00").exists()

        frame = manifest["frames"][0]["files"]
        assert set(frame) == set(ENCODINGS)
        run_dir = tmp_path / manifest["dir"]
        temp = np.asarray(Image.open(run_dir / frame["temp_f"]))
        depth = np.asarray(Image.open(run_dir / frame["depth_in"]))
        density = np.asarray(Image.open(run_dir / frame["density"]))
        new = np.asarray(Image.open(run_dir / frame["new_in"]))
        assert temp.shape == (361, 720) and temp.dtype == np.uint8
        assert np.allclose(decode("temp_f", temp), 23.0, atol=0.5)
        # Arctic rows have 0.5 m (19.7 in) of snow at 250 kg/m3; the tropics have none
        assert decode("depth_in", depth[10, 100]) == pytest.approx(19.7, abs=0.4)
        assert decode("density", density[10, 100]) == pytest.approx(250.0, abs=1.0)
        assert depth[180, 100] == 0 and density[180, 100] == 0
        assert np.all(new == 0)  # identical depth 2h earlier: no new snow

    @responses.activate
    def test_fetches_only_the_needed_byte_ranges(self, tmp_path):
        mock_gfs_bucket()
        export_overlays(tmp_path, now=datetime(2026, 10, 14, 16, tzinfo=UTC))
        grib_reads = [c.request for c in responses.calls
                      if c.request.method == "GET" and not c.request.url.endswith(".idx")]
        assert grib_reads and all("Range" in r.headers for r in grib_reads)
        # 6 frames x 3 fields, plus snow depth for the 2 hours before the first frame
        assert len(grib_reads) == 6 * 3 + 2
