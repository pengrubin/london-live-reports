#!/usr/bin/env python3
"""Offline re-match of displayed diversion events against archived TfL road
disruption snapshots (sections 7.6 and 7.8).

The transition log does not record the live matcher's result, so it is
re-derived here. The live matcher takes the midpoint of every drawn band
segment and looks for a TfL road disruption within 250 m. The log keeps only
the event centroid and its route names, so this script approximates a band
by the learned polylines of the event's routes within SITE_R of the centroid,
and measures each candidate disruption's distance to the nearest vertex of
those polylines (vertices are 25 m apart, so the error is under 13 m).

Validity: a disruption counts if its start/end window contains the event's
first display time (1 h slack). Snapshots are ~6 h apart; the nearest one is
used and the gap is recorded.

Input : data/diversion-events.csv, data/learned/<snapshot>/routes/*.json,
        <archive>/road-disruptions/*.jsonl
Output: data/tfl-match.csv, numbers into numbers.json, fig-7-3.
"""
import csv, json, glob, os, sys, math, bisect, datetime as dt
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
A = sys.argv[1] if len(sys.argv) > 1 else '/Volumes/大龟壳/bus-archive'
MATCH_M = 250; SITE_R = 1500; SLACK_S = 3600
M_LAT = 110_540.0; M_LON = 111_320.0 * math.cos(math.radians(51.5))
def d_m(lon1, lat1, lon2, lat2): return math.hypot((lon2 - lon1) * M_LON, (lat2 - lat1) * M_LAT)

# learned polylines by route name (all operators, both directions)
snap = sorted(glob.glob(os.path.join(DATA, 'learned', '*')))[-1]
by_route = defaultdict(list)
for f in glob.glob(os.path.join(snap, 'routes', '*.json')):
    d = json.load(open(f)); parts = d.get('key', '').split(':')
    if len(parts) == 3: by_route[parts[1]].append(d['poly'])

snaps = []
def ep(s):
    try: return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
    except Exception: return None
for path in sorted(glob.glob(os.path.join(A, 'road-disruptions', '*.jsonl'))):
    for line in open(path):
        try: r = json.loads(line)
        except Exception: continue
        items = []
        for d in r.get('disruptions', []):
            try: lon, lat = json.loads(d['pt'])
            except Exception: continue
            items.append((lon, lat, ep(d.get('start') or '') or 0, ep(d.get('end') or '') or 4e9, d.get('cat'), d.get('sev'), d.get('id')))
        snaps.append((r['t'], items))
snaps.sort(); snap_t = [s[0] for s in snaps]

rows = list(csv.DictReader(open(os.path.join(DATA, 'diversion-events.csv'))))
out = []; dists = []; cats = defaultdict(int); no_poly = 0
for r in rows:
    if r['displayWorthy'] != '1' or not r['lon']: continue
    t = int(r['startedAt']); clon, clat = float(r['lon']), float(r['lat'])
    verts = [(x, y) for name in r['routes'].split() for poly in by_route.get(name, []) for (x, y) in poly if d_m(clon, clat, x, y) <= SITE_R]
    if not verts: no_poly += 1; verts = [(clon, clat)]
    i = bisect.bisect_left(snap_t, t); cand = [j for j in (i - 1, i) if 0 <= j < len(snaps)]
    if not cand: continue
    j = min(cand, key=lambda j: abs(snap_t[j] - t))
    best = None
    for (dlon, dlat, s0, s1, cat, sev, did) in snaps[j][1]:
        if not (s0 - SLACK_S <= t <= s1 + SLACK_S): continue
        if d_m(clon, clat, dlon, dlat) > SITE_R + MATCH_M: continue
        d = min(d_m(x, y, dlon, dlat) for (x, y) in verts)
        if best is None or d < best[0]: best = (d, cat, sev, did)
    matched = best is not None and best[0] <= MATCH_M
    out.append({'id': r['id'], 'startedAt': t, 'snapshot_gap_s': abs(snap_t[j] - t), 'band_vertices': len(verts),
                'nearest_m': round(best[0]) if best else '', 'matched': int(matched),
                'cat': best[1] if matched else '', 'sev': best[2] if matched else '', 'tfl_id': best[3] if matched else ''})
    dists.append(best[0] if best else 9999)
    if matched: cats[best[1]] += 1
with open(os.path.join(DATA, 'tfl-match.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
n = len(out); m = sum(o['matched'] for o in out)
fig, ax = plt.subplots(figsize=(7.2, 2.6))
ax.hist([min(d, 1750) for d in dists], bins=range(0, 1800, 50), color=INK)
ax.axvline(MATCH_M, color=RED, ls='--', lw=1); ax.text(MATCH_M + 20, ax.get_ylim()[1] * 0.9, 'match radius 250 m', color=RED, fontsize=8)
ax.set_xlabel('distance from the event\'s route path to the nearest active TfL road disruption (m); last bar = none within 1.75 km'); ax.set_ylabel('displayed events')
ax.set_title(f'{m} of {n} displayed events ({100 * m / n:.0f}%) sit within 250 m of a TfL road disruption record', loc='left')
fig.tight_layout(); save(fig, 'fig-7-3-tfl-match')
put(tfl_match_events=n, tfl_match_matched=m, tfl_match_pct=round(100 * m / n, 1), tfl_match_by_category=dict(cats),
    tfl_match_events_without_polyline=no_poly, tfl_snapshots=len(snaps), tfl_snapshot_gap_p50_s=sorted(o['snapshot_gap_s'] for o in out)[n // 2])
print(n, m, dict(cats), 'no polyline', no_poly)
