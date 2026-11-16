"""Terrain the weather models can't see, from the free AWS Terrarium DEM tiles the web map uses.

    poetry run python tools/calibrate/terrain.py      # caches tools/calibrate/.cache/terrain.json

For each resort, samples the DEM on a 21 x 21 grid over +/-R km for a few radii and stores
mean / max / min / std (feet).
"""

import io
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hindcast  # noqa: E402

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 10
RADII_KM = (5, 15, 30)
N = 21
OUT = hindcast.CACHE / "terrain.json"


@lru_cache(maxsize=None)
def tile(x: int, y: int) -> np.ndarray:
    resp = requests.get(TILE_URL.format(z=ZOOM, x=x, y=y), timeout=30)
    resp.raise_for_status()
    a = np.asarray(Image.open(io.BytesIO(resp.content)).convert("RGB"), dtype=np.float64)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


def elevation_ft(lat: float, lon: float) -> float:
    n = 2 ** ZOOM
    fx = (lon + 180) / 360 * n
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    x, y = int(fx), int(fy)
    px, py = min(int((fx - x) * 256), 255), min(int((fy - y) * 256), 255)
    return float(tile(x, y)[py, px]) * 3.28084


def summarize(lat: float, lon: float, radius_km: float) -> dict:
    vals = []
    for i in range(N):
        for j in range(N):
            dy = (i / (N - 1) * 2 - 1) * radius_km
            dx = (j / (N - 1) * 2 - 1) * radius_km
            vals.append(elevation_ft(lat + dy / 111.32, lon + dx / (111.32 * math.cos(math.radians(lat)))))
    v = np.array(vals)
    return {"mean": v.mean(), "max": v.max(), "min": v.min(), "std": v.std()}


def load() -> dict:
    return json.loads(OUT.read_text()) if OUT.exists() else {}


def main():
    data = load()
    for r in hindcast.resorts():
        if r.name not in data:
            data[r.name] = {f"r{k}": summarize(r.latitude, r.longitude, k) for k in RADII_KM}
    OUT.write_text(json.dumps(data))
    for name, d in data.items():
        print(f"{name:26s} " + "  ".join(f"{k}: mean {s['mean']:5.0f} std {s['std']:5.0f}" for k, s in d.items()))


if __name__ == "__main__":
    main()
