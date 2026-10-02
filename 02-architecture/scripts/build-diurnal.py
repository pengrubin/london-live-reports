#!/usr/bin/env python3
"""24-hour calibration: hourly aggregates from the unprofiled replica run (data-24h/) and the
10-minute production endpoint samples. Writes data-24h/diurnal.json and d24_* numbers."""
import json, os, sys, statistics as st, datetime as dt
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import put, ROOT
D = os.path.join(ROOT, 'data-24h')
WARMUP_MS = 120_000
# --- replica process metrics: cumulative CPU -> ms per 15 s, heap, rss
rows = [json.loads(l) for l in open(f'{D}/proc-metrics.jsonl') if l.strip()]
proc = [r for r in rows if r.get('kind') == 'proc']
proc.sort(key=lambda r: r['at']); t0 = proc[0]['at']
cpu = []  # (at, ms per 15 s)
for a, b in zip(proc, proc[1:]):
    dtms = b['at'] - a['at']
    if dtms <= 0 or b['sinceStartMs'] < WARMUP_MS: continue
    dcpu = (b['cpuUserUs'] + b['cpuSystemUs'] - a['cpuUserUs'] - a['cpuSystemUs']) / 1000
    cpu.append((b['at'], dcpu / dtms * 15000, b['heapUsed'] / 1e6, b['rss'] / 1e6))
# --- upstream wire bytes per 30 s flush: BODS and TfL arrivals
ups = [r for r in rows if r.get('kind') == 'upstream']
wire = []
for r in ups:
    bods = next((v for k, v in r['byKey'].items() if 'bus-data.dft' in k), None)
    arr = next((v for k, v in r['byKey'].items() if 'Arrivals' in k), None)
    wire.append((r['at'], bods['wireBytes'] / max(1, bods['completed']) if bods and bods['completed'] else None,
                 arr['wireBytes'] / max(1, arr['completed']) if arr and arr['completed'] else None))
# --- per-poll log: live vehicles, parse ms
polls = []; poll_errors = 0
for l in open(f'{D}/bods-polls.jsonl'):
    r = json.loads(l); m = r['msg'].split()
    if m[2].isdigit(): polls.append((r['time'], int(m[2]), int(m[5])))
    else: poll_errors += 1  # 'BODS poll error: ...' - upstream failure, last good table kept
# --- production endpoint samples
eps = [json.loads(l) for l in open(f'{D}/endpoint-samples.jsonl')]
def hour(ms): return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime('%Y-%m-%dT%H')
def by_hour(rows, key_at, fields):
    out = {}
    for r in rows:
        h = hour(key_at(r)); out.setdefault(h, []).append(r)
    res = {}
    for h, rs in sorted(out.items()):
        res[h] = {name: round(st.median([f(r) for r in rs if f(r) is not None]), 2) for name, f in fields.items() if any(f(r) is not None for r in rs)}
        res[h]['n'] = len(rs)
    return res
hours = {}
for h, v in by_hour(cpu, lambda r: r[0], {'cpu_ms_per_15s': lambda r: r[1], 'heap_mb': lambda r: r[2], 'rss_mb': lambda r: r[3]}).items(): hours.setdefault(h, {}).update(v)
for h, v in by_hour(wire, lambda r: r[0], {'bods_wire_kb': lambda r: r[1] / 1000 if r[1] else None, 'arrivals_wire_kb': lambda r: r[2] / 1000 if r[2] else None}).items(): hours.setdefault(h, {}).update({k: x for k, x in v.items() if k != 'n'})
for h, v in by_hour(polls, lambda r: r[0], {'live_vehicles': lambda r: r[1], 'parse_ms': lambda r: r[2]}).items(): hours.setdefault(h, {}).update({k: x for k, x in v.items() if k != 'n'})
for h, v in by_hour(eps, lambda r: r['t'] * 1000, {'prod_buses': lambda r: r['buses'].get('n'), 'prod_buses_br_kb': lambda r: r['buses']['wire'] / 1000 if r['buses']['wire'] else None,
        'prod_predictions': lambda r: r['arrivals'].get('n'), 'prod_arrivals_br_kb': lambda r: r['arrivals']['wire'] / 1000 if r['arrivals']['wire'] else None,
        'prod_bus_age_p50': lambda r: (r['buses'].get('age') or {}).get('p50'), 'prod_vessels': lambda r: r['vessels'].get('n'), 'prod_aircraft': lambda r: r['aircraft'].get('n')}).items(): hours.setdefault(h, {}).update({k: x for k, x in v.items() if k != 'n'})
# full hours only (both replica and production present)
full = {h: v for h, v in hours.items() if v.get('n', 0) >= 100 and 'live_vehicles' in v and 'prod_predictions' in v}
json.dump({'measurement': '24-hour replica run + 10-minute production samples', 'window_utc': [hour(proc[0]['at']), hour(proc[-1]['at'])], 'hours': hours}, open(f'{D}/diurnal.json', 'w'), indent=1)
# --- summary numbers
cpu_vals = [c[1] for c in cpu]; lv = [p[1] for p in polls if p[0] - t0 > WARMUP_MS]; pm = [p[2] for p in polls if p[0] - t0 > WARMUP_MS]
hr = sorted(full.items())
def ext(key, fn): 
    vals = [(h, v[key]) for h, v in hr if key in v]; return fn(vals, key=lambda x: x[1])
