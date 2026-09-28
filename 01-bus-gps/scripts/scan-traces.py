#!/usr/bin/env python3
"""One streaming pass over a day of bus GPS traces -> one JSON of histograms.

Input : <archive>/bus-traces/YYYY-MM-DD.jsonl.gz, lines {"k","i","x","y","t"}
        (k = OPERATOR:line:direction, i = OPERATOR:vehicleRef, t = epoch s),
        appended in poll order, so per-vehicle "last fix" state is enough.
Output: data/daily/YYYY-MM-DD.json with per-day totals and histograms.
        Every figure in section 2 and 4 of the report is drawn from these files;
        the raw traces are never read twice.

Definitions (must match backend/src/rollup-writer.ts and learn-bus-routes.mjs):
  journey split gap  600 s      complete journey: >=15 fixes, >=2000 m, >=480 s
  speed pairs        5 s <= dt <= 60 s, speed <= 40 m/s (else GPS glitch)

Usage: scan-traces.py <archive> <out_dir> <day>...   (one process per day)
"""
import gzip, json, math, sys, os
from collections import defaultdict

SPLIT_GAP_S = 600
J_MIN_FIXES, J_MIN_LEN_M, J_MIN_DUR_S = 15, 2000, 480
SPEED_MIN_DT, SPEED_MAX_DT, SPEED_MAX_MS = 5, 60, 40.0
M_LAT = 110_540.0
M_LON = 111_320.0 * math.cos(math.radians(51.5))

def dist_m(x1, y1, x2, y2):
    return math.hypot((x2 - x1) * M_LON, (y2 - y1) * M_LAT)

def scan(archive, out_dir, day):
    path = os.path.join(archive, 'bus-traces', f'{day}.jsonl.gz')
    last = {}                      # vehicle -> (t, x, y)
    jour = {}                      # vehicle -> [key, n, len_m, t0, t1]
    dt_hist = defaultdict(int)     # seconds (capped 900) -> count
    speed_hist = defaultdict(int)  # 0.5 m/s bins -> count
    fix_per_veh = defaultdict(int)
    minute_veh = defaultdict(set)  # minute-of-day -> vehicles with a fix
    op_fixes = defaultdict(int); op_veh = defaultdict(set); keys = set()
    journeys = []                  # closed journeys: (operator, n, len_m, dur_s)
    n_lines = n_bad = 0

    def close(v):
        j = jour.pop(v, None)
        if j: journeys.append((v.split(':', 1)[0], j[1], j[2], j[4] - j[3]))

    with gzip.open(path, 'rt') as f:
        for line in f:
            n_lines += 1
            try:
                r = json.loads(line)
                k, v, x, y, t = r['k'], r['i'], float(r['x']), float(r['y']), int(r['t'])
            except Exception:
                n_bad += 1; continue
            op = v.split(':', 1)[0]
            op_fixes[op] += 1; op_veh[op].add(v); keys.add(k); fix_per_veh[v] += 1
            minute_veh[(t // 60) % 1440].add(v)
            prev = last.get(v)
            if prev is not None:
                dt = t - prev[0]
                if dt >= 0:
                    dt_hist[min(dt, 900)] += 1
                    ds = dist_m(prev[1], prev[2], x, y)
                    if SPEED_MIN_DT <= dt <= SPEED_MAX_DT:
                        sp = ds / dt
                        if sp <= SPEED_MAX_MS: speed_hist[int(sp / 0.5)] += 1
                        else: speed_hist['glitch'] += 1
                    j = jour.get(v)
                    if j is None or dt > SPLIT_GAP_S or j[0] != k:
                        close(v); jour[v] = [k, 1, 0.0, t, t]
                    else:
                        j[1] += 1; j[2] += ds if dt <= SPLIT_GAP_S else 0.0; j[4] = t
            else:
                jour[v] = [k, 1, 0.0, t, t]
            last[v] = (t, x, y)
    for v in list(jour): close(v)

    def hist(vals, edges):
        h = [0] * (len(edges))
        for x in vals:
            i = 0
            while i < len(edges) - 1 and x >= edges[i + 1]: i += 1
            h[i] += 1
        return {'edges': edges, 'counts': h}

    complete = [j for j in journeys if j[1] >= J_MIN_FIXES and j[2] >= J_MIN_LEN_M and j[3] >= J_MIN_DUR_S]
    def jstats(js):
        if not js: return {'n': 0}
        L = sorted(j[2] for j in js); D = sorted(j[3] for j in js); N = sorted(j[1] for j in js)
        q = lambda a, p: a[min(len(a) - 1, int(p * len(a)))]
        return {'n': len(js), 'len_m_p50': q(L, .5), 'len_m_p90': q(L, .9), 'dur_s_p50': q(D, .5),
                'dur_s_p90': q(D, .9), 'fixes_p50': q(N, .5)}
    by_op = lambda js, tflo: [j for j in js if (j[0] == 'TFLO') == tflo]
    out = {
        'day': day, 'lines': n_lines, 'malformed': n_bad,
        'vehicles': len(fix_per_veh), 'keys': len(keys),
        'operators': {op: {'fixes': op_fixes[op], 'vehicles': len(op_veh[op])} for op in op_fixes},
        'dt_hist': {str(k): c for k, c in sorted(dt_hist.items())},
        'speed_hist': {str(k): c for k, c in speed_hist.items()},
        'fixes_per_vehicle_hist': hist(fix_per_veh.values(), [0, 50, 100, 200, 400, 800, 1200, 1600, 2400, 4000]),
        'vehicles_per_minute': [len(minute_veh[m]) for m in range(1440)],
        'journeys': {
            'all': jstats(journeys), 'complete': jstats(complete),
            'tflo_all': jstats(by_op(journeys, True)), 'tflo_complete': jstats(by_op(complete, True)),
            'other_all': jstats(by_op(journeys, False)), 'other_complete': jstats(by_op(complete, False)),
            'len_hist': hist([j[2] for j in journeys], [0, 500, 1000, 2000, 4000, 8000, 12000, 16000, 24000, 40000]),
            'dur_hist': hist([j[3] for j in journeys], [0, 120, 480, 900, 1800, 2700, 3600, 5400, 7200, 14400]),
        },
    }
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, f'{day}.json.part')
    with open(tmp, 'w') as f: json.dump(out, f)
    os.replace(tmp, os.path.join(out_dir, f'{day}.json'))
    print(day, 'lines', n_lines, 'vehicles', len(fix_per_veh), 'journeys', len(journeys), flush=True)

if __name__ == '__main__':
    archive, out_dir, *days = sys.argv[1:]
    for d in days:
        if os.path.exists(os.path.join(out_dir, f'{d}.json')): print(d, 'exists'); continue
        scan(archive, out_dir, d)
