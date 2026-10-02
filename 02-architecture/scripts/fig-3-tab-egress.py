#!/usr/bin/env python3
"""What one open tab costs the origin per minute: requests and compressed bytes per endpoint."""
import os, sys, json, csv
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
ep = {r['endpoint']: r for r in csv.DictReader(open(os.path.join(DATA, 'endpoints.csv'))) if r['deployment'] == 'london'}
nr = list(csv.DictReader(open(os.path.join(DATA, 'endpoints-nr-board.csv'))))
nr_ok = sorted(float(r['br_wire_bytes_median']) for r in nr if r['samples_ok'] not in ('0', '')); nr_br = nr_ok[len(nr_ok) // 2]
# frontend poll table (client inventory): endpoint -> interval s
TAB = [('nr-board', 4, nr_br), ('aircraft', 5, None), ('arrivals', 10, None), ('vessels', 10, None), ('buses', 15, None), ('leaderboard', 30, None), ('bikes', 60, None), ('disruptions', 90, None), ('road-disruptions', 120, None), ('tide-gauges', 300, None)]
rows = []
for name, T, br in TAB:
    key = {'leaderboard': 'leaderboard day/bus', 'arrivals': 'arrivals (25 lines)', 'bikes': 'bikes (GBFS)'}.get(name, name)
    if br is None:
        r = ep[key]; br = float(r['br_wire_bytes_median'] or 0)
    rows.append((name, 60 / T, 60 / T * br / 1000))
tot_req = sum(r[1] for r in rows); tot_kb = sum(r[2] for r in rows)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.2)); names = [r[0] for r in rows]; y = range(len(rows))
ax1.barh(list(y), [r[1] for r in rows], color=INK); ax1.set_yticks(list(y)); ax1.set_yticklabels(names, fontsize=8); ax1.invert_yaxis(); ax1.set_xlabel(f'requests per minute (total {tot_req:.1f})')
for i, r in enumerate(rows): ax1.text(r[1] + 0.3, i, f"{r[1]:.1f}", va='center', fontsize=7.2)
ax1.set_xlim(0, max(r[1] for r in rows) * 1.2)
ax2.barh(list(y), [r[2] for r in rows], color=RED); ax2.set_yticks(list(y)); ax2.set_yticklabels([]); ax2.invert_yaxis(); ax2.set_xlabel(f'compressed KB per minute (total {tot_kb:,.0f})')
for i, r in enumerate(rows): ax2.text(r[2] + 15, i, f"{r[2]:,.0f}", va='center', fontsize=7.2)
ax2.set_xlim(0, max(r[2] for r in rows) * 1.22); fig.tight_layout(); save(fig, 'fig-3-tab-egress')
put(tab_nr_board_kb_per_min=round(rows[0][2]), tab_arrivals_kb_per_min=round(rows[2][2]), tab_buses_kb_per_min=round(rows[4][2]))
