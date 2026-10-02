#!/usr/bin/env python3
"""Every number document 3 quotes, derived from data/arrivals-metrics.json (the
recorded Arrivals samples), the baked branch files and the rule constants.
Keys are prefixed t_. fig-arrivals.py adds its own arr_* keys; both merge into numbers.json."""
import json, os, sys, math, glob
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import put, ROOT
M = json.load(open(os.path.join(ROOT, 'data', 'arrivals-metrics.json')))
APP = os.path.expanduser('~/london-live-worktrees/deps')  # checkout of origin/main used for the baked data
BR = os.path.join(APP, 'data', 'branches')
N = {}
# --- sample
days = M['days']; N['t_days'] = len(days); N['t_day_first'] = min(days); N['t_day_last'] = max(days)
N['t_polls'] = M['polls']; N['t_stale_polls'] = M['stale_polls']; N['t_fresh_polls'] = M['polls'] - M['stale_polls'] - M.get('error_polls', 0)
N['t_stale_pct'] = round(100 * M['stale_polls'] / M['polls'], 1); N['t_error_polls'] = M.get('error_polls', 0)
N['t_rows_total'] = sum(d['rows'] for d in days.values()); N['t_rows_per_poll'] = round(N['t_rows_total'] / max(1, N['t_fresh_polls'] + M['stale_polls']))
g = M['poll_gap']; N['t_gap_p50'] = g['p50']; N['t_gap_p90'] = g['p90']; N['t_gap_mean'] = round(g['mean'], 1)
C = M['constants']; N.update({f't_const_{k}': v for k, v in C.items()})
# --- per line / per mode
L = M['lines']; modes = {}
for lid, v in L.items(): modes.setdefault(v['mode'], []).append(lid)
N['t_lines'] = len(L); N['t_modes'] = ', '.join(f"{m} ({len(ls)})" for m, ls in sorted(modes.items()))
def agg(mode, key):
    return sum(L[l].get(key, 0) for l in modes.get(mode, []))
for m in ('tube', 'dlr', 'overground', 'elizabeth'):
    pairs = agg(m, 'pairs'); N[f't_{m}_pairs'] = pairs
    N[f't_{m}_regress_pct'] = round(100 * agg(m, 'regress') / pairs, 1) if pairs else None
    N[f't_{m}_stall_pct'] = round(100 * agg(m, 'stall') / pairs, 1) if pairs else None
    rows = agg(m, 'rows'); N[f't_{m}_rows'] = rows
    N[f't_{m}_posless_pct'] = round(100 * agg(m, 'posless_rows') / rows, 1) if rows else None
    N[f't_{m}_tt_pct'] = round(100 * agg(m, 'tt_rows') / rows, 1) if rows else None
    N[f't_{m}_vid_missing_pct'] = round(100 * (agg(m, 'vid_missing') + agg(m, 'vid_000')) / rows, 1) if rows else None
    N[f't_{m}_dup_pct'] = round(100 * agg(m, 'dup_listings') / rows, 1) if rows else None
    obs = agg(m, 'vid_obs'); fl = {k: sum((L[l].get('flicker') or {}).get(k, 0) for l in modes.get(m, [])) for k in ('1', '2', '3')}
    N[f't_{m}_flicker1_per_1000'] = round(1000 * fl['1'] / obs, 1) if obs else None
    N[f't_{m}_flicker_any_per_1000'] = round(1000 * sum(fl.values()) / obs, 1) if obs else None
    N[f't_{m}_gone'] = agg(m, 'gone')
    # train counts per fresh poll
    N[f't_{m}_trains_per_poll'] = round(sum(L[l]['trains_per_fresh_poll'] for l in modes.get(m, [])))
    # per-mode distributions from the metrics file
    for key in ('residual', 'track_life'):
        d = M.get(key, {}).get(m)
        if d: N[f't_{m}_{key}_p10'] = d['p10']; N[f't_{m}_{key}_p50'] = d['p50']; N[f't_{m}_{key}_p90'] = d['p90']; N[f't_{m}_{key}_n'] = d['n']
    acc = M.get('accuracy', {}).get(m, {})
    for h in ('30', '60', '120', '300', '480', '900'):
        if h in acc: N[f't_{m}_acc{h}_p50'] = acc[h]['p50']; N[f't_{m}_acc{h}_p90'] = acc[h]['p90']; N[f't_{m}_acc{h}_p10'] = acc[h]['p10']; N[f't_{m}_acc{h}_n'] = acc[h]['n']
    ar = M.get('accuracy_rule', {}).get(m, {})
    tot = sum(ar.values()) or 1; N[f't_{m}_arrival_at_pct'] = round(100 * ar.get('at', 0) / tot); N[f't_{m}_arrival_reached_pct'] = round(100 * ar.get('reached', 0) / tot); N[f't_{m}_arrival_censored_pct'] = round(100 * (ar.get('censored', 0) + ar.get('censored-gap', 0)) / tot)
