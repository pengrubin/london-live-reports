#!/usr/bin/env python3
"""Case-study figures 7.4-7.6 from the 2026-09-22 traces of the affected routes.
For each case: left, the learned path(s) with every fix of the case routes near
the site coloured by |d| (on-route grey, off-route red); right, one vehicle's
(s, d) time series with the excursion marked. Also fig 7.1 (the (s,d) plane
illustration) reuses the H32 vehicle.
"""
import json, os, sys, math, glob, datetime as dt
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
M_LAT = 110_540.0; M_LON = 111_320.0 * math.cos(math.radians(51.5))
SNAP = sorted(glob.glob(os.path.join(DATA, 'learned', '*')))[-1]
TR = os.path.join(DATA, 'cases', 'traces-2026-09-22-cases.jsonl')

def load_poly(key):
    p = os.path.join(SNAP, 'routes', key.replace(':', '_') + '.json')
    d = json.load(open(p)); poly = d['poly']
    xs = [x * M_LON for x, y in poly]; ys = [y * M_LAT for x, y in poly]
    cum = [0.0]
    for i in range(1, len(xs)): cum.append(cum[-1] + math.hypot(xs[i] - xs[i-1], ys[i] - ys[i-1]))
    return {'key': key, 'xs': xs, 'ys': ys, 'cum': cum, 'res': d.get('quality', {}).get('meanResidualM', 15)}

def project(P, px, py):
    best = (0.0, float('inf'))
    xs, ys, cum = P['xs'], P['ys'], P['cum']
    for i in range(len(xs) - 1):
        ax, ay, bx, by = xs[i], ys[i], xs[i+1], ys[i+1]; dx, dy = bx - ax, by - ay; L2 = dx*dx + dy*dy
        t = 0 if L2 == 0 else max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / L2))
        d = math.hypot(px - (ax + t*dx), py - (ay + t*dy))
        if d < best[1]: best = (cum[i] + t * math.sqrt(L2), d)
    return best

fixes = defaultdict(list)
for line in open(TR):
    r = json.loads(line); fixes[r['k']].append(r)
for k in fixes: fixes[k].sort(key=lambda r: r['t'])

