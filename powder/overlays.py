"""Global weather overlays (temperature, snow depth, new snow) from NOAA GFS.

Ventusky-style: for every hour in a window around the latest GFS run, each field is
written as one small grayscale "data image" on a 0.5 degree lat/lon grid, where the
pixel value encodes the physical value (see ENCODINGS). The web UI colours and
reprojects these in the browser and reads values back out for click-to-inspect.

Only the needed GRIB2 messages are downloaded, via HTTP range requests driven by each
file's .idx index, from NOAA's free GFS mirror on AWS (no API key).
"""

from __future__ import annotations

import json
import math
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import eccodes
import numpy as np
import requests
from PIL import Image

GFS_BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
GFS_RES = "0p25"  # hourly steps to f120; downsampled to 0.5 degrees on output
RUN_INTERVAL_HOURS = 6
PAST_HOURS = 24  # frames before the run time, from the previous runs' first hours
FUTURE_HOURS = 78  # frames after the run time; runs publish ~4-6h late, so ~72h ahead of now
NEW_SNOW_WINDOW_HOURS = 24
MAX_RUN_LOOKBACK = 4
DOWNLOAD_WORKERS = 16
TIMEOUT = 60

METERS_TO_INCHES = 39.3701
MIN_SNOW_DEPTH_M = 0.0025  # below this, density is meaningless

# GRIB2 message selectors as they appear in the .idx files
GRIB_FIELDS = {
    "TMP": ":TMP:2 m above ground:",
    "SNOD": ":SNOD:surface:",
    "WEASD": ":WEASD:surface:",
}

# How each output field maps to 8-bit pixel codes. "linear": value = offset + code * scale.
# "sqrt": value = max * (code / 255)^2, which keeps precision for small snow amounts.
ENCODINGS: dict[str, dict] = {
    "temp_f": {"kind": "linear", "offset": -80.0, "scale": 0.8, "units": "°F"},
    "depth_in": {"kind": "sqrt", "max": 200.0, "units": "in"},
    "new_in": {"kind": "sqrt", "max": 60.0, "units": "in"},
    "density": {"kind": "linear", "offset": 0.0, "scale": 2.0, "units": "kg/m³"},
}


@dataclass(frozen=True)
class Grid:
    """Output grid: rows run north to south from lat0, columns east from lon0."""

    ni: int = 720
    nj: int = 361
    lat0: float = 90.0
    lon0: float = -180.0
    step: float = 0.5


GRID = Grid()


# ---- Encoding ---------------------------------------------------------------------------

def encode(field: str, values: np.ndarray) -> np.ndarray:
    """Physical values -> uint8 codes for one field."""
    enc = ENCODINGS[field]
    if enc["kind"] == "linear":
        codes = (values - enc["offset"]) / enc["scale"]
    else:
        codes = np.sqrt(np.clip(values, 0, None) / enc["max"]) * 255
    return np.clip(np.round(np.nan_to_num(codes, nan=0.0)), 0, 255).astype(np.uint8)


def decode(field: str, codes: np.ndarray) -> np.ndarray:
    """uint8 codes -> physical values (inverse of encode, to within one code step)."""
    enc = ENCODINGS[field]
    codes = codes.astype(np.float64)
    if enc["kind"] == "linear":
        return enc["offset"] + codes * enc["scale"]
    return enc["max"] * (codes / 255) ** 2


# ---- Run / frame planning ---------------------------------------------------------------

def floor_to_run(t: datetime) -> datetime:
    """Most recent GFS cycle time (00/06/12/18Z) at or before t."""
    t = t.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return t - timedelta(hours=t.hour % RUN_INTERVAL_HOURS)


