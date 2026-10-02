#!/usr/bin/env python3
"""The feed carries the same records by day and night; live vehicles halve; CPU does not move."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
N = json.load(open(NUMBERS))
pairs = [('feed\nrecords', N['bus_records_night'], N['bus_records_per_poll']), ('XML MB\nper poll', N['bus_decoded_mb'] * (7.26/7.59), N['bus_decoded_mb']),
         ('live\nvehicles', N['bus_live_night'], N['bus_live_day']), ('train\npredictions', N['ep_arrivals_records_night'], N['ep_arrivals_records']),
         ('process\nCPU ms', N['cpu_process_ms_control_night'], N['cpu_process_ms_control']), ('parse ms\nper poll', N['parse_ms_per_poll_night'], N['parse_ms_per_poll_day']),
         ('buses body\nKB br', N['ep_buses_br_kb_night'], N['ep_buses_br_kb']), ('arrivals body\nKB br', N['ep_arrivals_br_kb_night'], N['ep_arrivals_br_kb'])]
fig, ax = plt.subplots(figsize=(7.2, 3.3)); x = range(len(pairs))
ax.bar([i - 0.2 for i in x], [100 * n / d for _, n, d in pairs], 0.4, color=GREY, label=f"night ({N['cal_night_date']} {N['cal_night_window'].split(' to ')[0]} UTC)")
ax.bar([i + 0.2 for i in x], [100] * len(pairs), 0.4, color=INK, label=f"day ({N['cal_day_date']} {N['cal_day_window'].split(' to ')[0]} UTC) = 100")
for i, (_, n, d) in enumerate(pairs): ax.text(i - 0.2, 100 * n / d + 2, f"{100*n/d:.0f}%", ha='center', fontsize=7.2)
ax.set_xticks(list(x)); ax.set_xticklabels([p[0] for p in pairs], fontsize=7.5); ax.set_ylabel('night as % of day'); ax.set_ylim(0, 118); ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=2)
fig.tight_layout(); save(fig, 'fig-5-day-night')
put(night_live_pct=round(100 * N['bus_live_night'] / N['bus_live_day']), night_records_pct=round(100 * N['bus_records_night'] / N['bus_records_per_poll']), night_cpu_pct=round(100 * N['cpu_process_ms_control_night'] / N['cpu_process_ms_control']))
