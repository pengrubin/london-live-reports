#!/usr/bin/env python3
"""Fig 2.1: fixes, vehicles and journeys per day from the daily rollups (38 days).
Also numbers: weekday/weekend medians, the two outage days."""
import json, glob, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
A = sys.argv[1] if len(sys.argv) > 1 else '/Volumes/大龟壳/bus-archive'
rows = []
for f in sorted(glob.glob(os.path.join(A, 'bus-rollups', '*.json'))):
    d = json.load(open(f)); t = d['totals']
    rows.append((dt.date.fromisoformat(d['day']), t['fixes'], t['vehicles'], t['journeys'], t['routes']))
days = [r[0] for r in rows]
fig, axes = plt.subplots(3, 1, figsize=(7.2, 5.2), sharex=True)
for ax, (idx, label, scale) in zip(axes, [(1, 'GPS fixes per day (millions)', 1e6), (2, 'distinct vehicles per day', 1), (3, 'journeys per day (thousands)', 1e3)]):
    ys = [r[idx] / scale for r in rows]
    ax.bar(days, ys, width=0.8, color=[GREY if d.weekday() >= 5 else INK for d in days])
    ax.set_ylabel(label, fontsize=8); ax.set_ylim(0, max(ys) * (1.45 if idx == 1 else 1.12))
for d, lab in [(dt.date(2026, 9, 4), 'OOM crash'), (dt.date(2026, 9, 11), 'HTTP client crash')]:
    top = max(r[1] for r in rows) / 1e6
    axes[0].annotate(lab, (d, [r[1] for r in rows if r[0] == d][0] / 1e6), xytext=(d, top * 1.3), textcoords='data', ha='center', va='bottom', fontsize=7.5, color=RED, arrowprops=dict(arrowstyle='-', color=RED, lw=0.6))
axes[0].set_title('Daily volume of the BODS feed for London (grey = weekend)', loc='left')
axes[-1].tick_params(axis='x', rotation=45)
fig.tight_layout(); save(fig, 'fig-2-1-fleet-daily')
wd = [r for r in rows if r[0].weekday() < 5 and r[0] not in (dt.date(2026, 9, 4), dt.date(2026, 9, 11))]
we = [r for r in rows if r[0].weekday() >= 5]
med = lambda a: sorted(a)[len(a) // 2]
put(days_of_rollups=len(rows), first_day=str(days[0]), last_day=str(days[-1]),
    fixes_per_day_weekday_median=med([r[1] for r in wd]), fixes_per_day_weekend_median=med([r[1] for r in we]),
    vehicles_per_day_weekday_median=med([r[2] for r in wd]), vehicles_per_day_weekend_median=med([r[2] for r in we]),
    journeys_per_day_weekday_median=med([r[3] for r in wd]), journeys_per_day_weekend_median=med([r[3] for r in we]),
    route_keys_weekday_median=med([r[4] for r in wd]))
