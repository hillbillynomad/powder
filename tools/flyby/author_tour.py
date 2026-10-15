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
     {label, camera: [lng, lat, metres AGL], pitch?} waypoints. Fly it like a bird: the camera
     faces the way it flies (tilted down by pitch, default 68), so plan a circuit with no
     backtracking - up from the base over famous runs, over the summit lodge, turn, and
     down another side past lifts and lodges to the base. Keep climbs under ~30 degrees
     (the printout shows climb and turn per leg). Adding "target": [lng, lat] to points
     switches to look-at mode; "seconds" per point instead of "speed_mps" times legs by hand.
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
EXAGGERATION = 1.4  # must match TERRAIN_EXAGGERATION in powder/web/js/app.js
DEFAULT_PITCH = 68.0  # must match DEFAULT_PITCH in powder/web/js/flyby.js
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


def leg_metres(a, b):
    """Horizontal and vertical metres between two [lng, lat, alt] points."""
    dx = (b[0] - a[0]) * 111320 * math.cos(math.radians(a[1]))
    dy = (b[1] - a[1]) * 110540
    return math.hypot(dx, dy), b[2] - a[2]


def bearing(a, b):
    dx = (b[0] - a[0]) * math.cos(math.radians(a[1]))
    return (math.degrees(math.atan2(dx, b[1] - a[1])) + 360) % 360


def build_tour(spec, verbose=True):
    """Turn a spec dict into a tour dict (heights, clearance, timing, ground aim heights)."""
    pts = []
    # Some points with a target and some without: bird flight with orbits (see flyby.js)
    has_t = [('target' in w) for w in spec['points']]
    mixed = any(has_t) and not all(has_t)
    for w in spec['points']:
        cam_lng, cam_lat, cam_agl = w['camera']
        cam_alt = elevation(cam_lng, cam_lat) + cam_agl
        point = {'camera': [cam_lng, cam_lat, cam_alt], 'seconds': w.get('seconds'), 'label': w.get('label', '')}
        if w.get('orbit') and 'target' not in w:
            sys.exit(f"{w.get('label')}: an orbit point needs a target")
        if 'target' in w:  # look-at mode
            tgt_lng, tgt_lat = w['target'][:2]
            tgt_alt = elevation(tgt_lng, tgt_lat) + (w['target'][2] if len(w['target']) > 2 else 0)
            dist, _ = leg_metres(point['camera'], [tgt_lng, tgt_lat, 0])
            point['camera'][2] = max(cam_alt, tgt_alt + dist / math.tan(math.radians(MAX_PITCH)))
            point['target'] = [tgt_lng, tgt_lat, tgt_alt]
            if mixed:
                point['orbit'] = 1
        elif 'pitch' in w:  # bird mode: optional per-point downward tilt
            point['pitch'] = w['pitch']
        pts.append(point)

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

    # A cruise speed in the spec sets each leg's time from its length (constant speed)
    n = len(pts)
    if spec.get('speed_mps'):
        for i, p in enumerate(pts):
            if p['seconds'] is not None:  # an explicit time (e.g. an orbit's pace) wins
                continue
            flat, rise = leg_metres(p['camera'], pts[(i + 1) % n]['camera'])
            p['seconds'] = round(max(spec.get('min_leg_s', 3.0), math.hypot(flat, rise) / spec['speed_mps']), 1)

    # Bird mode: record the ground height where each waypoint's line of sight meets the
    # (exaggerated) terrain. The app aims at a smooth blend of these instead of reading live
    # terrain, so the camera never jumps as terrain tiles load, yet the view centre stays on
    # the surface (which is what MapLibre uses to pick imagery tiles).
    for i, p in enumerate(pts):
        if 'target' in p and not mixed:
            continue
        prev, nxt = pts[i - 1]['camera'], pts[(i + 1) % n]['camera']
        heading = math.radians(bearing(prev, nxt))
        pitch = math.radians(p.get('pitch', DEFAULT_PITCH))
        cam = p['camera']
        ground = elevation(cam[0], cam[1])
        for step in range(1, 400):  # march the rendered-space ray 25 m at a time
            s = step * 25.0
            ahead = s * math.sin(pitch)
            lng = cam[0] + ahead * math.sin(heading) / (111320 * math.cos(math.radians(cam[1])))
            lat = cam[1] + ahead * math.cos(heading) / 110540
            ground = elevation(lng, lat)
            if cam[2] * EXAGGERATION - s * math.cos(pitch) <= ground * EXAGGERATION:
                break
        p['ground'] = round(ground)
        if mixed and 'target' not in p:  # bird points carry their aim so orbits can blend to it
            p['target'] = [round(lng, 5), round(lat, 5), round(ground)]

    for i, p in enumerate(pts):
        cam, nxt, prev = p['camera'], pts[(i + 1) % n]['camera'], pts[i - 1]['camera']
        flat, rise = leg_metres(cam, nxt)
        climb = math.degrees(math.atan2(rise, flat))
        turn = ((bearing(cam, nxt) - bearing(prev, cam) + 540) % 360) - 180
        agl = cam[2] - elevation(cam[0], cam[1])
        line = f"{p['label']:<34} {cam[2]:5.0f} m ({agl:4.0f} AGL)  leg {flat:5.0f} m, climb {climb:+5.1f} deg, turn {turn:+6.1f} deg"
        if 'target' in p:
            tgt = p['target']
            dist, _ = leg_metres(cam, tgt)
            line += f"  look pitch {90 - math.degrees(math.atan2(cam[2] - tgt[2], dist)):4.1f}"
            tgt[:] = [round(tgt[0], 5), round(tgt[1], 5), round(tgt[2])]
        if verbose:
            print(line)
        cam[:] = [round(cam[0], 5), round(cam[1], 5), round(cam[2])]

    tour = {'resort': spec['resort'], 'version': 1, 'units': 'metres above sea level (real, unexaggerated)',
            'points': pts}
    return tour


def main(spec_path, out_path):
    spec = json.load(open(spec_path, encoding='utf-8'))
    tour = build_tour(spec)
    with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(tour, f, indent=1)
    print('total', round(sum(p['seconds'] for p in tour['points']), 1), 's ->', out_path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
