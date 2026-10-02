#!/usr/bin/env python3
"""Feed-quality and self-consistency metrics for the recorded TfL Arrivals predictions.

Input : ~/bus-archive/arrivals/YYYY-MM-DD.jsonl.gz written by arrivals-sampler.mjs:
        one line per poll, {"t": epoch_s, "n": rows, "p": [[id, lineId, vehicleId,
        naptanId, timeToStation, currentLocation, towards, destinationNaptanId,
        platformName, direction, timestamp], ...]} or {"t", "error"}; each line is
        its own gzip member. ~9 000 rows per poll, one poll every 30 s.
Output: data/arrivals-metrics.json (every histogram and table, read by fig-*.py)
        and data/arrivals/m01-..m12-*.csv (one CSV per metric).

There is no ground truth for train positions, so every metric is a property of
the feed itself or a consistency check between what the feed said earlier and
what it said later. The identity rules (train key, S-stock groups, DLR leading
edge, 480 s horizon) are ported from frontend/src/realtime/position-inference.ts
so the metrics exercise the rules the map actually runs.

One streaming pass; memory is bounded by the live prediction set (state per
train and per (train, station) track, closed after MAX_ABSENT_POLLS absent
polls). Only polls whose TfL `timestamp` moved FORWARD (per line) are compared: an
unchanged timestamp replays the previous body, and an older one (~10% of line-polls,
see check-timestamps.py) is a stale body served after a fresher one. Both count as
stale; `back` counts the older ones separately.

Usage: analyze-arrivals.py [--branches DIR] [--out DIR] FILE...
  --branches  london-live-2d/data/branches: station names (for the "At <own
              stop>" arrival rule) and the DLR stop graph (leading-edge
              replication). Without it, names are learned from the feed ("At X"
              rows with countdown <= 15 s, majority vote, persisted to
              data/arrivals/naptan-names.json) and the DLR metric only reports
              rows per (direction, destination) group.
"""
import argparse, calendar, csv, glob, gzip, json, math, os, re, sys, zlib, zoneinfo, datetime as dt
from collections import Counter, defaultdict

ID, LINE, VID, NAPTAN, TTS, LOC, TOWARDS, DEST, PLAT, DIR, TS = range(11)

# ── constants mirrored from position-inference.ts / interpolator.ts ──
RUN_HORIZON_S = 480      # position-less prediction beyond this is timetable, not live
AT_PLATFORM_S = 15       # countdown at or below this = at the platform
NO_VEHICLE_ID = '000'
SIDINGS = re.compile(r'sidings?\b|depot', re.I)
STOCK_GROUP = {**{l: 'sub' for l in ('district', 'circle', 'hammersmith-city', 'metropolitan')},
               **{l: 'og' for l in ('mildmay', 'windrush', 'weaver', 'lioness', 'suffragette', 'liberty')}}
# ── analysis constants ──
MAX_ABSENT_POLLS = 4     # track closed after this many fresh polls without the row (2 min)
GONE_POLLS = 10          # train closed after this many fresh polls absent (5 min): flicker vs gone
MAX_POLL_GAP_S = 90      # sampler gap: everything is closed as censored, nothing counts as flicker
REACHED_S = 45           # last countdown at or below this when a row vanishes = the train got there
STALL_S = 10             # countdown advanced >10 s less than the clock between polls = stalled
QUEUE_MATCH_S = 150      # half the 300 s spacing TfL uses between queued DLR trains at one stop
HORIZONS = [30, 60, 120, 180, 300, 480, 600, 900, 1200, 1800, 3600, 7200]  # accuracy buckets (s)
TTS_EDGES = [0, 15, 30, 60, 120, 240, 480, 900, 1800, 3600, 7200]
TUBE = {'bakerloo', 'central', 'circle', 'district', 'hammersmith-city', 'jubilee', 'metropolitan',
        'northern', 'piccadilly', 'victoria', 'waterloo-city'}
OVERGROUND = {'liberty', 'lioness', 'mildmay', 'suffragette', 'weaver', 'windrush'}
LONDON = zoneinfo.ZoneInfo('Europe/London')
COV_BIN_MIN = 10

def mode_of(line):
    if line in TUBE: return 'tube'
    if line in OVERGROUND: return 'overground'
    return line if line in ('dlr', 'elizabeth', 'tram') else 'other'

# ── currentLocation vocabulary ──
LOC_CLASSES = [('at', re.compile(r'^\s*at\s+', re.I)), ('between', re.compile(r'^\s*between\s+', re.I)),
               ('approaching', re.compile(r'^\s*approaching\s+', re.I)), ('left', re.compile(r'^\s*left\s+', re.I)),
               ('leaving', re.compile(r'^\s*leaving\s+', re.I)), ('departed', re.compile(r'^\s*departed\s+', re.I))]