def frame_source(t: datetime, run: datetime) -> tuple[datetime, int]:
    """(cycle, forecast hour) to read valid time t from: the run itself from its start
    onwards, else the earlier cycle that covers t with its first few (best) hours."""
    if t >= run:
        return run, int((t - run).total_seconds() // 3600)
    cycle = floor_to_run(t)
    return cycle, int((t - cycle).total_seconds() // 3600)


def frame_times(run: datetime) -> list[datetime]:
    """Valid times of the published frames, hourly."""
    return [run + timedelta(hours=h) for h in range(-PAST_HOURS, FUTURE_HOURS + 1)]


def file_url(cycle: datetime, fhour: int) -> str:
    return (f"{GFS_BUCKET}/gfs.{cycle:%Y%m%d}/{cycle:%H}/atmos/"
            f"gfs.t{cycle:%H}z.pgrb2.{GFS_RES}.f{fhour:03d}")


def find_latest_run(session: requests.Session, now: datetime) -> datetime:
    """Newest cycle whose last needed forecast hour is already published."""
    cycle = floor_to_run(now)
    for _ in range(MAX_RUN_LOOKBACK):
        response = session.head(f"{file_url(cycle, FUTURE_HOURS)}.idx", timeout=TIMEOUT)
        if response.status_code == 200:
            return cycle
        cycle -= timedelta(hours=RUN_INTERVAL_HOURS)
    raise RuntimeError(f"No complete GFS run found in the last {MAX_RUN_LOOKBACK} cycles")


# ---- Download + decode ------------------------------------------------------------------

def byte_ranges(idx_text: str, selectors: dict[str, str]) -> dict[str, tuple[int, int | None]]:
    """Map each selector name to its message's (start, end-inclusive) byte range."""
    lines = [line for line in idx_text.splitlines() if line.strip()]
    ranges = {}
    for name, selector in selectors.items():
        for i, line in enumerate(lines):
            if selector in line:
                start = int(line.split(":")[1])
                end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else None
                ranges[name] = (start, end)
                break
        else:
            raise KeyError(f"{selector!r} not in GRIB index")
    return ranges


def decode_message(data: bytes) -> np.ndarray:
    """One GRIB2 message -> 2D array on the output grid (north-up, -180..180, 0.5 deg).
    Missing points (e.g. snow depth over open ocean) become 0."""
    gid = eccodes.codes_new_from_message(data)
    try:
        ni = eccodes.codes_get(gid, "Ni")
        nj = eccodes.codes_get(gid, "Nj")
        missing = eccodes.codes_get(gid, "missingValue")
        values = eccodes.codes_get_values(gid).reshape(nj, ni)
    finally:
        eccodes.codes_release(gid)
    values = np.where(values == missing, 0.0, values)
    values = np.roll(values, ni // 2, axis=1)  # 0..360 -> -180..180
    stride = round(ni / GRID.ni)
    # Copy so the full-resolution grid can be freed; float32 is plenty for 8-bit output
    return np.ascontiguousarray(values[::stride, ::stride][:GRID.nj, :GRID.ni], dtype=np.float32)


def fetch_fields(session: requests.Session, cycle: datetime, fhour: int,
                 names: list[str]) -> dict[str, np.ndarray]:
    """Download and decode the named GRIB fields from one GFS file."""
    url = file_url(cycle, fhour)
    idx = session.get(f"{url}.idx", timeout=TIMEOUT)
    idx.raise_for_status()
    ranges = byte_ranges(idx.text, {n: GRIB_FIELDS[n] for n in names})
    fields = {}
    for name, (start, end) in ranges.items():
        response = session.get(url, headers={"Range": f"bytes={start}-{'' if end is None else end}"},
                               timeout=TIMEOUT)
        response.raise_for_status()
        fields[name] = decode_message(response.content)
    return fields


# ---- Output -----------------------------------------------------------------------------

def derive_outputs(fields: dict[str, np.ndarray], snod_earlier: np.ndarray) -> dict[str, np.ndarray]:
    """Physical output fields for one frame."""
    snod = fields["SNOD"]
    with np.errstate(divide="ignore", invalid="ignore"):
        density = np.where(snod > MIN_SNOW_DEPTH_M, fields["WEASD"] / snod, 0.0)
    return {
        "temp_f": (fields["TMP"] - 273.15) * 9 / 5 + 32,
        "depth_in": snod * METERS_TO_INCHES,
        # Depth gained over the window; melt and settling are not "new snow"
        "new_in": np.clip(snod - snod_earlier, 0, None) * METERS_TO_INCHES,
        "density": density,
    }


def frame_key(t: datetime) -> str:
    return f"{t:%Y%m%dT%H}"


def write_frame(out_dir: Path, t: datetime, outputs: dict[str, np.ndarray]) -> dict[str, str]:
    paths = {}
    for field, values in outputs.items():
        rel = f"{field}-{frame_key(t)}.png"
        Image.fromarray(encode(field, values), "L").save(out_dir / rel, optimize=True)
        paths[field] = rel
    return paths


def build_manifest(run: datetime, run_dir: str, frames: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": "NOAA GFS",
        "run": run.isoformat().replace("+00:00", "Z"),
        "grid": {"ni": GRID.ni, "nj": GRID.nj, "lat0": GRID.lat0, "lon0": GRID.lon0, "step": GRID.step},
        "fields": ENCODINGS,
        "dir": run_dir,
        "frames": frames,
    }


def export_overlays(output_dir: Path, now: datetime | None = None,
                    session: requests.Session | None = None) -> dict:
    """Build every frame for the latest complete GFS run into output_dir.

    Layout: output_dir/manifest.json and output_dir/<run>/<field>-<time>.png. Each run
    gets its own directory so browsers can cache frames forever; older runs are removed.
    The manifest is written last, so a failed build never points at missing frames.
    """
    session = session or requests.Session()
    now = now or datetime.now(UTC)
    run = find_latest_run(session, now)
    run_dir = frame_key(run)
    out = output_dir / run_dir
    out.mkdir(parents=True, exist_ok=True)

    times = frame_times(run)
    earliest = times[0] - timedelta(hours=NEW_SNOW_WINDOW_HOURS)
    extra = [earliest + timedelta(hours=h) for h in range(NEW_SNOW_WINDOW_HOURS)]
    print(f"GFS run {run:%Y-%m-%d %HZ}: {len(times)} hourly frames "
          f"({times[0]:%m-%d %HZ} .. {times[-1]:%m-%d %HZ})")

    def fetch(t: datetime, names: list[str]):
        cycle, fhour = frame_source(t, run)
        return t, fetch_fields(session, cycle, fhour, names)

    # Oldest first: each frame's snow depth 24h earlier is in hand by the time it's written.
    # Only snow depth is kept around; the other fields are written and dropped.
    jobs = [(t, ["SNOD"]) for t in extra] + [(t, ["TMP", "SNOD", "WEASD"]) for t in times]
    snod: dict[datetime, np.ndarray] = {}
    frames = []
    with ThreadPoolExecutor(DOWNLOAD_WORKERS) as pool:
        for t, fields in pool.map(lambda job: fetch(*job), jobs):
            snod[t] = fields["SNOD"]
            if "TMP" not in fields:
                continue
            snod_earlier = snod.pop(t - timedelta(hours=NEW_SNOW_WINDOW_HOURS))
            paths = write_frame(out, t, derive_outputs(fields, snod_earlier))
            frames.append({"time": t.isoformat().replace("+00:00", "Z"), "files": paths})

    manifest = build_manifest(run, run_dir, frames)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    for old in output_dir.iterdir():
        if old.is_dir() and old.name != run_dir:
            shutil.rmtree(old)

    size_kb = sum(f.stat().st_size for f in out.iterdir()) // 1024
    print(f"Wrote {len(frames)} frames x {len(ENCODINGS)} fields to {out} ({size_kb} KB)")
    return manifest


def main_export(output_dir: Path) -> None:
    """CLI entry: export overlays, printing a short summary."""
    start = datetime.now(UTC)
    export_overlays(output_dir)
    print(f"Overlays done in {math.ceil((datetime.now(UTC) - start).total_seconds())}s")
