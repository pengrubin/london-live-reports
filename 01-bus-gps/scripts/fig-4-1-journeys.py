#!/usr/bin/env python3
"""Fig 4.1: one vehicle's day as arc length along the learned path of whichever
direction its fixes are labelled with, with the learner's journey splits marked:
600 s gaps (dashed) and terminal layovers >= 300 s within 80 m (dotted)."""
import json, os, sys, math, datetime as dt
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
M_LAT = 110_540.0; M_LON = 111_320.0 * math.cos(math.radians(51.5))
src = os.path.join(DATA, 'cases', 'LTZ1502-2026-09-25-all.jsonl')
polys = {}
for k in ('TFLO:11:inbound', 'TFLO:11:outbound'):
    d = json.load(open(os.path.join(DATA, 'cases', k.replace(':', '_') + '.json'))); poly = d['poly']
    xs = [x * M_LON for x, y in poly]; ys = [y * M_LAT for x, y in poly]; cum = [0.0]
    for i in range(1, len(xs)): cum.append(cum[-1] + math.hypot(xs[i]-xs[i-1], ys[i]-ys[i-1]))
    polys[k] = (xs, ys, cum)
def project(k, px, py):
    xs, ys, cum = polys[k]; best = (0.0, float('inf'))
    for i in range(len(xs)-1):
        ax, ay, bx, by = xs[i], ys[i], xs[i+1], ys[i+1]; dx, dy = bx-ax, by-ay; L2 = dx*dx+dy*dy
        t = 0 if L2 == 0 else max(0, min(1, ((px-ax)*dx+(py-ay)*dy)/L2)); dd = math.hypot(px-(ax+t*dx), py-(ay+t*dy))
        if dd < best[1]: best = (cum[i]+t*math.sqrt(L2), dd)
    return best
fx = sorted((json.loads(l) for l in open(src)), key=lambda r: r['t'])
t0 = fx[0]['t']; H = lambda t: (t - t0) / 3600
pts = []  # (h, s_km, key, d)
for r in fx:
    s, d = project(r['k'], r['x'] * M_LON, r['y'] * M_LAT); pts.append((H(r['t']), s / 1000, r['k'], d))
# splits
gaps = [H(fx[i]['t']) for i in range(1, len(fx)) if fx[i]['t'] - fx[i-1]['t'] > 600]
lay = []; i = 0
while i < len(fx):
    j = i
    while j + 1 < len(fx) and math.hypot((fx[j+1]['x']-fx[i]['x'])*M_LON, (fx[j+1]['y']-fx[i]['y'])*M_LAT) <= 80: j += 1
    if fx[j]['t'] - fx[i]['t'] >= 300: lay.append((H(fx[i]['t']), H(fx[j]['t']))); i = j + 1
    else: i += 1
fig, ax = plt.subplots(figsize=(7.2, 3.0))
for k, c, lab in (('TFLO:11:inbound', INK, 'labelled inbound, s on inbound path'), ('TFLO:11:outbound', RED, 'labelled outbound, s on outbound path')):
    P = [p for p in pts if p[2] == k]
    ax.scatter([p[0] for p in P], [p[1] for p in P], s=3, color=c, label=lab)
for g in gaps: ax.axvline(g, color=GREY, lw=0.7, ls='--')
for a, b in lay: ax.axvspan(a, b, color=AMBER, alpha=0.25, lw=0)
ax.set_xlabel(f'hours since first fix ({dt.datetime.fromtimestamp(t0, dt.UTC):%Y-%m-%d %H:%M} UTC)'); ax.set_ylabel('arc length along path (km)')
ax.set_title(f'Vehicle LTZ1502 on route 11: {len(fx)} fixes, {len(gaps)} gaps > 600 s (dashed), {len(lay)} layovers ≥ 300 s within 80 m (shaded)', loc='left')
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.28), ncol=2, fontsize=7.5); fig.tight_layout(); save(fig, 'fig-4-1-journeys')
put(journey_case_fixes=len(fx), journey_case_gaps=len(gaps), journey_case_layovers=len(lay), journey_case_mislabelled_fixes=sum(1 for p in pts if p[3] > 80))
print('gaps', len(gaps), 'layovers', len(lay), 'far-from-path fixes', sum(1 for p in pts if p[3] > 80))