DEPARTED_INFERENCE = {'between', 'left'}                       # what DEPARTED in the inference matches
DEPARTED_ANY = DEPARTED_INFERENCE | {'leaving', 'departed'}    # what the feed actually says
NAMED = re.compile(r'^\s*(?:at|approaching)\s+(.+)$', re.I)

def loc_class(loc):
    if not loc or not loc.strip(): return 'empty'
    if SIDINGS.search(loc): return 'sidings'
    for cls, rx in LOC_CLASSES:
        if rx.match(loc): return cls
    return 'other'

def norm_station(name):
    """Port of normStation(): tolerant station-name equality."""
    s = name.lower()
    s = re.sub(r'\s+(underground|dlr|rail)?\s*station\b.*$', ' ', s)
    s = re.sub(r'\s+platform\b.*$', ' ', s)
    s = re.sub(r"['`‘’]", '', s)
    s = re.sub(r'[.\-_/]', ' ', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def train_key(row):
    """Port of the identity collapse in inferTrains(): (key, kind)."""
    vid, line, loc = row[VID], row[LINE], row[LOC]
    if vid and vid != NO_VEHICLE_ID: return f'{line}:{vid}', 'vid'
    if loc.strip() and not SIDINGS.search(loc): return f'{line}|{loc}|{row[DIR]}', 'loc'
    if line == 'dlr': return f'dlr:{row[DIR]}|{row[DEST]}|{row[NAPTAN]}', 'dlr'
    return f'{line}:tt:{row[DEST]}:{row[NAPTAN]}', 'tt'

TS_RE = re.compile(r'^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.(\d+))?Z$')
def parse_ts(s, cache):
    v = cache.get(s)
    if v is None:
        m = TS_RE.match(s or '')
        if not m: return None
        y, mo, d, h, mi, se, fr = m.groups()
        v = calendar.timegm((int(y), int(mo), int(d), int(h), int(mi), int(se))) + (float('0.' + fr) if fr else 0.0)
        cache[s] = v
    return v

class Hist:
    """Fixed-width histogram, tails clamped to [lo, hi]; quantiles read from the bins (bin start,
    or bin centre for a `centered` histogram whose bins straddle multiples of w — used for signed
    residuals so that a value of -0.3 s lands in the 0 bin, not the -5 bin)."""
    __slots__ = ('w', 'lo', 'hi', 'c', 'n', 's', 'off')
    def __init__(self, w, lo, hi, centered=False):
        self.w, self.lo, self.hi, self.c, self.n, self.s, self.off = w, lo, hi, defaultdict(int), 0, 0.0, (0.5 if centered else 0.0)
    def add(self, x):
        self.n += 1; self.s += x
        self.c[int(math.floor(min(self.hi, max(self.lo, x)) / self.w + self.off)) * self.w] += 1
    def q(self, p):
        cum = 0
        for k in sorted(self.c):
            cum += self.c[k]
            if cum >= p * self.n: return k
        return None
    def summary(self):
        if not self.n: return {'n': 0}
        return {'n': self.n, 'mean': round(self.s / self.n, 2), 'p10': self.q(.1), 'p50': self.q(.5), 'p90': self.q(.9),
                'w': self.w, 'bins': {str(k): v for k, v in sorted(self.c.items())}}

class EdgeHist:
    __slots__ = ('edges', 'c')
    def __init__(self, edges): self.edges, self.c = edges, [0] * len(edges)
    def add(self, x):
        i = 0
        while i < len(self.edges) - 1 and x >= self.edges[i + 1]: i += 1
        self.c[i] += 1
    def summary(self): return {'edges': self.edges, 'counts': self.c}

def new_line_stats():
    return {'polls': 0, 'fresh': 0, 'stale': 0, 'back': 0, 'rows': 0, 'rows_max': 0, 'trains_sum': 0, 'trains_max': 0,
            'age': Hist(1, 0, 300), 'ts_interval': Hist(1, 0, 300),
            'vid_missing': 0, 'vid_000': 0, 'vocab': Counter(), 'other_loc': Counter(),
            'tts_log': EdgeHist(TTS_EDGES), 'tt_rows': 0, 'posless_rows': 0, 'undeparted': 0, 'train_obs': 0,
            'pairs': 0, 'regress': 0, 'stall': 0, 'id_changes': 0, 'dup_listings': 0,
            'flicker': Counter(), 'vid_obs': 0, 'gone': 0, 'life': defaultdict(lambda: Hist(1, 0, 600)),
            'ktype': Counter(), 'first_tts': Hist(30, 0, 7200), 'dep_tts': Hist(5, 0, 1200),
            'at_own': Hist(5, 0, 300), 'app_own': Hist(5, 0, 300), 'near_mix': Counter(), 'dep_vocab': Counter()}

class Track:
    """One (train, station) prediction followed across polls."""
    __slots__ = ('id', 'tts', 'teff', 'idx', 'n', 'hz', 'at_t', 'first_tts')
    def __init__(self, row, teff, idx):
        self.id, self.tts, self.teff, self.idx, self.n = row[ID], row[TTS], teff, idx, 1
        self.hz, self.at_t, self.first_tts = {}, None, row[TTS]

class Analyzer:
    def __init__(self, names, dlr_prev):
        self.names, self.dlr_prev = names, dlr_prev
        self.votes = defaultdict(Counter)              # naptan -> name -> votes (learned station names)
        self.lines = defaultdict(new_line_stats)
        self.tracks = defaultdict(dict)                # line -> (key, naptan) -> Track  (vehicleId / location keys)
        self.queues = defaultdict(dict)                # line -> stop key -> [Track]      (DLR / timetable keys)
        self.trains = defaultdict(dict)                # line -> key -> [first_idx, last_idx, n, cls, kind]
        self.prev_ts, self.prev_teff, self.prev_t = {}, {}, None
        self.polls = self.err_polls = self.stale_polls = self.back_polls = 0
        self.gap_hist = Hist(1, 0, 600)
        self.cov = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))   # line -> bin -> [polls, rows, max trains]
        self.cov_polls = defaultdict(Counter)          # bin -> {'fresh','stale','error'}
        self.resid = defaultdict(lambda: Hist(5, -300, 300, centered=True))            # mode -> residual hist
        self.acc = defaultdict(lambda: defaultdict(lambda: Hist(10, -1200, 1200, centered=True)))  # mode -> horizon -> error hist
        self.acc_rule = defaultdict(Counter)           # mode -> {'at','reached','censored'}
        self.track_life = defaultdict(lambda: Hist(5, 0, 600))
        self.stock = defaultdict(lambda: defaultdict(dict))             # group -> vid -> line -> min tts
        self.stock_stats = defaultdict(lambda: {'polls': 0, 'vids': 0, 'dup': 0, 'pairs': Counter(), 'margin': Hist(30, 0, 3600)})
        self.dlr = {'polls': 0, 'rows': 0, 'rows_le_h': 0, 'keys_le_h': 0, 'leads': 0, 'groups': 0,
                    'rows_per_lead': Hist(0.5, 0, 20), 'rows_per_group': Hist(1, 0, 60)}
        self.days = {}
        self.day_hours = defaultdict(lambda: defaultdict(Counter))   # UTC day -> local hour -> fresh/stale/error
        self.gaps = []                                 # sampler gaps > MAX_POLL_GAP_S: [epoch_s, seconds]

    # ── station-name learning (when no baked branches are given) ──
    def vote(self, naptan, name):
        v = self.votes[naptan]; v[name] += 1
        if naptan not in self.names and v[name] >= 3: self.names[naptan] = name

    def own_station(self, row):
        """'at'/'approaching' when currentLocation names the row's own station, else None."""
        m = NAMED.match(row[LOC])
        if not m: return None
        own = self.names.get(row[NAPTAN])
        return loc_class(row[LOC]) if own and norm_station(m.group(1)) == own else None

    # ── one poll ──
    def poll(self, rec, day):
        t = rec['t']; d = self.days.setdefault(day, Counter()); d['polls'] += 1
        lbin = local_bin(t); dh = self.day_hours[day][lbin * COV_BIN_MIN // 60]
        if 'error' in rec or 'p' not in rec:
            self.err_polls += 1; d['errors'] += 1; self.cov_polls[lbin]['error'] += 1; dh['error'] += 1; return
        if self.prev_t is not None:
            gap = t - self.prev_t; self.gap_hist.add(gap)
            if gap > MAX_POLL_GAP_S: self.flush('gap'); self.gaps.append([self.prev_t, gap])
        self.prev_t = t; self.polls += 1; d['rows'] += len(rec['p'])
        by_line = defaultdict(list)
        for row in rec['p']: by_line[row[LINE]].append(row)
        tscache, any_fresh, any_back = {}, False, False
        for line, rows in by_line.items():
            L = self.lines[line]; L['polls'] += 1
            ts = rows[0][TS]
            if ts == self.prev_ts.get(line): L['stale'] += 1; continue   # cache replay of the previous body
            teff = parse_ts(ts, tscache)
            if teff is None: teff = float(t)
            if line in self.prev_teff and teff <= self.prev_teff[line]:
                # an OLDER body than one already seen (~10% of line-polls): not new information, and
                # comparing it would fake flickers (a train listed later is absent from an older snapshot)
                L['stale'] += 1; L['back'] += 1; any_back = True; continue
            if line in self.prev_teff: L['ts_interval'].add(teff - self.prev_teff[line])
            self.prev_ts[line], self.prev_teff[line] = ts, teff
            L['fresh'] += 1; L['age'].add(t - teff); any_fresh = True
            self.process_line(line, rows, teff, L['fresh'], lbin, L)
        self.cov_polls[lbin]['fresh' if any_fresh else 'stale'] += 1; dh['fresh' if any_fresh else 'stale'] += 1
        if not any_fresh:
            self.stale_polls += 1; d['stale'] += 1
            if any_back: self.back_polls += 1; d['back'] += 1
        self.eval_stock()

    def process_line(self, line, rows, teff, idx, lbin, L):
        mode = mode_of(line); best = {}; queues = {}
        L['rows'] += len(rows); L['rows_max'] = max(L['rows_max'], len(rows))
        for row in rows:
            self.row_stats(row, line, mode, L)
            key, kind = train_key(row); L['ktype'][kind] += 1
            if kind in ('vid', 'loc'):
                tk = (key, row[NAPTAN]); cur = best.get(tk)
                if cur is None: best[tk] = (row, kind)
                else:
                    L['dup_listings'] += 1     # same train listed twice at one stop (terminus platforms)
                    if row[TTS] < cur[0][TTS]: best[tk] = (row, kind)
            else:
                # DLR / timetable keys name the stop, and TfL lists the next several trains for it
                # (DLR: ~6 rows at 300 s spacing) — a queue, matched across polls below
                queues.setdefault(key, (kind, []))[1].append(row)
        tmin = {}
        for tk, (row, kind) in best.items():
            if tk[0] not in tmin or row[TTS] < tmin[tk[0]][0][TTS]: tmin[tk[0]] = (row, kind)
        for key, (kind, qrows) in queues.items(): tmin[key] = (min(qrows, key=lambda r: r[TTS]), kind)
        tracks = self.tracks[line]
        for tk, (row, kind) in best.items():
            tr = tracks.get(tk)
            if tr is None: tracks[tk] = self.new_track(row, teff, idx, L)
            else: self.observe(tr, row, teff, idx, L, mode, nearest=tmin[tk[0]][0] is row)
        for key, (kind, qrows) in queues.items(): self.match_queue(self.queues[line].setdefault(key, []), qrows, teff, idx, L, mode)
        L['trains_sum'] += len(tmin); L['trains_max'] = max(L['trains_max'], len(tmin))
        c = self.cov[line][lbin]; c[0] += 1; c[1] += len(rows); c[2] = max(c[2], len(tmin))
        for key, (row, kind) in tmin.items(): self.update_train(line, mode, key, kind, row, idx, L)
        if line == 'dlr': self.dlr_stats([r for kind, qrows in queues.values() if kind == 'dlr' for r in qrows])
        self.sweep(line, mode, idx, L)

    def row_stats(self, row, line, mode, L):
        tts, loc = row[TTS], row[LOC]
        if not row[VID]: L['vid_missing'] += 1
        elif row[VID] == NO_VEHICLE_ID: L['vid_000'] += 1
        cls = loc_class(loc); L['vocab'][cls] += 1
        if cls in ('other', 'sidings') and (loc in L['other_loc'] or len(L['other_loc']) < 200): L['other_loc'][loc] += 1
        L['tts_log'].add(tts)
        if cls == 'empty' and mode in ('overground', 'elizabeth'):
            L['posless_rows'] += 1
            if tts > RUN_HORIZON_S: L['tt_rows'] += 1
        if cls == 'at' and tts <= AT_PLATFORM_S and row[NAPTAN] not in self.names:
            self.vote(row[NAPTAN], norm_station(NAMED.match(loc).group(1)))
        if tts <= AT_PLATFORM_S:
            own = self.own_station(row) if cls in ('at', 'approaching') else None
            L['near_mix'][f'{cls}-own' if own else cls] += 1

    def new_track(self, row, teff, idx, L):
        tr = Track(row, teff, idx); L['first_tts'].add(row[TTS]); self.sample_horizon(tr, teff, row[TTS]); return tr

    def observe(self, tr, row, teff, idx, L, mode, nearest):
        """An existing (train, stop) track sees its row in a fresh poll."""
        tts = row[TTS]
        if teff > tr.teff:
            resid = (tr.tts - (teff - tr.teff)) - tts     # >0: countdown ran ahead of the clock; <0: stalled
            self.resid[mode].add(resid); L['pairs'] += 1
            if tts > tr.tts: L['regress'] += 1
            if resid < -STALL_S: L['stall'] += 1
        if row[ID] != tr.id: L['id_changes'] += 1
        tr.id, tr.tts, tr.teff, tr.idx, tr.n = row[ID], tts, teff, idx, tr.n + 1
        self.sample_horizon(tr, teff, tts)
        # "At <own stop>" counts as arrival only on the train's nearest stop, as in the inference:
        # a terminus/loop train is also listed for its NEXT call at the same station.
        if nearest and tr.at_t is None and self.own_station(row) == 'at': tr.at_t = teff

    @staticmethod
    def sample_horizon(tr, teff, tts):
        h = next((h for h in HORIZONS if tts <= h), None)   # bucket (prev edge, h]: first sample only
        if h is not None and h not in tr.hz: tr.hz[h] = (teff, tts)

    def match_queue(self, lst, qrows, teff, idx, L, mode):
        """Greedy continuity matching for a stop's queue: each new row takes the unmatched track whose
        countdown, advanced by the elapsed time, is nearest (within QUEUE_MATCH_S)."""
        free = list(lst)
        for row in sorted(qrows, key=lambda r: r[TTS]):
            pick = None
            for tr in free:
                d = abs(tr.tts - (teff - tr.teff) - row[TTS])
                if d < QUEUE_MATCH_S and (pick is None or d < pick[0]): pick = (d, tr)
            if pick: free.remove(pick[1]); self.observe(pick[1], row, teff, idx, L, mode, nearest=False)
            else: lst.append(self.new_track(row, teff, idx, L))

    def close_track(self, mode, tr, reason):
        self.track_life[mode].add(tr.n)
        if reason == 'gap': self.acc_rule[mode]['censored-gap'] += 1; return
        if tr.at_t is not None: t_arr, rule = tr.at_t, 'at'
        elif tr.tts <= REACHED_S: t_arr, rule = tr.teff + tr.tts, 'reached'
        else: self.acc_rule[mode]['censored'] += 1; return
        self.acc_rule[mode][rule] += 1
        for h, (te, tts) in tr.hz.items(): self.acc[mode][h].add((t_arr - te) - tts)

    def update_train(self, line, mode, key, kind, row, idx, L):
        cls = loc_class(row[LOC]); T = self.trains[line].get(key)
        L['train_obs'] += 1
        own = self.own_station(row) if cls in ('at', 'approaching') else None   # nearest stop only
        if own == 'at': L['at_own'].add(row[TTS])
        elif own == 'approaching': L['app_own'].add(row[TTS])
        if mode in ('overground', 'elizabeth') and cls == 'empty' and row[TTS] > RUN_HORIZON_S: L['undeparted'] += 1
        if T is None: self.trains[line][key] = [idx, idx, 1, cls, kind]
        else:
            gap = idx - T[1] - 1
            if kind == 'vid':
                L['vid_obs'] += 1
                if gap >= 1: L['flicker'][min(gap, 3)] += 1
            if T[3] == 'at' and cls in DEPARTED_ANY:
                L['dep_tts'].add(row[TTS]); L['dep_vocab'][cls] += 1
            T[1], T[2], T[3] = idx, T[2] + 1, cls
        if kind == 'vid' and line in STOCK_GROUP:
            g = self.stock[STOCK_GROUP[line]][row[VID]]
            g[line] = min(g.get(line, 1e9), row[TTS])

    def eval_stock(self):
        for group, vids in self.stock.items():
            if not vids: continue
            S = self.stock_stats[group]; S['polls'] += 1; S['vids'] += len(vids)
            for vid, per in vids.items():
                if len(per) < 2: continue
                S['dup'] += 1; S['pairs']['+'.join(sorted(per))] += 1
                a, b = sorted(per.values())[:2]; S['margin'].add(b - a)
        self.stock.clear()

    def dlr_stats(self, rows):
        D = self.dlr; D['polls'] += 1; D['rows'] += len(rows)
        minT, groups = {}, Counter()
        for r in rows:
            if r[TTS] > RUN_HORIZON_S: continue
            D['rows_le_h'] += 1; groups[(r[DIR], r[DEST])] += 1
            k = (r[DIR], r[DEST], r[NAPTAN])
            if k not in minT or r[TTS] < minT[k]: minT[k] = r[TTS]
        D['keys_le_h'] += len(minT); D['groups'] += len(groups)
        for n in groups.values(): D['rows_per_group'].add(n)
        if self.dlr_prev is None: return
        leads = 0
        for (d, dest, nap), tts in minT.items():
            if not any(minT.get((d, dest, p), 1e9) < tts for p in self.dlr_prev.get(f'{d}|{nap}', ())): leads += 1
        D['leads'] += leads
        if leads: D['rows_per_lead'].add(len(minT) / leads)

    def sweep(self, line, mode, idx, L):
        tracks = self.tracks[line]
        for tk in [k for k, tr in tracks.items() if idx - tr.idx > MAX_ABSENT_POLLS]:
            self.close_track(mode, tracks.pop(tk), 'absent')
        queues = self.queues[line]
        for key in list(queues):
            keep = []
            for tr in queues[key]:
                if idx - tr.idx > MAX_ABSENT_POLLS: self.close_track(mode, tr, 'absent')
                else: keep.append(tr)
            if keep: queues[key] = keep
            else: del queues[key]
        trains = self.trains[line]
        for key in [k for k, T in trains.items() if idx - T[1] > GONE_POLLS]:
            T = trains.pop(key); L['gone'] += 1; L['life'][T[4]].add(T[2])

    def flush(self, reason):
        for line, tracks in self.tracks.items():
            mode = mode_of(line)
            for tr in tracks.values(): self.close_track(mode, tr, reason)
            tracks.clear()
        for line, queues in self.queues.items():
            mode = mode_of(line)
            for lst in queues.values():
                for tr in lst: self.close_track(mode, tr, reason)
            queues.clear()
        for line, trains in self.trains.items():
            for T in trains.values(): self.lines[line]['life'][T[4]].add(T[2])
            trains.clear()
        self.prev_ts.clear(); self.prev_teff.clear(); self.stock.clear()

def local_bin(t):
    lt = dt.datetime.fromtimestamp(t, LONDON)
    return (lt.hour * 60 + lt.minute) // COV_BIN_MIN

def load_branches(d):
    names, prev = {}, None
    for path in glob.glob(os.path.join(d, '*.json')):
        for br in json.load(open(path)).get('branches', []):
            for s in br['stops']: names[s['id']] = norm_station(s['name'])
            if os.path.basename(path) == 'dlr.json':
                prev = prev if prev is not None else defaultdict(list)
                for i in range(1, len(br['stops'])): prev[f"{br['direction']}|{br['stops'][i]['id']}"].append(br['stops'][i - 1]['id'])
    return names, prev

def pct(a, b): return round(100.0 * a / b, 3) if b else None

def build_output(A, files):
    lines = {}
    for line, L in sorted(A.lines.items()):
        fresh = L['fresh'] or 1
        lines[line] = {
            'mode': mode_of(line), 'polls': L['polls'], 'fresh': L['fresh'], 'stale': L['stale'], 'back': L['back'],
            'rows': L['rows'], 'rows_per_fresh_poll': round(L['rows'] / fresh, 1), 'rows_max': L['rows_max'],
            'trains_per_fresh_poll': round(L['trains_sum'] / fresh, 1), 'trains_max': L['trains_max'],
            'age': L['age'].summary(), 'ts_interval': L['ts_interval'].summary(),
            'vid_missing': L['vid_missing'], 'vid_000': L['vid_000'],
            'vocab': dict(L['vocab']), 'other_loc_top': L['other_loc'].most_common(25),
            'tts_log': L['tts_log'].summary(), 'posless_rows': L['posless_rows'], 'tt_rows': L['tt_rows'],
            'train_obs': L['train_obs'], 'undeparted': L['undeparted'],
            'pairs': L['pairs'], 'regress': L['regress'], 'stall': L['stall'], 'id_changes': L['id_changes'],
            'dup_listings': L['dup_listings'], 'vid_obs': L['vid_obs'], 'flicker': {str(k): v for k, v in sorted(L['flicker'].items())},
            'gone': L['gone'], 'life': {k: h.summary() for k, h in L['life'].items()}, 'ktype': dict(L['ktype']),
            'first_tts': L['first_tts'].summary(), 'dep_tts': L['dep_tts'].summary(), 'dep_vocab': dict(L['dep_vocab']),
            'at_own': L['at_own'].summary(), 'app_own': L['app_own'].summary(), 'near_mix': dict(L['near_mix']),
        }
    return {
        'files': files, 'days': {d: dict(c) for d, c in A.days.items()},
        'polls': A.polls, 'error_polls': A.err_polls, 'stale_polls': A.stale_polls, 'back_polls': A.back_polls, 'poll_gap': A.gap_hist.summary(),
        'constants': {'RUN_HORIZON_S': RUN_HORIZON_S, 'AT_PLATFORM_S': AT_PLATFORM_S, 'MAX_ABSENT_POLLS': MAX_ABSENT_POLLS,
                      'GONE_POLLS': GONE_POLLS, 'REACHED_S': REACHED_S, 'STALL_S': STALL_S, 'QUEUE_MATCH_S': QUEUE_MATCH_S, 'HORIZONS': HORIZONS},
        'names_known': len(A.names), 'names_learned': sum(1 for n in A.names if n in A.votes),
        'lines': lines,
        'residual': {m: h.summary() for m, h in A.resid.items()},
        'accuracy': {m: {str(h): hh.summary() for h, hh in sorted(d.items())} for m, d in A.acc.items()},
        'accuracy_rule': {m: dict(c) for m, c in A.acc_rule.items()},
        'track_life': {m: h.summary() for m, h in A.track_life.items()},
        'stock': {g: {'polls': S['polls'], 'vids': S['vids'], 'dup': S['dup'], 'pairs': dict(S['pairs']), 'margin': S['margin'].summary()}
                  for g, S in A.stock_stats.items()},
        'dlr': {k: (v.summary() if isinstance(v, Hist) else v) for k, v in A.dlr.items()},
        'coverage': {line: {str(b): v for b, v in sorted(c.items())} for line, c in A.cov.items()},
        'coverage_polls': {str(b): dict(c) for b, c in sorted(A.cov_polls.items())},
        'day_hours': {d: {str(h): dict(c) for h, c in sorted(hs.items())} for d, hs in sorted(A.day_hours.items())},
        'gaps': A.gaps,
    }

def write_csvs(out, M):
    d = os.path.join(out, 'arrivals'); os.makedirs(d, exist_ok=True)
    def w(name, header, rows):
        with open(os.path.join(d, name), 'w', newline='') as f:
            cw = csv.writer(f); cw.writerow(header); cw.writerows(rows)
    L = M['lines']; q = lambda s, k: s.get(k)
    w('m01-cadence.csv', ['line', 'mode', 'polls', 'fresh', 'stale_pct', 'rows_per_fresh_poll', 'rows_max', 'trains_per_fresh_poll',
                          'trains_max', 'ts_interval_p50', 'ts_interval_p90', 'age_p50', 'age_p90', 'dup_listings_pct'],
      [[l, s['mode'], s['polls'], s['fresh'], pct(s['stale'], s['polls']), s['rows_per_fresh_poll'], s['rows_max'], s['trains_per_fresh_poll'],
        s['trains_max'], q(s['ts_interval'], 'p50'), q(s['ts_interval'], 'p90'), q(s['age'], 'p50'), q(s['age'], 'p90'),
        pct(s['dup_listings'], s['rows'])] for l, s in L.items()])
    w('m02-coverage.csv', ['line', 'local_time', 'polls', 'rows_mean', 'trains_max'],
      [[l, f'{int(b) * COV_BIN_MIN // 60:02d}:{int(b) * COV_BIN_MIN % 60:02d}', v[0], round(v[1] / v[0], 1), v[2]]
       for l, c in M['coverage'].items() for b, v in c.items()])
    w('m03-vehicle-id.csv', ['line', 'mode', 'rows', 'vid_missing', 'vid_missing_pct', 'vid_000', 'vid_000_pct'],
      [[l, s['mode'], s['rows'], s['vid_missing'], pct(s['vid_missing'], s['rows']), s['vid_000'], pct(s['vid_000'], s['rows'])] for l, s in L.items()])
    w('m04-vocabulary.csv', ['line', 'mode', 'class', 'rows', 'pct'],
      [[l, s['mode'], c, n, pct(n, s['rows'])] for l, s in L.items() for c, n in sorted(s['vocab'].items())])
    w('m04-vocabulary-other.csv', ['line', 'currentLocation', 'rows'], [[l, loc, n] for l, s in L.items() for loc, n in s['other_loc_top']])
    w('m05-regression.csv', ['line', 'mode', 'pairs', 'regress', 'regress_pct', 'stall', 'stall_pct'],
      [[l, s['mode'], s['pairs'], s['regress'], pct(s['regress'], s['pairs']), s['stall'], pct(s['stall'], s['pairs'])] for l, s in L.items()])
    w('m05-residual-by-mode.csv', ['mode', 'n', 'mean', 'p10', 'p50', 'p90'],
      [[m, h['n'], h.get('mean'), h.get('p10'), h.get('p50'), h.get('p90')] for m, h in M['residual'].items()])
    w('m06-accuracy.csv', ['mode', 'horizon_s', 'n', 'mean_err', 'p10', 'p50', 'p90'],
      [[m, h, s['n'], s.get('mean'), s.get('p10'), s.get('p50'), s.get('p90')] for m, d in M['accuracy'].items() for h, s in d.items()])
    w('m06-accuracy-rule.csv', ['mode', 'rule', 'tracks'], [[m, r, n] for m, c in M['accuracy_rule'].items() for r, n in sorted(c.items())])
    w('m07-flicker.csv', ['line', 'vid_obs', 'gap1', 'gap2', 'gap3plus', 'episodes_per_1000_obs', 'gone'],
      [[l, s['vid_obs'], s['flicker'].get('1', 0), s['flicker'].get('2', 0), s['flicker'].get('3', 0),
        round(1000 * sum(s['flicker'].values()) / s['vid_obs'], 2) if s['vid_obs'] else None, s['gone']] for l, s in L.items()])
    w('m08-stock-dup.csv', ['group', 'polls', 'vid_listings', 'dup', 'dup_pct', 'margin_p50', 'margin_p90', 'pairs'],
      [[g, S['polls'], S['vids'], S['dup'], pct(S['dup'], S['vids']), q(S['margin'], 'p50'), q(S['margin'], 'p90'), json.dumps(S['pairs'])]
       for g, S in M['stock'].items()])
    D = M['dlr']
    w('m09-dlr.csv', ['fresh_polls', 'rows', 'rows_le_480', 'stop_keys_le_480', 'leading_edges', 'stop_keys_per_train', 'rows_per_train', 'rows_per_group_mean'],
      [[D['polls'], D['rows'], D['rows_le_h'], D['keys_le_h'], D['leads'], D['rows_per_lead'].get('mean'),
        round(D['rows_le_h'] / D['leads'], 2) if D['leads'] else None, D['rows_per_group'].get('mean')]])
    w('m10-horizon.csv', ['line', 'mode', 'rows', 'posless_rows', 'tt_rows', 'tt_pct_of_rows', 'train_obs', 'undeparted', 'undeparted_pct',
                          'first_tts_p50', 'first_tts_p90', 'tts_edges', 'tts_counts'],
      [[l, s['mode'], s['rows'], s['posless_rows'], s['tt_rows'], pct(s['tt_rows'], s['rows']), s['train_obs'], s['undeparted'],
        pct(s['undeparted'], s['train_obs']), q(s['first_tts'], 'p50'), q(s['first_tts'], 'p90'),
        ' '.join(map(str, s['tts_log']['edges'])), ' '.join(map(str, s['tts_log']['counts']))] for l, s in L.items()])
    w('m11-consistency.csv', ['line', 'mode', 'measure', 'n', 'p10', 'p50', 'p90'],
      [[l, s['mode'], k, s[k]['n'], q(s[k], 'p10'), q(s[k], 'p50'), q(s[k], 'p90')] for l, s in L.items() for k in ('at_own', 'app_own', 'dep_tts')])
    w('m11-near-platform-mix.csv', ['line', 'class', 'rows'], [[l, c, n] for l, s in L.items() for c, n in sorted(s['near_mix'].items())])
    w('m11-departure-vocab.csv', ['line', 'class', 'transitions'], [[l, c, n] for l, s in L.items() for c, n in sorted(s['dep_vocab'].items())])
    w('m12-identity.csv', ['line', 'kind', 'rows', 'rows_pct', 'train_life_p50', 'train_life_p90', 'id_changes_pct'],
      [[l, k, n, pct(n, s['rows']), q(s['life'].get(k, {}), 'p50'), q(s['life'].get(k, {}), 'p90'), pct(s['id_changes'], s['pairs'])]
       for l, s in L.items() for k, n in sorted(s['ktype'].items())])

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+'); ap.add_argument('--branches'); ap.add_argument('--out')
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = a.out or os.path.join(root, 'data'); os.makedirs(os.path.join(out, 'arrivals'), exist_ok=True)
    names_path = os.path.join(out, 'arrivals', 'naptan-names.json')
    if a.branches: names, dlr_prev = load_branches(a.branches)
    else:
        names, dlr_prev = {}, None
        if os.path.exists(names_path): names = json.load(open(names_path))
    A = Analyzer(names, dlr_prev)
    for path in a.files:
        day = os.path.basename(path).split('.')[0]; n = bad = 0
        with gzip.open(path, 'rt') as f:
            try:
                for line in f:
                    n += 1
                    try: rec = json.loads(line)
                    except Exception: bad += 1; continue
                    A.poll(rec, day)
            except (EOFError, gzip.BadGzipFile, zlib.error):
                # the sampler is still appending today's file: its last gzip member can be cut short
                print(day, 'truncated final member after', n, 'lines (file still being written)', flush=True)
        print(day, 'polls', n, 'malformed', bad, 'tracks', sum(map(len, A.tracks.values())) + sum(len(l) for q in A.queues.values() for l in q.values()), 'names', len(A.names), flush=True)
    A.flush('eof')
    M = build_output(A, a.files)
    tmp = os.path.join(out, 'arrivals-metrics.json.part')
    with open(tmp, 'w') as f: json.dump(M, f)
    os.replace(tmp, os.path.join(out, 'arrivals-metrics.json'))
    json.dump(A.names, open(names_path, 'w'), indent=0, sort_keys=True)
    write_csvs(out, M)
    print('polls', A.polls, 'errors', A.err_polls, 'stale', A.stale_polls, 'back', A.back_polls, 'lines', len(M['lines']), '->', os.path.join(out, 'arrivals-metrics.json'))

if __name__ == '__main__':
    main()