hi_v, lo_v = ext('live_vehicles', max), ext('live_vehicles', min)
hi_c, lo_c = ext('cpu_ms_per_15s', max), ext('cpu_ms_per_15s', min)
hi_p, lo_p = ext('prod_predictions', max), ext('prod_predictions', min)
hi_w, lo_w = ext('bods_wire_kb', max), ext('bods_wire_kb', min)
put(d24_hours=len(full), d24_start=hour(proc[0]['at']).replace('T', ' ') + ':00 UTC', d24_end=hour(proc[-1]['at']).replace('T', ' ') + ':00 UTC',
    d24_cpu_mean_ms=round(st.mean(cpu_vals), 1), d24_cpu_p5_ms=round(sorted(cpu_vals)[int(.05 * len(cpu_vals))], 1), d24_cpu_p95_ms=round(sorted(cpu_vals)[int(.95 * len(cpu_vals))], 1),
    d24_cpu_util_pct=round(100 * st.mean(cpu_vals) / 15000, 2), d24_cpu_hour_max_ms=round(hi_c[1], 1), d24_cpu_hour_min_ms=round(lo_c[1], 1), d24_cpu_hour_ratio=round(hi_c[1] / lo_c[1], 2),
    d24_live_max=int(hi_v[1]), d24_live_max_hour=hi_v[0][-2:] + ':00', d24_live_min=int(lo_v[1]), d24_live_min_hour=lo_v[0][-2:] + ':00', d24_live_ratio=round(hi_v[1] / lo_v[1], 1),
    d24_parse_ms_median=round(st.median(pm), 1), d24_parse_ms_p95=round(sorted(pm)[int(.95 * len(pm))], 1),
    d24_bods_wire_kb_max=round(hi_w[1]), d24_bods_wire_kb_min=round(lo_w[1]), d24_bods_wire_ratio=round(hi_w[1] / lo_w[1], 2),
    d24_pred_max=int(hi_p[1]), d24_pred_max_hour=hi_p[0][-2:] + ':00', d24_pred_min=int(lo_p[1]), d24_pred_min_hour=lo_p[0][-2:] + ':00',
    d24_heap_min_mb=round(min(c[2] for c in cpu)), d24_heap_max_mb=round(max(c[2] for c in cpu)), d24_rss_max_mb=round(max(c[3] for c in cpu)),
    d24_bus_age_p50_min=min(v['prod_bus_age_p50'] for h, v in hr if 'prod_bus_age_p50' in v), d24_bus_age_p50_max=max(v['prod_bus_age_p50'] for h, v in hr if 'prod_bus_age_p50' in v),
    d24_polls=len(polls), d24_poll_errors=poll_errors, d24_prod_samples=len(eps))
print(len(full), 'full hours;', 'cpu mean', round(st.mean(cpu_vals), 1), 'ms/15s; live', lo_v, hi_v, '; cpu hours', lo_c, hi_c, '; wire', lo_w, hi_w, '; pred', lo_p, hi_p)

# --- what drives CPU over the day: least squares of CPU per 15 s on live vehicles and uptime
import bisect
pt = [p[0] for p in polls]
X, Y, Xp, Yp = [], [], [], []
for at, ms, heap, rss in cpu:
    i = bisect.bisect_left(pt, at); i = min(max(i - 1, 0), len(polls) - 1)
    if abs(polls[i][0] - at) > 60_000: continue
    X.append((1.0, polls[i][1], (at - t0) / 3.6e6)); Y.append(ms)
for at, live, pms in polls:
    if at - t0 > WARMUP_MS: Xp.append((1.0, live)); Yp.append(pms)
def ols(X, Y):
    import itertools
    n, k = len(X), len(X[0])
    # normal equations via Gaussian elimination (no numpy dependency)
    A = [[sum(x[i] * x[j] for x in X) for j in range(k)] for i in range(k)]; b = [sum(x[i] * y for x, y in zip(X, Y)) for i in range(k)]
    for i in range(k):
        piv = max(range(i, k), key=lambda r: abs(A[r][i])); A[i], A[piv] = A[piv], A[i]; b[i], b[piv] = b[piv], b[i]
        for r in range(k):
            if r != i:
                f = A[r][i] / A[i][i]; A[r] = [a - f * c for a, c in zip(A[r], A[i])]; b[r] -= f * b[i]
    beta = [b[i] / A[i][i] for i in range(k)]
    yhat = [sum(bb * xx for bb, xx in zip(beta, x)) for x in X]; ybar = sum(Y) / n
    r2 = 1 - sum((y - h) ** 2 for y, h in zip(Y, yhat)) / sum((y - ybar) ** 2 for y in Y)
    return beta, r2
(b0, b1, b2), r2 = ols(X, Y); (p0, p1), r2p = ols(Xp, Yp)
(c0, c1), r2c = ols([(x[0], x[1]) for x in X], Y)
put(d24_cpu_fit_fixed_ms=round(b0), d24_cpu_fit_us_per_live=round(b1 * 1000, 1), d24_cpu_fit_ms_per_uptime_h=round(b2, 1), d24_cpu_fit_r2=round(r2, 2),
    d24_cpu_fit_live_only_fixed_ms=round(c0), d24_cpu_fit_live_only_us_per_live=round(c1 * 1000, 1), d24_cpu_fit_live_only_r2=round(r2c, 2),
    d24_parse_fit_fixed_ms=round(p0, 1), d24_parse_fit_us_per_live=round(p1 * 1000, 1), d24_parse_fit_r2=round(r2p, 2), d24_cpu_fit_n=len(Y))
print('cpu = %.0f + %.1f us/live + %.1f ms/h uptime, R2 %.2f (live only: %.0f + %.1f us, R2 %.2f); parse = %.1f + %.1f us/live, R2 %.2f' % (b0, b1 * 1000, b2, r2, c0, c1 * 1000, r2c, p0, p1 * 1000, r2p))
