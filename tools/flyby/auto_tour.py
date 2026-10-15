"""Generate flyover tours for every resort.

Hand-crafted specs (tools/flyby/specs/<slug>.json) always win. Every other resort gets an
automatic route planned from its harvested lifts (tools/flyby/cache, see harvest.cjs):

  lift route    a "racetrack" that flies up alongside the biggest-vertical lift, crosses the
                top, and comes back down alongside a second lift when one is on the right side
                (otherwise down a parallel line), so every frame overlooks lifts and runs
  orbit         resorts with no usable lifts in the map data: a slow circle around the
                highest point near the resort (look-at mode)

Usage:
    poetry run python tools/flyby/auto_tour.py                # all resorts -> powder/web/tours
    poetry run python tools/flyby/auto_tour.py snowbird zermatt   # only these (index updated too)
"""
import hashlib
import json
import math
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)

import lifts as lift_model  # noqa: E402
from author_tour import build_tour, elevation  # noqa: E402

TOURS_DIR = os.path.join(ROOT, 'powder', 'web', 'tours')
HAND_SPECS = os.path.join(HERE, 'specs')
PICKS = os.path.join(HERE, 'picks.json')
AUTO_SPECS = os.path.join(HERE, 'specs', 'auto')
SPEED = 132.0  # m/s, 1.25x the original tour speed
MIN_VERTICAL = 120  # m: smaller lifts (carpets, rope tows, tile slivers) aren't worth a flyover
MIN_LENGTH = 400
RUN_LIMITS = (1700, 1300, 1000)  # metres of the main lift to fly, shortened until it fits
MAX_SECONDS = 46.0
HARD_MAX_SECONDS = 56.0  # accept the shortest route up to this rather than fall back to an orbit
CLOSE_M = 1800.0  # preferred: lifts this close to the resort marker
NEAR_M = 3000.0  # next best; further than this is probably a neighbouring resort
ORBIT_RADIUS = 750.0  # m
MIN_ORBIT_RELIEF = 250.0  # m of relief within 1.8 km, else the resort gets no orbit
M_LAT = 110540.0


