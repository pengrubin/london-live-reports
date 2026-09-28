#!/usr/bin/env python3
"""Figures 2.2-2.5 and table 4.1 from data/daily/*.json (all scanned days):
  fig-2-2 fix interval distribution (per vehicle, consecutive fixes)
  fig-2-3 fixes per vehicle per day
  fig-2-4 implied speed distribution (5-60 s pairs) + glitch share
  fig-2-5 vehicles reporting per minute of day, weekday vs weekend
  numbers: operator shares, journey statistics (table 4.1)
"""
import json, glob, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
days = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(DATA, 'daily', '*.json')))]
print('days', len(days))
def add(acc, h):
    for k, v in h.items(): acc[k] = acc.get(k, 0) + v
    return acc
dt_all = {}; sp_all = {}; fpv = None; ops = {}
for d in days:
    add(dt_all, {int(k): v for k, v in d['dt_hist'].items()})
    add(sp_all, d['speed_hist'])
    h = d['fixes_per_vehicle_hist']
    fpv = [a + b for a, b in zip(fpv, h['counts'])] if fpv else list(h['counts']); edges = h['edges']
    for op, v in d['operators'].items():
        o = ops.setdefault(op, {'fixes': 0, 'veh_days': 0}); o['fixes'] += v['fixes']; o['veh_days'] += v['vehicles']

# fig 2.2 fix interval
tot = sum(dt_all.values()); cum = 0; q = {}
for k in sorted(dt_all):
    cum += dt_all[k]
    for p in (0.1, 0.5, 0.9, 0.99):
        if p not in q and cum >= p * tot: q[p] = k
fig, ax = plt.subplots(figsize=(7.2, 2.6))
xs = list(range(0, 301)); ys = [dt_all.get(x, 0) / tot * 100 for x in xs]
ax.bar(xs, ys, width=1, color=INK)
for p, c in ((0.1, GREY), (0.5, RED), (0.9, AMBER)): ax.axvline(q[p], color=c, lw=1, ls='--')
ax.text(0.99, 0.95, f'p10 = {q[0.1]} s   p50 = {q[0.5]} s   p90 = {q[0.9]} s (dashed lines)\nspikes at ~30 s and ~60 s are operator polling cadences', transform=ax.transAxes, ha='right', va='top', fontsize=7.5, color=INK)
ax.set_xlim(0, 300); ax.set_xlabel('seconds between consecutive fixes of the same vehicle'); ax.set_ylabel('% of fix pairs')
ax.set_title(f'Fix interval, all vehicles, {len(days)} days ({tot/1e6:.0f} M pairs); {100*sum(v for k,v in dt_all.items() if k>300)/tot:.1f}% beyond 300 s not shown', loc='left')
fig.tight_layout(); save(fig, 'fig-2-2-fix-interval')

# fig 2.3 fixes per vehicle-day
fig, ax = plt.subplots(figsize=(7.2, 2.4))
labels = [f'{edges[i]}–{edges[i+1]}' if i + 1 < len(edges) else f'{edges[i]}+' for i in range(len(edges))]
ax.bar(labels, [c / sum(fpv) * 100 for c in fpv], color=INK); ax.set_ylabel('% of vehicle-days'); ax.set_xlabel('fixes per vehicle per day'); ax.tick_params(axis='x', labelrotation=30)
ax.set_title('How much each vehicle reports in a day', loc='left'); fig.tight_layout(); save(fig, 'fig-2-3-fixes-per-vehicle')

# fig 2.4 implied speed
gl = sp_all.pop('glitch', 0); sp = {int(k): v for k, v in sp_all.items()}; stot = sum(sp.values())
fig, ax = plt.subplots(figsize=(7.2, 2.6))
xs = sorted(sp); ax.bar([x * 0.5 for x in xs], [sp[x] / stot * 100 for x in xs], width=0.5, color=INK)
cum = 0; sq = {}
for x in xs:
    cum += sp[x]
    for p in (0.5, 0.9):
        if p not in sq and cum >= p * stot: sq[p] = x * 0.5