CASES = [
    # name, keys drawn, site centre (lon, lat), radius m, vehicle for the time series, time window (UTC h)
    ('7-4-camberwell', ['TFLO:36:inbound', 'TFLO:36:outbound', 'TFLO:185:inbound', 'TFLO:185:outbound'], (-0.0970, 51.4795), 1800, 'TFLO:LG73FRP', (13.5, 16.5),
     'Camberwell New Road blocked by a collision, 22 Sep 13:53 BST'),
    ('7-5-h32', ['TFLO:H32:inbound', 'TFLO:H32:outbound'], (-0.3748, 51.4968), 2500, 'TFLO:LTZ1657', (18.5, 21.0),
     'H32 near North Hyde, 22 Sep: no TfL road record within 250 m at the time'),
    ('7-6-victoria', ['TFLO:11:inbound', 'TFLO:11:outbound', 'TFLO:24:inbound', 'TFLO:24:outbound', 'TFLO:148:inbound', 'TFLO:148:outbound'], (-0.1303, 51.4951), 1000, None, (9.5, 12.5),
     'Victoria Street closed, 22 Sep: routes 11, 24, 26 and 148 share one band'),
]
def utc_h(t): return (t % 86400) / 3600
for name, keys, (clon, clat), R, veh, (h0, h1), title in CASES:
    cx, cy = clon * M_LON, clat * M_LAT
    polys = {k: load_poly(k) for k in keys}
    fig, (axm, axs) = plt.subplots(1, 2, figsize=(7.2, 3.9), gridspec_kw={'width_ratios': [1.15, 1]})
    for k, P in polys.items(): axm.plot([x - cx for x in P['xs']], [y - cy for y in P['ys']], lw=1.2, color=LIGHT, zorder=1)
    on = []; off = []; cand = defaultdict(int)
    for k, P in polys.items():
        thr = max(50, 5 * P['res'])
        for r in fixes.get(k, []):
            if not (h0 <= utc_h(r['t']) <= h1): continue
            px, py = r['x'] * M_LON, r['y'] * M_LAT
            if abs(px - cx) > R or abs(py - cy) > R: continue   # square window = the axis window, so nothing drawn is cut
            s, d = project(P, px, py)
            if d > 1500: continue   # the detector's credibility cap: not a diversion, not drawn
            (off if d > thr else on).append((px - cx, py - cy))
            if d > thr: cand[(k, r['i'])] += 1
    axm.scatter([p[0] for p in on], [p[1] for p in on], s=2, color=GREY, alpha=0.5, zorder=2, label=f'on-route fixes ({len(on)})')
    axm.scatter([p[0] for p in off], [p[1] for p in off], s=3, color=RED, alpha=0.7, zorder=3, label=f'off-route fixes ({len(off)}); fixes over 1.5 km from any path not drawn')
    axm.set_aspect('equal'); axm.set_xlim(-1.05 * R, 1.05 * R); axm.set_ylim(-1.05 * R, 1.05 * R); axm.set_xlabel('m east of site'); axm.set_ylabel('m north of site'); axm.legend(loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=1, fontsize=7)
    axm.set_title(f'{h0:.0f}:00–{h1:.0f}:00 UTC, {len(keys)} learned paths', fontsize=8.5, loc='left')
    if name == '7-4-camberwell':
        # TfL road-disruption point for TIMS record: Camberwell New Road / Wyndham Road, (-0.101978, 51.477709)
        tx, ty = (-0.101978 - clon) * M_LON, (51.477709 - clat) * M_LAT
        axm.scatter([tx], [ty], s=90, marker='x', color=INK, zorder=6, lw=1.5)
        axm.annotate('collision (TfL record)', (tx, ty), xytext=(-1500, -1200), fontsize=7, color=INK, arrowprops=dict(arrowstyle='-', color=INK, lw=0.6))
        axm.scatter([0], [0], s=40, marker='+', color='#4a5563', zorder=6, lw=1)
        axm.text(60, 60, 'event centroid', fontsize=6.5, color='#4a5563')
        axm.annotate('buses leave the route', (-1150, 720), xytext=(-1750, 1750), fontsize=7, color=RED, arrowprops=dict(arrowstyle='-', color=RED, lw=0.6))
        axm.annotate('detour, ~1.5 km north', (-200, 1500), xytext=(500, 1650), fontsize=7, color=RED, arrowprops=dict(arrowstyle='-', color=RED, lw=0.6))
        axm.annotate('rejoin the route', (270, -500), xytext=(700, -1000), fontsize=7, color=RED, arrowprops=dict(arrowstyle='-', color=RED, lw=0.6))
        axm.text(1000, -400, 'normal route\n(grey = on-route fixes)', fontsize=7, color='#4a5563', ha='left')
    # time series: chosen vehicle or the one with most off-route fixes
    if veh: k, v = next(((k, veh) for (k, vv) in cand if vv == veh), max(cand, key=cand.get))
    else: k, v = max(cand, key=cand.get)
    P = polys[k]; thr = max(50, 5 * P['res'])
    series = [(r['t'],) + project(P, r['x'] * M_LON, r['y'] * M_LAT) for r in fixes[k] if r['i'] == v and h0 - 0.5 <= utc_h(r['t']) <= h1 + 0.5]
    tt = [utc_h(t) for t, s, d in series]
    axs.plot(tt, [s / 1000 for t, s, d in series], lw=1, color=INK, label='s: position along path (km)')
    ax2 = axs.twinx(); ax2.plot(tt, [min(d, 1500) for t, s, d in series], lw=0.9, color=RED, label='d: distance from path (m)')
    ax2.axhline(thr, color=RED, lw=0.7, ls='--'); ax2.set_ylim(0, 1500); ax2.set_ylabel('d (m)', color=RED); ax2.grid(False)
    for spine in ('top',): ax2.spines[spine].set_visible(False)
    if name == '7-4-camberwell':
        for (t0e, t1e) in ((14.35, 14.85), (15.45, 15.8)):
            axs.axvspan(t0e, t1e, color=RED, alpha=0.08, lw=0)
        axs.text(15.15, 8.2, 'off route:\ndriving\nthe detour', ha='center', fontsize=7, color=RED)
        axs.text(13.45, 2.2, 'one trip\ntowards\nthe city', fontsize=7, color=INK, ha='center')
        axs.text(16.6, 2.2, 'next trip\nback out', fontsize=7, color=INK, ha='center')
    axs.set_xlabel('hour (UTC)'); axs.set_ylabel('s (km)'); axs.set_title(f'{k.split(":")[1]} {k.split(":")[2]}, vehicle {v.split(":")[1]}; threshold {thr:.0f} m', fontsize=8.5, loc='left')
    h1l, l1 = axs.get_legend_handles_labels(); h2l, l2 = ax2.get_legend_handles_labels(); axs.legend(h1l + h2l, l1 + l2, loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=1, fontsize=7)
    fig.suptitle(title, x=0.01, ha='left', fontsize=9.5); fig.tight_layout(); save(fig, f'fig-{name}')
    put(**{f'case_{name.split("-",2)[2]}_offroute_fixes': len(off), f'case_{name.split("-",2)[2]}_onroute_fixes': len(on), f'case_{name.split("-",2)[2]}_vehicle': v})