def slugify(name):
    """Same as slugify() in powder/web/js/flyby.js."""
    text = unicodedata.normalize('NFD', str(name or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


# ---- local flat-earth helpers (metres east / north of a reference point) -----------------

def to_xy(ref, pt):
    return ((pt[0] - ref[0]) * 111320 * math.cos(math.radians(ref[1])), (pt[1] - ref[1]) * M_LAT)


def from_xy(ref, xy):
    return [ref[0] + xy[0] / (111320 * math.cos(math.radians(ref[1]))), ref[1] + xy[1] / M_LAT]


def unit(v):
    n = math.hypot(*v) or 1.0
    return (v[0] / n, v[1] / n)


def add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k)


# ---- planners --------------------------------------------------------------------------

def find_lift(info, name):
    """Biggest lift whose name contains `name` (case-insensitive); None when absent."""
    want = unicodedata.normalize('NFKD', name).lower()
    hits = [l for l in info['lifts'] if l['name'] and want in unicodedata.normalize('NFKD', l['name']).lower()]
    return max(hits, key=lambda l: l['vertical']) if hits else None


def plan_lift_route(info, run_limit, pick=None):
    """Spec dict for a racetrack along the best lift, or None when the data has no lift.

    `pick` (from picks.json) names the lifts to fly: {"up": "Gondola One", "down": "Born Free",
    "run_limit": 2000, "side": 1}."""
    pick = pick or {}
    cands = [l for l in info['lifts'] if l['vertical'] >= MIN_VERTICAL and l['length'] >= MIN_LENGTH]
    if not cands:
        return None
    center = info['center']

    def away_m(l):
        mid = ((l['top'][0] + l['bottom'][0]) / 2, (l['top'][1] + l['bottom'][1]) / 2)
        return math.hypot(*to_xy(center, mid))

    # The resort's own lifts first: a neighbour's bigger lift only if it has none of its own
    for radius in (CLOSE_M, NEAR_M):
        near = [l for l in cands if away_m(l) <= radius]
        if near:
            cands = near
            break

    def score(l):
        # Big vertical wins, but a lift far from the resort's marker is probably a remote
        # side of the area: every 10 m away costs 1 m of vertical
        mid = ((l['top'][0] + l['bottom'][0]) / 2, (l['top'][1] + l['bottom'][1]) / 2)
        away = math.hypot(*to_xy(center, mid))
        return l['vertical'] + min(l['length'], 1500) * 0.1 - away * 0.1

    cands = sorted(cands, key=score, reverse=True)
    main = find_lift(info, pick['up']) if pick.get('up') else None
    if main is None:
        main = cands[0]
    forced_down = find_lift(info, pick['down']) if pick.get('down') else None
    run_limit = pick.get('run_limit', run_limit)
    ref = main['top']
    top = (0.0, 0.0)
    bottom = to_xy(ref, main['bottom'])
    u = unit((top[0] - bottom[0], top[1] - bottom[1]))
    run = math.hypot(*bottom)
    if run > run_limit:
        bottom = (-u[0] * run_limit, -u[1] * run_limit)
    mid = ((bottom[0] + top[0]) / 2, (bottom[1] + top[1]) / 2)

    # A second lift to fly back down: similar direction, top near ours, sitting off to a side
    best = None
    for l in ([forced_down] if forced_down else cands):
        if l is main:
            continue
        t, b = to_xy(ref, l['top']), to_xy(ref, l['bottom'])
        v = unit((t[0] - b[0], t[1] - b[1]))
        lmid = ((t[0] + b[0]) / 2, (t[1] + b[1]) / 2)
        offset = (lmid[0] - mid[0]) * -u[1] + (lmid[1] - mid[1]) * u[0]  # signed, left positive
        if not forced_down:
            if u[0] * v[0] + u[1] * v[1] < 0.3 or math.hypot(*t) > 1500:
                continue
            if abs(offset) < 250 or abs(offset) > 1000:
                continue
        if best is None or l['vertical'] > best[0]['vertical']:
            best = (l, t, b, v, offset)

    if best:
        l, t, b, v, offset = best
        side_sign = 1 if offset > 0 else -1
        # Fly the second lift top -> bottom, a touch past each end so its stations show
        if math.hypot(t[0] - b[0], t[1] - b[1]) > run_limit:  # fly only the top stretch
            b = add(t, v, -run_limit)
        r1 = add(t, v, 60)
        r2 = ((t[0] + b[0]) / 2, (t[1] + b[1]) / 2)
        r3 = add(b, v, -150)
        kind = f"lift route: {main['name'] or 'main lift'} up, {l['name'] or 'second lift'} down"
    else:
        side_sign = pick.get('side', 1)
        side = (-u[1] * side_sign, u[0] * side_sign)
        r1 = add(add(top, u, 100), side, 650)
        r2 = add(mid, side, 650)
        r3 = add(add(bottom, u, -150), side, 650)
        kind = f"lift route: {main['name'] or 'main lift'}, parallel return"

    side = (-u[1] * side_sign, u[0] * side_sign)
    start = add(add(bottom, u, -260), side, 60)
    m1 = add(mid, side, -100)
    crest = add(top, u, 140)

    def pt(label, xy, agl, pitch):
        lng, lat = from_xy(ref, xy)
        return {'label': label, 'camera': [round(lng, 5), round(lat, 5), agl], 'pitch': pitch}

    return {
        'resort': info['raw']['resort'], 'speed_mps': SPEED, 'kind': kind,
        'points': [
            pt('Base, lift line ahead', start, 340, 52),
            pt('Up the lift line', m1, 520, 48),
            pt('Over the top', crest, 460, 54),
            pt('Across the top', r1, 420, 56),
            pt('Down the run', r2, 330, 60),
            pt('Back toward the base', r3, 300, 64),
        ],
    }


def highest_point(center, half=1800.0, step=120.0):
    """(point, relief_m): the highest DEM point near `center` and the height range around it."""
    best = (-1e9, center)
    low = 1e9
    n = int(half // step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            p = from_xy(center, (i * step, j * step))
            e = elevation(*p)
            low = min(low, e)
            if e > best[0]:
                best = (e, p)
    return best[1], best[0] - low


def plan_orbit(resort):
    center = [resort['longitude'], resort['latitude']]
    peak, relief = highest_point(center)
    if relief < MIN_ORBIT_RELIEF:
        return None  # flat ground (the marker is a town): no flyover beats a dull one
    pts = []
    for k in range(6):
        a = math.radians(k * 60)
        lng, lat = from_xy(peak, (math.sin(a) * ORBIT_RADIUS, math.cos(a) * ORBIT_RADIUS))
        pts.append({'label': f'Orbit {k * 60} deg', 'camera': [round(lng, 5), round(lat, 5), 420],
                    'target': [round(peak[0], 5), round(peak[1], 5), 0]})
    return {'resort': resort['name'], 'speed_mps': SPEED, 'kind': 'orbit around the highest point', 'points': pts}


# ---- driver ----------------------------------------------------------------------------

def duration(tour):
    return sum(p['seconds'] for p in tour['points'])


def load_picks():
    if not os.path.exists(PICKS):
        return {}
    return json.load(open(PICKS, encoding='utf-8'))


def make_tour(resort, picks=None):
    """(tour, kind) for one resort: hand spec if present, else a lift route, else an orbit."""
    slug = slugify(resort['name'])
    pick = (picks or {}).get(slug)
    hand = os.path.join(HAND_SPECS, f'{slug}.json')
    if os.path.exists(hand):
        spec = json.load(open(hand, encoding='utf-8'))
        return build_tour(spec, verbose=False), 'hand-crafted'

    info = lift_model.build(slug)
    if info is not None:
        best = None
        for limit in RUN_LIMITS:
            spec = plan_lift_route(info, limit, pick)
            if spec is None:
                break
            tour = build_tour(spec, verbose=False)
            if duration(tour) <= MAX_SECONDS or (pick and pick.get('run_limit')):
                return tour, ('curated ' if pick else '') + spec['kind']
            if best is None or duration(tour) < duration(best[0]):
                best = (tour, spec['kind'])
        if best and duration(best[0]) <= HARD_MAX_SECONDS:
            return best[0], ('curated ' if pick else '') + best[1]
    spec = plan_orbit(resort)
    if spec is None:
        return None, 'none (no lifts in the map data and flat terrain)'
    return build_tour(spec, verbose=False), spec['kind']


def write_tour(slug, tour):
    os.makedirs(TOURS_DIR, exist_ok=True)
    with open(os.path.join(TOURS_DIR, f'{slug}.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(tour, f, indent=1)
        f.write('\n')


def write_index():
    slugs = sorted(f[:-5] for f in os.listdir(TOURS_DIR) if f.endswith('.json') and f != 'index.json')
    # Content hash per tour: the web app requests tours/<slug>.json?v=<hash>, so an edited tour
    # is a new URL and no HTTP / service-worker cache can serve the old route
    versions = {}
    for slug in slugs:
        with open(os.path.join(TOURS_DIR, f'{slug}.json'), 'rb') as t:
            versions[slug] = hashlib.sha1(t.read()).hexdigest()[:8]
    with open(os.path.join(TOURS_DIR, 'index.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'tours': slugs, 'versions': versions}, f, indent=1)
        f.write('\n')
    return slugs


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raw = json.load(open(os.path.join(ROOT, 'powder', 'data', 'resorts.json'), encoding='utf-8'))
    resorts = raw.get('resorts', raw)
    only = set(argv)
    picks = load_picks()
    seen = {}
    summary = []
    for r in resorts:
        slug = slugify(r['name'])
        if slug in seen:
            sys.exit(f"slug collision: {r['name']!r} and {seen[slug]!r} -> {slug}")
        seen[slug] = r['name']
        if only and slug not in only:
            continue
        try:
            tour, kind = make_tour(r, picks)
        except Exception as e:  # never let one resort stop the batch: fall back to an orbit
            print(f'  {slug}: route failed ({e}); using orbit')
            orbit = plan_orbit(r)
            tour, kind = (build_tour(orbit, verbose=False), 'orbit (after error)') if orbit else (None, 'none')
        stale = os.path.join(TOURS_DIR, f'{slug}.json')
        if tour is None:
            if os.path.exists(stale):
                os.remove(stale)
            summary.append((slug, kind, 0))
            print(f'{slug:<42}   -    {kind}')
            continue
        write_tour(slug, tour)
        summary.append((slug, kind, round(duration(tour), 1)))
        print(f'{slug:<42} {duration(tour):5.1f} s  {kind}')
    slugs = write_index()
    kinds = {}
    for _, k, _ in summary:
        key = ('hand-crafted' if k == 'hand-crafted' else 'no tour' if k.startswith('none')
               else 'orbit' if k.startswith('orbit')
               else 'curated lift route' if k.startswith('curated') else 'lift route')
        kinds[key] = kinds.get(key, 0) + 1
    secs = [s for _, _, s in summary if s]
    print(json.dumps({'tours_written': len(summary), 'index_size': len(slugs), 'by_kind': kinds,
                      'seconds_min': min(secs, default=0), 'seconds_max': max(secs, default=0)}))


if __name__ == '__main__':
    main(sys.argv[1:])
