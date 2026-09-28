#!/usr/bin/env python3
"""Section 7.8: what the detector produced over the logged days.
  fig-7-7 displayed events started per hour of day (weekday/weekend) and per day
  table numbers: outcomes, sizes, durations, TfL-match rate by size
"""
import csv, os, sys, datetime as dt
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
ev = list(csv.DictReader(open(os.path.join(DATA, 'diversion-events.csv'))))
mt = {r['id']: r for r in csv.DictReader(open(os.path.join(DATA, 'tfl-match.csv')))}
shown = [e for e in ev if e['displayWorthy'] == '1' and e['startedAt']]
days = sorted({dt.datetime.fromtimestamp(int(e['startedAt']), dt.UTC).date() for e in shown})
per_day = Counter(dt.datetime.fromtimestamp(int(e['startedAt']), dt.UTC).date() for e in shown)
hour = defaultdict(lambda: [0, 0])
for e in shown:
    d = dt.datetime.fromtimestamp(int(e['startedAt']), dt.UTC); hour[d.hour][1 if d.weekday() >= 5 else 0] += 1
nwd = sum(1 for d in days if d.weekday() < 5); nwe = len(days) - nwd
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 2.6), gridspec_kw={'width_ratios': [1.3, 1]})
a1.bar(sorted(per_day), [per_day[d] for d in sorted(per_day)], color=[GREY if d.weekday() >= 5 else INK for d in sorted(per_day)])
a1.set_ylabel('displayed events started'); a1.set_title(f'Per day, {len(days)} logged days (grey = weekend)', loc='left'); a1.tick_params(axis='x', rotation=45)
a2.plot(range(24), [hour[h][0] / max(1, nwd) for h in range(24)], color=INK, lw=1.2, label='weekday')
a2.plot(range(24), [hour[h][1] / max(1, nwe) for h in range(24)], color=GREY, lw=1.2, label='weekend')
a2.set_xlabel('hour (UTC)'); a2.set_ylabel('events per day'); a2.set_xticks(range(0, 25, 6)); a2.legend(); a2.set_title('By hour of day', loc='left')
fig.tight_layout(); save(fig, 'fig-7-7-events-per-day')

q = lambda a, p: sorted(a)[min(len(a) - 1, int(p * len(a)))]
dur = [int(e['duration_s']) for e in shown]; veh = [int(e['max_vehicles']) for e in shown]; nr = [int(e['n_routes']) for e in shown]
def match_rate(pred):
    s = [e for e in shown if pred(e) and e['id'] in mt]; k = sum(int(mt[e['id']]['matched']) for e in s)
    return {'n': len(s), 'matched': k, 'pct': round(100 * k / max(1, len(s)), 1)}
put(ev_logged_days=len(days), ev_total_ids=len(ev), ev_displayed=len(shown), ev_displayed_per_day_median=q(list(per_day.values()), .5),
    ev_outcomes=dict(Counter(e['outcome'] for e in shown)),
    ev_duration_p50_min=round(q(dur, .5) / 60), ev_duration_p90_min=round(q(dur, .9) / 60),
    ev_vehicles_p50=q(veh, .5), ev_vehicles_p90=q(veh, .9), ev_routes_p50=q(nr, .5), ev_routes_p90=q(nr, .9),
    ev_share_single_route_pct=round(100 * sum(1 for x in nr if x == 1) / len(nr), 1),
    ev_match_all=match_rate(lambda e: True), ev_match_5veh=match_rate(lambda e: int(e['max_vehicles']) >= 5),
    ev_match_2routes=match_rate(lambda e: int(e['n_routes']) >= 2), ev_match_10veh_2routes=match_rate(lambda e: int(e['max_vehicles']) >= 10 and int(e['n_routes']) >= 2),
    ev_peak_hour_utc=max(range(24), key=lambda h: hour[h][0]))
print('displayed', len(shown), 'per day median', q(list(per_day.values()), .5), 'outcomes', Counter(e['outcome'] for e in shown))
