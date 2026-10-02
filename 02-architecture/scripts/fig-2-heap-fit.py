#!/usr/bin/env python3
"""Production heap over the primary uptime window: observed vs the two-counter linear model."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
from datetime import datetime, timezone
m = json.load(open(os.path.join(DATA, 'memory-fit.json'))); w = m['primary_window']
fit = m['fits_primary_window']['heapUsedMB']['M4 vehicleStates + lbVehicleTotals']['coefficients']
a, bv, bl = fit['intercept']['value'], fit['vehicleStates']['value'], fit['lbVehicleTotals']['value']
t0 = datetime.fromisoformat(w['from'].replace('Z', '+00:00')).timestamp(); t1 = datetime.fromisoformat(w['to'].replace('Z', '+00:00')).timestamp()
T, H, P, VS, LB = [], [], [], [], []
for line in open(os.path.expanduser('~/bus-archive/health-samples.jsonl')):
    try: r = json.loads(line)
    except Exception: continue
    if r.get('status') != 200 or not (t0 <= r['at'] <= t1): continue
    c = r['comp']; t = (r['at'] - t0) / 86400
    if T and t - T[-1] > 15 / 1440:  # break the line across sampling gaps longer than 15 min (laptop off) instead of drawing a chord
        T.append(t - 1e-6); H.append(float('nan')); P.append(float('nan')); VS.append(float('nan')); LB.append(float('nan'))
    T.append(t); H.append(r['mem']['heapUsedMB']); VS.append(c['vehicleStates']); LB.append(c['lbVehicleTotals'])
    P.append(a + bv * c['vehicleStates'] + bl * c['lbVehicleTotals'])
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 5.0), sharex=True, gridspec_kw={'height_ratios': [2, 1.1]})
ax1.plot(T, H, color=INK, lw=0.8, label='heap used, observed'); ax1.plot(T, P, color=RED, lw=0.9, label='model: 146 MB + 3.48 KB per vehicle state + 0.33 KB per leaderboard entry')
ax1.set_ylabel('heap used, MB'); ax1.legend(loc='upper left', ncol=1)
ax2.plot(T, [v / 1000 for v in VS], color=INK, lw=0.8, label='vehicle states, thousands (left axis)'); ax2.set_ylabel('vehicle states, k'); ax2.set_ylim(0, 13)
ax3 = ax2.twinx(); ax3.plot(T, [v / 1000 for v in LB], color=GREY, lw=0.8, label='leaderboard entries, thousands (right axis)'); ax3.set_ylabel('leaderboard, k', color=GREY); ax3.grid(False); ax3.set_ylim(150, 520)
h1, l1 = ax2.get_legend_handles_labels(); h2, l2 = ax3.get_legend_handles_labels(); ax2.legend(h1 + h2, l1 + l2, loc='upper center', bbox_to_anchor=(0.5, -0.32), ncol=2)
ax2.set_xlabel(f"days since process start ({w['from'][:10]})")
# label each gap in the top panel: the sampler runs on a laptop and stops with it
gaps = [(T[i-1], T[i+1]) for i in range(1, len(T)-1) if H[i] != H[i]]  # NaN marker sits between the last sample before the gap and the first after
for a, b in gaps:
    if b - a > 0.5: ax1.text((a + b) / 2, 230, 'no samples:\nlaptop off', ha='center', va='center', fontsize=7, color=GREY)
fig.tight_layout(); save(fig, 'fig-2-heap-fit')
put(heap_fit_days=round((t1 - t0) / 86400, 1), heap_obs_min_mb=min(H), heap_obs_max_mb=max(H), vs_min=min(VS), vs_max=max(VS), lb_min=min(LB), lb_max=max(LB))
