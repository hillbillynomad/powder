"""Author a resort flyover tour.

Waypoints are hand-placed (camera position + look-at target). Heights are given as metres
above ground (AGL) and resolved against the same AWS Terrarium DEM the app renders, then the
closed Catmull-Rom path the browser will fly is sampled to make sure it never dips below a
minimum clearance. Output: real metres above sea level (the app multiplies by its terrain
exaggeration at runtime).

Workflow for a new resort:
  1. Find its lifts: serve powder/web, then
       node tools/flyby/extract_lifts.cjs tests/web/node_modules/playwright             "http://localhost:8000/" <lng> <lat> lifts.json
     (reads the same OpenFreeMap lift lines and names the app draws).
  2. Write tools/flyby/specs/<slug>.json: {"resort", "speed_mps", "points": [...]}, a loop of
     {label, camera: [lng, lat, metres AGL], target: [lng, lat]} waypoints. Aim for ~30 s at
     ~130 m/s (about 4 km): sweep across the face of the mountain looking into it, so the
     heading barely changes, and point the targets at the famous runs, lifts and lodges.
     ("seconds" per point instead of "speed_mps" times legs by hand.)
  3. poetry run python tools/flyby/author_tour.py tools/flyby/specs/<slug>.json powder/web/tours/<slug>.json
     and add <slug> to powder/web/tours/index.json.
"""
import json
import math
import os
import sys
import urllib.request

from PIL import Image

Z = 13
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dem-cache')
MIN_CLEARANCE = 150.0  # metres, camera above ground anywhere along the path
MAX_PITCH = 75.0  # degrees from straight down; flatter than this shows mostly sky
_tiles = {}


def tile(x, y):
    key = (x, y)
    if key not in _tiles:
        os.makedirs(CACHE, exist_ok=True)
        path = os.path.join(CACHE, f'{Z}-{x}-{y}.png')
        if not os.path.exists(path):
            url = f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png'
            with urllib.request.urlopen(url, timeout=30) as r:
                open(path, 'wb').write(r.read())
        _tiles[key] = Image.open(path).convert('RGB').load()
    return _tiles[key]


def elevation(lng, lat):
    n = 2 ** Z
    fx = (lng + 180) / 360 * n * 256
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256

    def px(ix, iy):
        r, g, b = tile(ix // 256, iy // 256)[ix % 256, iy % 256]
        return r * 256 + g + b / 256 - 32768

    x0, y0 = int(fx), int(fy)
    tx, ty = fx - x0, fy - y0
    top = px(x0, y0) * (1 - tx) + px(x0 + 1, y0) * tx
    bot = px(x0, y0 + 1) * (1 - tx) + px(x0 + 1, y0 + 1) * tx
    return top * (1 - ty) + bot * ty


def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return [0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
            for a, b, c, d in zip(p0, p1, p2, p3)]


def main(spec_path, out_path):
    spec = json.load(open(spec_path))
    pts = []
    for w in spec['points']:
        cam_lng, cam_lat, cam_agl = w['camera']
        tgt_lng, tgt_lat = w['target'][:2]
        tgt_agl = w['target'][2] if len(w['target']) > 2 else 0
        cam_ground = elevation(cam_lng, cam_lat)
        tgt_alt = elevation(tgt_lng, tgt_lat) + tgt_agl
        cam_alt = cam_ground + cam_agl
        dist = math.hypot((tgt_lng - cam_lng) * 111320 * math.cos(math.radians(cam_lat)), (tgt_lat - cam_lat) * 110540)
        cam_alt = max(cam_alt, tgt_alt + dist / math.tan(math.radians(MAX_PITCH)))
        pts.append({'camera': [cam_lng, cam_lat, cam_alt], 'target': [tgt_lng, tgt_lat, tgt_alt],
                    'seconds': w.get('seconds'), 'label': w.get('label', '')})

    # Lift any waypoint whose neighbouring path segment scrapes the ground, until clear
    for _ in range(20):
        worst = None
        n = len(pts)
        for i in range(n):
            ctrl = [pts[(i + k) % n]['camera'] for k in (-1, 0, 1, 2)]
            for s in range(1, 40):
                lng, lat, alt = catmull(*ctrl, s / 40)
                clearance = alt - elevation(lng, lat)
                if clearance < MIN_CLEARANCE and (worst is None or clearance < worst[0]):
                    worst = (clearance, i, s / 40)
        if not worst:
            break
        clearance, i, t = worst
        bump = MIN_CLEARANCE - clearance + 20
        for j in (i, (i + 1) % n):  # raise both ends of the offending segment
            pts[j]['camera'][2] += bump * (1 - t if j == i else t) + 10
    else:
        sys.exit('could not clear terrain')

    # A cruise speed in the spec sets each leg's time from its length (constant ground speed)
    if spec.get('speed_mps'):
        n = len(pts)
        for i, p in enumerate(pts):
            a, b = p['camera'], pts[(i + 1) % n]['camera']
            leg = math.hypot((b[0] - a[0]) * 111320 * math.cos(math.radians(a[1])), (b[1] - a[1]) * 110540, b[2] - a[2])
            p['seconds'] = round(max(3.0, leg / spec['speed_mps']), 1)

    for p in pts:
        cam, tgt = p['camera'], p['target']
        ground = math.hypot((tgt[0] - cam[0]) * 111320 * math.cos(math.radians(cam[1])), (tgt[1] - cam[1]) * 110540)
        pitch = 90 - math.degrees(math.atan2(cam[2] - tgt[2], ground))
        agl = cam[2] - elevation(cam[0], cam[1])
        print(f"{p['label']:<28} cam {cam[2]:6.0f} m ({agl:4.0f} AGL)  target {tgt[2]:6.0f} m  pitch {pitch:4.1f}  dist {ground:5.0f} m")
        cam[:] = [round(cam[0], 5), round(cam[1], 5), round(cam[2])]
        tgt[:] = [round(tgt[0], 5), round(tgt[1], 5), round(tgt[2])]

    tour = {'resort': spec['resort'], 'version': 1, 'units': 'metres above sea level (real, unexaggerated)',
            'points': pts}
    json.dump(tour, open(out_path, 'w', encoding='utf-8', newline='\n'), indent=1)
    print('total', sum(p['seconds'] for p in pts), 's ->', out_path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
