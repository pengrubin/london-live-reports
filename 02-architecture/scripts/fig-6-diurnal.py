#!/usr/bin/env python3
"""24 hours of one deployment: what moves with the clock and what does not."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
d = json.load(open(os.path.join(ROOT, 'data-24h', 'diurnal.json')))['hours']
H = sorted(h for h, v in d.items() if 'live_vehicles' in v and 'cpu_ms_per_15s' in v and 'prod_predictions' in v)
x = list(range(len(H))); lab = [h[-2:] for h in H]
g = lambda k: [d[h].get(k) for h in H]
fig, axes = plt.subplots(4, 1, figsize=(7.2, 9.2), sharex=True)
ax = axes[0]; ax.plot(x, g('live_vehicles'), color=INK, label='live buses (replica, per poll)'); ax.plot(x, g('prod_predictions'), color=RED, label='train predictions (production, per fetch)'); ax.set_ylabel('count'); ax.legend(loc='upper left', ncol=2, fontsize=7.5); ax.set_ylim(0, 10500)
ax = axes[1]; ax.plot(x, g('bods_wire_kb'), color=INK, label='bus feed, KB on the wire per poll'); ax.set_ylabel('KB per poll'); ax.set_ylim(0, 1300)
ax2 = ax.twinx(); ax2.plot(x, g('parse_ms'), color=RED, label='parse block, ms per poll'); ax2.set_ylabel('ms', color=RED); ax2.grid(False); ax2.set_ylim(0, 80)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax.legend(h1 + h2, l1 + l2, loc='lower left', ncol=2, fontsize=7.5)
ax = axes[2]; ax.plot(x, g('cpu_ms_per_15s'), color=INK, label='process CPU, ms per 15 s (unprofiled)'); ax.set_ylabel('ms per 15 s'); ax.set_ylim(0, 700)
ax2 = ax.twinx(); ax2.plot(x, g('heap_mb'), color=GREY, label='heap used, MB'); ax2.set_ylabel('MB', color=GREY); ax2.grid(False); ax2.set_ylim(0, 260)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax.legend(h1 + h2, l1 + l2, loc='lower left', ncol=2, fontsize=7.5)
ax = axes[3]; kb = [(a or 0) * 4 + (b or 0) * 6 for a, b in zip(g('prod_buses_br_kb'), g('prod_arrivals_br_kb'))]
ax.plot(x, kb, color=RED, label='bus + prediction bodies per tab, KB per minute (production)'); ax.set_ylabel('KB per minute'); ax.set_ylim(0, 2200)
ax2 = ax.twinx(); ax2.plot(x, g('prod_bus_age_p50'), color=GREY, label='bus fix age at response, median s'); ax2.set_ylabel('s', color=GREY); ax2.grid(False); ax2.set_ylim(0, 80)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax.legend(h1 + h2, l1 + l2, loc='upper center', bbox_to_anchor=(0.5, -0.42), ncol=1, fontsize=7.5)
ax.set_xticks(x[::2]); ax.set_xticklabels(lab[::2]); ax.set_xlabel(f"hour of day, UTC ({H[0][:10]} {H[0][-2:]}:00 to {H[-1][:10]} {H[-1][-2:]}:00); hourly medians")
fig.tight_layout(); save(fig, 'fig-6-diurnal')
