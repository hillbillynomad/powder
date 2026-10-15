"""Lift model built from the harvested vector-tile cache (tools/flyby/cache/<slug>.json).

Tiles clip aerialway lines at their edges, so a real lift arrives as several fragments. We
stitch fragments whose end points touch, orient each lift bottom -> top using the DEM, and give
it a name from the nearest named piece. Everything is in [lng, lat] with metres via local
flat-earth maths, which is plenty at resort scale.
"""
import json
import math
import os

from author_tour import elevation

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'cache')
JOIN_M = 15.0  # collinear pieces with a gap under this are the same lift


def metres(a, b):
    dx = (b[0] - a[0]) * 111320 * math.cos(math.radians((a[1] + b[1]) / 2))
    dy = (b[1] - a[1]) * 110540
    return math.hypot(dx, dy)


def length(coords):
    return sum(metres(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def load(slug):
    path = os.path.join(CACHE, f'{slug}.json')
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding='utf-8'))


def _axis(coords):
    """Unit vector (east, north metres) from first to last point, and the line length."""
    a, b = coords[0], coords[-1]
    dx = (b[0] - a[0]) * 111320 * math.cos(math.radians(a[1]))
    dy = (b[1] - a[1]) * 110540
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n, n


def _project(origin, axis, pt):
    """(along, across) metres of pt relative to origin along the given axis."""
    dx = (pt[0] - origin[0]) * 111320 * math.cos(math.radians(origin[1]))
    dy = (pt[1] - origin[1]) * 110540
    return dx * axis[0] + dy * axis[1], -dx * axis[1] + dy * axis[0]


def _try_merge(a, b):
    """Merge two near-collinear, overlapping or touching pieces; None if they are different
    lifts. Tiles on different grids cut the same lift at different places, so the pieces
    overlap; lifts that merely meet at a station run in other directions and stay apart."""
    ax, ay, an = _axis(a)
    bx, by, bn = _axis(b)
    if an < 5 or bn < 5:
        return None
    if abs(ax * bx + ay * by) < math.cos(math.radians(8)):
        return None
    origin = a[0]
    axis = (ax, ay)
    pts = a + b
    along = [_project(origin, axis, p) for p in pts]
    if any(abs(across) > 18 for _, across in along):
        return None
    ia = [_project(origin, axis, p)[0] for p in (a[0], a[-1])]
    ib = [_project(origin, axis, p)[0] for p in (b[0], b[-1])]
    lo_a, hi_a, lo_b, hi_b = min(ia), max(ia), min(ib), max(ib)
    if lo_b > hi_a + JOIN_M or lo_a > hi_b + JOIN_M:
        return None  # a gap: separate lifts in a row, leave them
    order = sorted(range(len(pts)), key=lambda k: along[k][0])
    merged = [pts[k] for k in order]
    out = [merged[0]]
    for p in merged[1:]:
        if metres(out[-1], p) > 1.0:
            out.append(p)
    return out


def _stitch(fragments):
    lines = [list(f) for f in fragments if len(f) >= 2]
    changed = True
    while changed:
        changed = False
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                m = _try_merge(lines[i], lines[j])
                if m:
                    lines[i] = m
                    del lines[j]
                    changed = True
                    break
            if changed:
                break
    return lines


def build(slug):
    """Return {'center': [lng, lat], 'lifts': [...], 'raw': cache} or None without a cache."""
    d = load(slug)
    if d is None:
        return None
    frags = [l['coords'] for l in d['lifts']]
    # Named pieces are separate (also tile-clipped) polylines: they make fragments too
    frags += [n['coords'] for n in d['liftNames']]
    lines = _stitch(frags)

    lifts = []
    for coords in lines:
        a, b = coords[0], coords[-1]
        ea, eb = elevation(*a), elevation(*b)
        if ea > eb:  # bottom first
            coords, ea, eb = coords[::-1], eb, ea
        mid = coords[len(coords) // 2]
        name, best = None, 150.0
        for n in d['liftNames']:
            for c in n['coords']:
                dist = metres(c, mid)
                if dist < best:
                    best, name = dist, n['name']
        lifts.append({
            'name': name, 'coords': coords, 'bottom': coords[0], 'top': coords[-1],
            'bottom_ele': round(ea), 'top_ele': round(eb), 'vertical': round(eb - ea),
            'length': round(length(coords)),
        })
    # De-duplicate near-identical lifts (same piece harvested from both layers)
    unique = []
    for l in sorted(lifts, key=lambda x: -x['length']):
        if not any(metres(l['bottom'], u['bottom']) < 80 and metres(l['top'], u['top']) < 200 for u in unique):
            unique.append(l)
    # Tiny fragments (gondola towers, tile slivers) are not worth flying along
    unique = [u for u in unique if u['length'] >= 250]
    unique.sort(key=lambda x: -x['vertical'])
    return {'center': [d['longitude'], d['latitude']], 'lifts': unique, 'raw': d}


if __name__ == '__main__':
    import sys
    info = build(sys.argv[1])
    for l in info['lifts']:
        print(f"{(l['name'] or '?'):<24} vert {l['vertical']:5d} m  len {l['length']:5d} m  "
              f"bottom {l['bottom']} ({l['bottom_ele']} m)  top {l['top']} ({l['top_ele']} m)")
