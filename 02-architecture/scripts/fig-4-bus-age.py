#!/usr/bin/env python3
"""Age of each bus fix at the moment /api/buses is served (production, daytime)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
b = json.load(open(os.path.join(DATA, 'bus-age.json'))); h = b['histogram_10s_bins']; p = b['pooled']
keys = list(h.keys()); vals = [h[k] for k in keys]; tot = sum(vals); x = [int(k[:3]) + 5 for k in keys]
fig, ax = plt.subplots(figsize=(7.2, 3.0)); ax.bar(x, [100 * v / tot for v in vals], width=9, color=INK)
for q, lab in [('p50', 'median'), ('p95', '95th percentile')]:
    ax.axvline(p[q], color=RED, lw=1, ls='--'); ax.text(p[q] + 3, ax.get_ylim()[1] * 0.92 if q == 'p50' else ax.get_ylim()[1] * 0.75, f"{lab} {p[q]:.0f} s", color=RED, fontsize=8)
ax.set_xlabel('age of the fix when served, seconds (operator report time to HTTP response)'); ax.set_ylabel('% of fixes'); ax.set_xlim(0, 310)
fig.tight_layout(); save(fig, 'fig-4-bus-age')
put(bus_age_fixes=p['fixes'], bus_age_under_30_pct=round(100 * sum(v for k, v in h.items() if int(k[:3]) < 30) / tot), bus_age_over_120_pct=round(100 * sum(v for k, v in h.items() if int(k[:3]) >= 120) / tot, 1))
