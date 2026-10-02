#!/usr/bin/env python3
"""Classify each poll's TfL `timestamp` against the previous poll, per line, to separate true
replays from bodies that went BACKWARDS in time (an older body served after a newer one).
analyze-arrivals.py's ts_interval histogram clamps negatives into its 0 s bin, so it cannot tell.

Per (line, poll) the first row's timestamp is compared with that line's newest timestamp so far:
  same      identical string (replay)
  back      older than the newest seen (stale body served after a fresher one)
  sub1      newer by < 1 s
  fwd       newer by >= 1 s  (a genuinely new snapshot); interval recorded
Also counts polls whose rows within one line carry more than one distinct timestamp.
Usage: check-timestamps.py --out data/arrivals-timestamps.json FILE...
"""
import argparse, calendar, gzip, json, re, zlib
from collections import Counter, defaultdict
TS_RE = re.compile(r'^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.(\d+))?Z$')
def parse(s):
    m = TS_RE.match(s or '')
    if not m: return None
    y, mo, d, h, mi, se, fr = m.groups()
    return calendar.timegm((int(y), int(mo), int(d), int(h), int(mi), int(se))) + (float('0.' + fr) if fr else 0.0)
ap = argparse.ArgumentParser(); ap.add_argument('files', nargs='+'); ap.add_argument('--out', required=True); a = ap.parse_args()
cls, back_by, fwd_iv, multi, newest = Counter(), Counter(), Counter(), Counter(), {}
poll_cls, polls = Counter(), 0
for path in a.files:
    with gzip.open(path, 'rt') as f:
        try:
            for line in f:
                try: rec = json.loads(line)
                except Exception: continue
                if 'p' not in rec: continue
                polls += 1; per = defaultdict(set); first = {}
                for r in rec['p']:
                    per[r[1]].add(r[10]); first.setdefault(r[1], r[10])
                kinds = Counter()
                for ln, ts in first.items():
                    if len(per[ln]) > 1: multi[ln] += 1
                    t = parse(ts)
                    if t is None: continue
                    prev = newest.get(ln)
                    if prev is None: newest[ln] = t; continue
                    d = t - prev
                    k = 'same' if d == 0 else 'back' if d < 0 else 'sub1' if d < 1 else 'fwd'
                    cls[k] += 1; kinds[k] += 1
                    if k == 'back': back_by[min(300, int(-d // 5 * 5))] += 1
                    if k == 'fwd': fwd_iv[min(300, int(d // 5 * 5))] += 1; newest[ln] = t
                    if k == 'sub1': newest[ln] = t
                # poll-level: fresh if any line moved forward >= 1 s
                poll_cls['fresh' if kinds['fwd'] else 'back' if kinds['back'] else 'replay'] += 1
        except (EOFError, gzip.BadGzipFile, zlib.error):
            pass
n = sum(cls.values()); nf = sum(fwd_iv.values())
mean_fwd = sum(k * v for k, v in fwd_iv.items()) / nf + 2.5 if nf else None
out = {'files': a.files, 'polls': polls, 'line_polls': dict(cls), 'line_polls_pct': {k: round(100 * v / n, 2) for k, v in cls.items()},
       'poll_class': dict(poll_cls), 'back_by_s': dict(sorted(back_by.items())), 'fwd_interval_s': dict(sorted(fwd_iv.items())),
       'fwd_interval_mean_s': round(mean_fwd, 1) if mean_fwd else None, 'multi_ts_line_polls': dict(multi)}
json.dump(out, open(a.out, 'w'), indent=1)
print(json.dumps({k: out[k] for k in ('polls', 'line_polls_pct', 'poll_class', 'fwd_interval_mean_s')}))
