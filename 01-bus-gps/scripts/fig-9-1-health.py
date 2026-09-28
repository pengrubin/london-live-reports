#!/usr/bin/env python3
"""Fig 9.1: in-memory table sizes and process memory from the local /health
sampler (every 300 s). Gaps are sampler outages (laptop off), not server ones."""
import json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
src = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/bus-archive/health-samples.jsonl')
rows = [json.loads(l) for l in open(src) if '"mem"' in l]
t = [dt.datetime.fromtimestamp(r['at'], dt.UTC) for r in rows]
def series(path):
    out = []
    for r in rows:
        v = r
        for p in path: v = v.get(p) if isinstance(v, dict) else None
        out.append(v)
    return out
# break lines across sampler gaps > 20 min
import math
def gapped(vals):
    return [v if (i == 0 or (t[i] - t[i-1]).total_seconds() <= 1200) else float('nan') for i, v in enumerate(vals)]
fig, axes = plt.subplots(3, 1, figsize=(7.2, 6.2), sharex=True)
axes[0].plot(t, gapped(series(['mem', 'rssMB'])), lw=0.8, color=RED, label='RSS'); axes[0].plot(t, gapped(series(['mem', 'heapUsedMB'])), lw=0.8, color=INK, label='V8 heap used')
axes[0].set_ylabel('MB'); axes[0].legend(loc='upper right', ncol=2, fontsize=7.5, bbox_to_anchor=(1, 1.08)); axes[0].set_title('Backend process, sampled every 5 min from /health', loc='left')
axes[1].plot(t, gapped(series(['comp', 'vehicleStates'])), lw=0.8, color=INK, label='vehicle states (diversion detector)'); axes[1].plot(t, gapped(series(['comp', 'routeIndexes'])), lw=0.8, color=GREY, label='route indexes')
axes[1].set_ylabel('entries'); axes[1].legend(loc='upper right', ncol=2, fontsize=7.5, bbox_to_anchor=(1, 1.08))
axes[2].plot(t, gapped(series(['comp', 'events'])), lw=0.8, color=RED, label='diversion events in store'); axes[2].plot(t, gapped(series(['comp', 'eventMembers'])), lw=0.8, color=AMBER, label='event members')
axes[2].set_ylabel('entries'); axes[2].legend(loc='upper right', ncol=2, fontsize=7.5, bbox_to_anchor=(1, 1.08))
restarts = [t[i] for i in range(1, len(rows)) if rows[i]['up'] < rows[i-1]['up']]
for ax in axes:
    for r in restarts: ax.axvline(r, color=LIGHT, lw=0.6)
axes[-1].tick_params(axis='x', rotation=30)
fig.tight_layout(); save(fig, 'fig-9-1-health')
rss = sorted(series(['mem', 'rssMB'])); heap = sorted(series(['mem', 'heapUsedMB'])); vs = sorted(v for v in series(['comp', 'vehicleStates']) if v)
put(health_samples=len(rows), health_first=str(t[0].date()), health_last=str(t[-1].date()), health_restarts=len(restarts),
    rss_mb_p50=rss[len(rss)//2], rss_mb_max=rss[-1], heap_mb_p50=heap[len(heap)//2], vehicle_states_p50=vs[len(vs)//2],
    restart_days=sorted({r.strftime('%m-%d') for r in restarts}))
print(len(rows), 'samples', len(restarts), 'restarts', sorted({r.strftime('%m-%d') for r in restarts}))
