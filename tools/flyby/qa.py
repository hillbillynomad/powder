"""Bounds check: a flyover must not wander away from the resort's lifts.

usage: poetry run python tools/flyby/qa.py [slug ...]   (default: every hand-crafted spec)

Samples the route every ~100 m along its waypoints (the overview approach and the closing
pull-back are exempt: they are meant to sit outside) and reports the farthest the camera strays
from the nearest lift line. Fails (exit 1) above MAX_OFF_M, or when any stretch of more than
~10 s is farther than WARN_OFF_M from every lift.
"""
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import features as F  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX_OFF_M = 900.0
WARN_OFF_M = 600.0


def lift_samples(lifts):
    out = []
    for l in lifts:
        c = l['coords']
        for a, b in zip(c, c[1:]):
            n = max(1, int(F.dist_m(a, b) // 100))
            out += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n] for k in range(n + 1)]
    return out


def check(slug):
    tour = json.load(open(os.path.join(ROOT, 'powder/web/tours', f'{slug}.json'), encoding='utf-8'))
    lifts = json.load(open(os.path.join(F.CACHE, f'{slug}.json'), encoding='utf-8'))['lifts']
    lifts_pts = lift_samples(lifts)
    pts = tour['points']
    # exempt the overview pair at the start and the final pull-back leg (last -> first)
    route = [p for p in pts if not p['label'].startswith(('Overview', 'Easing', 'Lining'))]
    worst = (0.0, None)
    far_seconds = 0.0
    for a, b, p in zip(route, route[1:], route):
        flat = F.dist_m(a['camera'], b['camera'])
        n = max(1, int(flat // 100))
        leg_far = 0
        for k in range(n + 1):
            q = [a['camera'][0] + (b['camera'][0] - a['camera'][0]) * k / n,
                 a['camera'][1] + (b['camera'][1] - a['camera'][1]) * k / n]
            d = min(F.dist_m(q, s) for s in lifts_pts)
            if d > worst[0]:
                worst = (d, f"{a['label'][:30]} -> {b['label'][:30]}")
            if d > WARN_OFF_M:
                leg_far += 1
        far_seconds += p['seconds'] * leg_far / (n + 1)
    return worst, far_seconds


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    slugs = sys.argv[1:] or sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(ROOT, 'tools/flyby/specs/*.json')))
    bad = 0
    for s in slugs:
        (d, where), far = check(s)
        flag = 'OUT OF BOUNDS' if d > MAX_OFF_M or far > 10 else 'ok'
        bad += flag != 'ok'
        print(f'{s:22} max {d:5.0f} m from a lift ({where}); {far:4.1f} s beyond {WARN_OFF_M:.0f} m  {flag}')
    sys.exit(1 if bad else 0)
