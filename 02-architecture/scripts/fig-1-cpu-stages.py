#!/usr/bin/env python3
"""Main-thread CPU per 15 s bus poll by stage, pollers only vs with one viewer (profiled run)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
c = json.load(open(os.path.join(DATA, 'cpu-profile-summary.json')))
W = c['windows']; quiet = next(v for k, v in W.items() if k.startswith('quiet')); viewer = next(v for k, v in W.items() if k.startswith('viewer'))
def table(w): return {s['stage']: s['cpu_ms_per_15s_bus_poll'] for s in w['stages'] if s['stage'] != 'idle'}
q, v = table(quiet), table(viewer)
# group profiler rows into the document's stages
GROUPS = [
  ('1 Ingest: parse + table', ['BODS parse + vehicle table', 'upstream body: UTF-8 decode to string (BODS XML)']),
  ('1 Ingest: HTTP client + I/O glue', ['upstream fetch: undici client', 'node I/O glue: TLS, sockets, streams, zlib bindings']),
  ('1 Ingest: JSON.parse (trains, rail, tides)', ['upstream body: JSON.parse (TfL, Darwin, EA)']),
  ('3 Detection: leaderboard sampling', ['leaderboard sampling']),
  ('3 Detection: diversion detector', ['diversion detector']),
  ('3 Detection: status + disruption shaping', ['status + disruption shaping']),
  ('4 Persist: trace writer', ['trace writer']),
  ('5 Serve: routes, serialise, compress', ['serve: routes, serialise, compress (main thread)', 'logging (pino)']),
  ('Runtime: garbage collection', ['GC']),
  ('Runtime: native outside JS', ['(program): native code outside JS']),
  ('Other (AIS, tides, measurement)', ['AIS stream', 'tide gauges', 'measurement overhead (preload)']),
]
labels = [g for g, _ in GROUPS]; qa = [sum(q.get(k, 0) for k in ks) for _, ks in GROUPS]; va = [sum(v.get(k, 0) for k in ks) for _, ks in GROUPS]
fig, ax = plt.subplots(figsize=(7.2, 4.0)); y = range(len(labels))
ax.barh([i + 0.2 for i in y], qa, 0.4, color=INK, label=f"pollers only ({sum(qa):.0f} ms per 15 s)")
ax.barh([i - 0.2 for i in y], va, 0.4, color=RED, label=f"with one viewer ({sum(va):.0f} ms per 15 s)")
ax.set_yticks(list(y)); ax.set_yticklabels(labels, fontsize=8); ax.invert_yaxis(); ax.set_xlabel('main-thread CPU, ms per 15 s bus poll (profiled run)')
for i, (a, b) in enumerate(zip(qa, va)):
    ax.text(max(a, b) + 0.8, i, f"{a:.0f} / {b:.0f}", va='center', fontsize=7.2, color=INK)
ax.set_xlim(0, max(va) * 1.22); ax.legend(loc='lower right'); fig.tight_layout(); save(fig, 'fig-1-cpu-stages')
put(cpu_ms_ingest_total=round(qa[0] + qa[1] + qa[2], 1), cpu_ms_detection_total=round(qa[3] + qa[4] + qa[5], 1), cpu_ms_runtime_total=round(qa[8] + qa[9], 1), cpu_ms_viewer_delta=round(sum(va) - sum(qa), 1),
    cpu_ms_rest=round(sum(qa) - (qa[0] + qa[1] + qa[2]) - (qa[3] + qa[4] + qa[5]) - qa[6] - qa[7], 1))  # GC + native + other: main-thread time not attributed to a stage
