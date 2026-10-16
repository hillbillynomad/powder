"""Find stretches of a flyover that look at nothing.

usage: poetry run python tools/flyby/deadtime.py <slug> [--fetch] [--radius 350] [--min-s 4]

Samples the tour every 0.5 s, works out where the camera is looking on the ground (the same
aim the app uses: along the heading, pitch down to the authored ground height; orbit points
blend toward their target) and measures the distance to the nearest named run or lift line
(OpenStreetMap pistes via Overpass, cached in tools/flyby/cache/<slug>-pistes.json, plus the
harvested lifts). Any stretch longer than --min-s seconds where the aim is farther than
--radius metres from every one of them is reported as dead time. The overview approach and the
final pull-back are exempt: they deliberately look at the whole resort.
"""
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import features as F  # noqa: E402
import author_tour as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = F.CACHE


def fetch_pistes(slug, box):
    s, w, n, e = box[1], box[0], box[3], box[2]
    q = f'[out:json][timeout:60];way["piste:type"="downhill"]({s},{w},{n},{e});out tags geom;'
    out = os.path.join(CACHE, f'{slug}-pistes.json')
    subprocess.run(['curl', '-s', '--max-time', '90', '-A', 'powder-flyby-research/1.0 (personal project)',
                    '-H', 'Accept: application/json', '-X', 'POST', 'https://overpass-api.de/api/interpreter',
                    '--data-urlencode', f'data={q}', '-o', out], check=True)
    return out


def feature_points(slug):
    cache = json.load(open(os.path.join(CACHE, f'{slug}.json'), encoding='utf-8'))
    pts = []
    for l in cache['lifts']:
        c = l['coords']
        for a, b in zip(c, c[1:]):
            n = max(1, int(F.dist_m(a, b) // 60))
            pts += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n] for k in range(n + 1)]
    path = os.path.join(CACHE, f'{slug}-pistes.json')
    if os.path.exists(path):
        for e in json.load(open(path, encoding='utf-8')).get('elements', []):
            if not e.get('tags', {}).get('name'):
                continue
            g = e['geometry']
            for a, b in zip(g, g[1:]):
                n = max(1, int(F.dist_m([a['lon'], a['lat']], [b['lon'], b['lat']]) // 60))
                pts += [[a['lon'] + (b['lon'] - a['lon']) * k / n, a['lat'] + (b['lat'] - a['lat']) * k / n] for k in range(n + 1)]
    return pts


def sample(tour, t):
    pts = tour['points']
    n = len(pts)
    total = sum(p['seconds'] for p in pts)
    t %= total
    i = 0
    while t >= pts[i]['seconds'] and i < n - 1:
        t -= pts[i]['seconds']
        i += 1
    u = min(1.0, t / pts[i]['seconds'])
    ctrl = [pts[(i + k) % n] for k in (-1, 0, 1, 2)]
    cam = A.catmull(*[c['camera'] for c in ctrl], u)
    pitch = A.catmull(*[[c.get('pitch', A.DEFAULT_PITCH)] for c in ctrl], u)[0]
    ground = A.catmull(*[[c.get('ground', c['camera'][2] - 300)] for c in ctrl], u)[0]
    return i, u, cam, pitch, ground


def aim_at(tour, t):
    i, u, cam, pitch, ground = sample(tour, t)
    _, _, cam_a, _, _ = sample(tour, t - 2.5)
    _, _, cam_b, _, _ = sample(tour, t + 4.5)
    heading = A.bearing(cam_a, cam_b)
    drop = max(cam[2] - ground, 50)
    dist = max(300.0, drop / math.cos(math.radians(pitch)))
    ahead = dist * math.sin(math.radians(pitch))
    lng = cam[0] + ahead * math.sin(math.radians(heading)) / (111320 * math.cos(math.radians(cam[1])))
    lat = cam[1] + ahead * math.cos(math.radians(heading)) / 110540
    pts = tour['points']
    n = len(pts)
    w0 = 1.0 if pts[i].get('orbit') else 0.0
    w1 = 1.0 if pts[(i + 1) % n].get('orbit') else 0.0
    w = w0 + (w1 - w0) * u * u * (3 - 2 * u)
    if w > 0:
        tg = A.catmull(*[c.get('target', c['camera']) for c in [pts[(i + k) % n] for k in (-1, 0, 1, 2)]], u)
        lng += (tg[0] - lng) * w
        lat += (tg[1] - lat) * w
    return [lng, lat], cam


def main():
    slug = sys.argv[1]
    radius = float(sys.argv[sys.argv.index('--radius') + 1]) if '--radius' in sys.argv else 350.0
    min_s = float(sys.argv[sys.argv.index('--min-s') + 1]) if '--min-s' in sys.argv else 4.0
    tour = json.load(open(os.path.join(ROOT, 'powder/web/tours', f'{slug}.json'), encoding='utf-8'))
    if '--fetch' in sys.argv or not os.path.exists(os.path.join(CACHE, f'{slug}-pistes.json')):
        cache = json.load(open(os.path.join(CACHE, f'{slug}.json'), encoding='utf-8'))
        fetch_pistes(slug, F.footprint(cache['lifts'], 1500))
    feats = feature_points(slug)
    pts = tour['points']
    exempt_labels = ('Overview', 'Easing')
    total = sum(p['seconds'] for p in pts)
    # exempt the last leg: the pull-back to the overview
    starts, c = [], 0.0
    for p in pts:
        starts.append(c)
        c += p['seconds']
    pull_back_from = starts[-1]
    dead, run = [], None
    t = 0.0
    while t < total:
        i = sample(tour, t)[0]
        exempt = pts[i]['label'].startswith(exempt_labels) or t >= pull_back_from
        aim, cam = aim_at(tour, t)
        d = min(F.dist_m(aim, f) for f in feats)
        bad = d > radius and not exempt
        if bad:
            run = run or [t, t, d]
            run[1] = t
            run[2] = max(run[2], d)
        elif run:
            if run[1] - run[0] >= min_s:
                dead.append(run)
            run = None
        t += 0.5
    if run and run[1] - run[0] >= min_s:
        dead.append(run)
    off = sum(r[1] - r[0] for r in dead)
    print(f'{slug}: {total:.0f} s tour, {len(dead)} dead stretch(es) (> {min_s:.0f} s with aim > {radius:.0f} m from any run/lift), {off:.0f} s total')
    for a, b, d in dead:
        j = max(k for k, s in enumerate(starts) if s <= a)
        print(f'   {a:6.1f}-{b:6.1f} s  around "{pts[j]["label"][:44]}"  farthest {d:.0f} m')
    sys.exit(1 if dead else 0)


if __name__ == '__main__':
    main()