# per-line specifics the text names
for lid in ('metropolitan', 'piccadilly', 'northern', 'jubilee', 'victoria', 'bakerloo', 'central', 'district', 'elizabeth', 'dlr'):
    v = L.get(lid)
    if not v: continue
    rows = v['rows'] or 1
    N[f't_{lid}_vid000_pct'] = round(100 * (v.get('vid_000', 0) + v.get('vid_missing', 0)) / rows, 1)
    N[f't_{lid}_trains_per_poll'] = round(v['trains_per_fresh_poll'], 1); N[f't_{lid}_rows_per_poll'] = round(v['rows_per_fresh_poll'])
    voc = v.get('vocab') or {}; tv = sum(voc.values()) or 1
    for k in ('at', 'approaching', 'between', 'left', 'sidings', 'other'): N[f't_{lid}_loc_{k}_pct'] = round(100 * voc.get(k, 0) / tv, 1)
    dv = v.get('dep_vocab') or {}; N[f't_{lid}_dep_vocab'] = ', '.join(f"{k} {n:,}" for k, n in sorted(dv.items(), key=lambda x: -x[1])[:4])
    for key in ('first_tts', 'dep_tts', 'app_own'):
        d = v.get(key)
        if d and d.get('n'): N[f't_{lid}_{key}_p50'] = d['p50']; N[f't_{lid}_{key}_p90'] = d['p90']; N[f't_{lid}_{key}_n'] = d['n']
    nm = v.get('near_mix') or {}; tn = sum(nm.values()) or 1
    for k, n in nm.items(): N[f't_{lid}_near_{k.replace("-", "_")}_pct'] = round(100 * n / tn, 1)
    ot = v.get('other_loc_top') or []; N[f't_{lid}_other_loc_top'] = '; '.join(f"{a} ({b})" for a, b in ot[:5])
# whole-feed vocabulary of departure prefixes the DEPARTED regex misses
missed = {}
for lid, v in L.items():
    for name, n in (v.get('other_loc_top') or []):
        w = str(name).split(' ')[0].lower()
        if w in ('departed', 'leaving', 'north', 'south', 'east', 'west'): missed[w] = missed.get(w, 0) + int(n)
N['t_departed_missed_rows'] = sum(missed.values()); N['t_departed_missed_vocab'] = ', '.join(f"{k} {n:,}" for k, n in sorted(missed.items(), key=lambda x: -x[1]))
# --- stock groups and DLR
S = M['stock']
for grp in ('sub', 'og'):
    s = S.get(grp)
    if not s: continue
    N[f't_{grp}_dup_pct'] = round(100 * s['dup'] / max(1, s['vids']), 1); N[f't_{grp}_margin_p50'] = s['margin']['p50']; N[f't_{grp}_margin_p10'] = s['margin']['p10']
    top = sorted(s['pairs'].items(), key=lambda x: -x[1])[:3]; N[f't_{grp}_top_pairs'] = '; '.join(f"{k.replace('+', ' + ')} {v:,}" for k, v in top)
D = M['dlr']; N['t_dlr_rows_per_lead_p50'] = D['rows_per_lead']['p50']; N['t_dlr_rows_per_lead_mean'] = round(D['rows_per_lead']['mean'], 2); N['t_dlr_leads_per_poll'] = round(D['leads'] / max(1, D['polls'])); N['t_dlr_rows_le_h_pct'] = round(100 * D['rows_le_h'] / max(1, D['rows']))
# --- coverage: hours with samples per day
dh = M.get('day_hours', {}); N['t_hours_with_samples'] = sum(len(h) for h in dh.values()); N['t_coverage_days'] = ', '.join(f"{d} ({len(h)} h)" for d, h in sorted(dh.items()))
# --- baked geometry (branch files)
tot_stops = tot_seg = tot_km = tot_rt = tot_rt_filled = 0; lines = 0
def plen(seg):
    s = 0
    for a, b in zip(seg, seg[1:]): s += math.hypot((a[0] - b[0]) * 111320 * math.cos(math.radians(51.5)), (a[1] - b[1]) * 110540)
    return s
for f in sorted(glob.glob(os.path.join(BR, '*.json'))):
    b = json.load(open(f)); lines += 1
    for br in b['branches']:
        tot_seg += len(br['segments']); tot_km += sum(plen(s) for s in br['segments']) / 1000
        rt = br.get('runTimes') or []; tot_rt += len(br['segments']); tot_rt_filled += sum(1 for x in rt if x)
import subprocess
N['t_app_commit'] = subprocess.run(['git', '-C', APP, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
manifest = json.load(open(os.path.join(APP, 'data', 'manifest.json')))
mode_of = {l['id']: l.get('mode', '') for l in manifest['lines']}
mk = {}
for f in sorted(glob.glob(os.path.join(BR, '*.json'))):
    b = json.load(open(f)); m = mode_of.get(b['lineId'], '?'); d = mk.setdefault(m, {'lines': 0, 'branches': 0, 'km': 0.0, 'rt': 0, 'rt_filled': 0})
    d['lines'] += 1
    for br in b['branches']:
        if br['direction'] != 'outbound': continue
        d['branches'] += 1; d['km'] += sum(plen(s_) for s_ in br['segments']) / 1000
        rt = br.get('runTimes') or []; d['rt'] += len(br['segments']); d['rt_filled'] += sum(1 for x in rt if x)
for m, d in mk.items():
    key = m.replace('-', '_'); N[f't_geo_{key}_lines'] = d['lines']; N[f't_geo_{key}_branches'] = d['branches']; N[f't_geo_{key}_km'] = round(d['km']); N[f't_geo_{key}_rt_pct'] = round(100 * d['rt_filled'] / max(1, d['rt']))
N['t_geo_fallback_segments'] = tot_rt - tot_rt_filled
N['t_geo_lines'] = lines; N['t_geo_segments'] = tot_seg; N['t_geo_km'] = round(tot_km); N['t_geo_runtime_pct'] = round(100 * tot_rt_filled / max(1, tot_rt), 1); N['t_geo_runtime_filled'] = tot_rt_filled
nr = json.load(open(os.path.join(APP, 'data', 'nr', 'segments.json'))); st = json.load(open(os.path.join(APP, 'data', 'nr', 'stations.json')))
N['t_nr_stations'] = len(st); N['t_nr_segments'] = len(nr); N['t_nr_km'] = round(sum(s['lenM'] for s in nr) / 1000)
put(**N); print(len(N), 'tube numbers written')