ax.set_xlabel('implied speed between consecutive fixes 5–60 s apart (m/s)'); ax.set_ylabel('% of pairs')
ax.set_title(f'Implied speed; median {sq[0.5]:.1f} m/s, p90 {sq[0.9]:.1f} m/s; {100*gl/(stot+gl):.2f}% of pairs exceed 40 m/s (GPS glitches)', loc='left')
fig.tight_layout(); save(fig, 'fig-2-4-implied-speed')

# fig 2.5 vehicles per minute
wd = [d for d in days if dt.date.fromisoformat(d['day']).weekday() < 5 and d['day'] not in ('2026-09-04', '2026-09-11')]
we = [d for d in days if dt.date.fromisoformat(d['day']).weekday() >= 5]
med = lambda ds, m: sorted(d['vehicles_per_minute'][m] for d in ds)[len(ds) // 2]
fig, ax = plt.subplots(figsize=(7.2, 2.6))
hrs = [m / 60 for m in range(1440)]
ax.plot(hrs, [med(wd, m) for m in range(1440)], color=INK, lw=1.1, label=f'weekday median ({len(wd)} days)')
ax.plot(hrs, [med(we, m) for m in range(1440)], color=GREY, lw=1.1, label=f'weekend median ({len(we)} days)')
ax.set_xlim(0, 24); ax.set_xticks(range(0, 25, 3)); ax.set_xlabel('hour of day (UTC; London is UTC+1 in this period)'); ax.set_ylabel('vehicles with a fix in that minute')
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.32), ncol=2); ax.set_title('Reporting fleet through the day', loc='left'); fig.tight_layout(); save(fig, 'fig-2-5-vehicles-per-minute')

# journeys (table 4.1) and operator shares
J = {}
for grp in ('all', 'complete', 'tflo_all', 'tflo_complete', 'other_all', 'other_complete'):
    ns = [d['journeys'][grp] for d in days if d['journeys'][grp].get('n')]
    J[grp] = {'n_per_day_median': sorted(x['n'] for x in ns)[len(ns) // 2],
              'len_m_p50': sorted(x['len_m_p50'] for x in ns)[len(ns) // 2], 'dur_s_p50': sorted(x['dur_s_p50'] for x in ns)[len(ns) // 2],
              'fixes_p50': sorted(x['fixes_p50'] for x in ns)[len(ns) // 2]}
tf = sum(o['fixes'] for o in ops.values())
op_share = sorted(((op, round(100 * o['fixes'] / tf, 1)) for op, o in ops.items()), key=lambda x: -x[1])[:8]
peak_wd = max(med(wd, m) for m in range(1440)); peak_min = max(range(1440), key=lambda m: med(wd, m))
put(scan_days=len(days), fix_pairs_total=tot, fix_interval_p10_s=q[0.1], fix_interval_p50_s=q[0.5], fix_interval_p90_s=q[0.9], fix_interval_p99_s=q[0.99],
    fix_interval_over_300s_pct=round(100 * sum(v for k, v in dt_all.items() if k > 300) / tot, 2),
    speed_p50_ms=sq[0.5], speed_p90_ms=sq[0.9], speed_glitch_pct=round(100 * gl / (stot + gl), 3),
    operator_fix_share_pct=dict(op_share), tflo_fix_share_pct=round(100 * ops.get('TFLO', {'fixes': 0})['fixes'] / tf, 1),
    fleet_peak_weekday_vehicles_per_minute=peak_wd, fleet_peak_weekday_time_utc=f'{peak_min//60:02d}:{peak_min%60:02d}',
    journeys=J, malformed_lines_total=sum(d['malformed'] for d in days))
print(json.dumps({'q': q, 'sq': sq, 'ops': op_share, 'J': J}, indent=1))
