"""Find the dramatic parts of a resort a flyover should not skip.

usage: poetry run python tools/flyby/features.py <slug> [slug ...]

For each resort (lifts/peaks from tools/flyby/cache/<slug>.json, heights from the same DEM the
app renders) it ranks:
  - `top`    the highest lift terminals (distinct sites): the summits people actually ski from
  - `steep`  clusters of >= STEEP_DEG slopes (cliffs, couloirs, headwalls) by slope x relief,
             with the cluster's long-axis bearing so a route can fly along the crest
  - `peak`   named peaks inside the resort footprint
and prints a suggested required-destination list: every distinct top terminal among the best
few, plus the strongest steep clusters. A route generator treats these as must-visit nodes (the
camera passes ~300 m above them, tilted to see the drop) and orders them with the lifts.
"""
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(__file__))
from author_tour import elevation  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), 'cache')
STEEP_DEG = 38.0
CELL_M = 40.0
MIN_SITE_SEP_M = 450.0


def metres_per_deg(lat):
    return 111320 * math.cos(math.radians(lat)), 110540


def dist_m(a, b):
    mx, my = metres_per_deg(a[1])
    return math.hypot((a[0] - b[0]) * mx, (a[1] - b[1]) * my)


def footprint(lifts, buffer_m=600):
    pts = [p for l in lifts for p in l['coords']]
    lat = statistics.mean(p[1] for p in pts)
    mx, my = metres_per_deg(lat)
    return (min(p[0] for p in pts) - buffer_m / mx, min(p[1] for p in pts) - buffer_m / my,
            max(p[0] for p in pts) + buffer_m / mx, max(p[1] for p in pts) + buffer_m / my)


def near_lift(p, lifts, within_m):
    return any(dist_m(p, c) <= within_m for l in lifts for c in l['coords'])


def lift_tops(lifts):
    ends = []
    for l in lifts:
        for c in (l['coords'][0], l['coords'][-1]):
            ends.append((elevation(c[0], c[1]), c))
    ends.sort(reverse=True)
    sites = []
    for ele, c in ends:
        if all(dist_m(c, s['at']) > MIN_SITE_SEP_M for s in sites):
            sites.append({'kind': 'top', 'at': [round(c[0], 5), round(c[1], 5)], 'ground': round(ele)})
    return sites


def steep_clusters(box, lifts):
    lng0, lat0, lng1, lat1 = box
    mx, my = metres_per_deg((lat0 + lat1) / 2)
    dx, dy = CELL_M / mx, CELL_M / my
    nx, ny = int((lng1 - lng0) / dx), int((lat1 - lat0) / dy)
    ele = [[elevation(lng0 + i * dx, lat0 + j * dy) for i in range(nx)] for j in range(ny)]
    steep = {}
    for j in range(1, ny - 1):
        for i in range(1, nx - 1):
            gx = (ele[j][i + 1] - ele[j][i - 1]) / (2 * CELL_M)
            gy = (ele[j + 1][i] - ele[j - 1][i]) / (2 * CELL_M)
            deg = math.degrees(math.atan(math.hypot(gx, gy)))
            if deg >= STEEP_DEG:
                steep[(i, j)] = deg
    seen, clusters = set(), []
    for start in steep:
        if start in seen:
            continue
        stack, cells = [start], []
        seen.add(start)
        while stack:
            c = stack.pop()
            cells.append(c)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    n = (c[0] + di, c[1] + dj)
                    if n in steep and n not in seen:
                        seen.add(n)
                        stack.append(n)
        if len(cells) < 25:  # ~40,000 m2: ignore specks
            continue
        es = [ele[j][i] for i, j in cells]
        top = max(cells, key=lambda c: ele[c[1]][c[0]])
        relief = max(es) - min(es)
        mean_deg = statistics.mean(steep[c] for c in cells)
        cx = statistics.mean(c[0] for c in cells)
        cy = statistics.mean(c[1] for c in cells)
        # long axis of the cluster from its second moments (bearing of the crest)
        sxx = statistics.mean((c[0] - cx) ** 2 for c in cells)
        syy = statistics.mean((c[1] - cy) ** 2 for c in cells)
        sxy = statistics.mean((c[0] - cx) * (c[1] - cy) for c in cells)
        theta = 0.5 * math.atan2(2 * sxy, sxx - syy)  # from +x (east) toward +y (north)
        axis = (90 - math.degrees(theta)) % 180
        at = [lng0 + cx * dx, lat0 + cy * dy]
        clusters.append({
            'kind': 'steep', 'at': [round(at[0], 5), round(at[1], 5)], 'ground': round(ele[top[1]][top[0]]),
            'crest': [round(lng0 + top[0] * dx, 5), round(lat0 + top[1] * dy, 5)],
            'relief_m': round(relief), 'mean_deg': round(mean_deg, 1), 'cells': len(cells),
            'axis_bearing': round(axis), 'score': round(mean_deg * math.sqrt(len(cells)) * relief / 100, 1),
            'by_lift': near_lift(at, lifts, 800),
        })
    return sorted(clusters, key=lambda c: -c['score'])


def analyse(slug):
    data = json.load(open(os.path.join(CACHE, f'{slug}.json'), encoding='utf-8'))
    lifts = data['lifts']
    box = footprint(lifts)
    tops = lift_tops(lifts)
    steep = [c for c in steep_clusters(box, lifts) if c['by_lift']]
    peaks = [{'kind': 'peak', 'name': p['name'], 'at': p['coord'], 'ground': p['ele']} for p in data.get('peaks', [])
             if box[0] <= p['coord'][0] <= box[2] and box[1] <= p['coord'][1] <= box[3]]
    required = tops[:3] + steep[:2]
    return {'slug': slug, 'tops': tops[:6], 'steep': steep[:6], 'peaks': peaks, 'required': required}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    for slug in sys.argv[1:]:
        r = analyse(slug)
        print(f"== {slug}")
        for t in r['tops']:
            print('  top  ', t['at'], t['ground'], 'm')
        for s in r['steep']:
            print('  steep', s['at'], f"crest {s['crest']} {s['ground']} m", f"relief {s['relief_m']} m, {s['mean_deg']} deg, axis {s['axis_bearing']} deg, score {s['score']}")
        for p in r['peaks']:
            print('  peak ', p['name'], p['at'], p['ground'], 'm')
