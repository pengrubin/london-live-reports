#!/usr/bin/env python3
"""Validation-section figures from data/arrivals-metrics.json (written by analyze-arrivals.py):
  fig-v-1 countdown advance residual per mode (regression / stall)
  fig-v-2 countdown error vs horizon per mode (p10 / p50 / p90)
  fig-v-3 currentLocation vocabulary per line
  fig-v-4 flicker episodes per line by gap length
  fig-v-5 time-of-day coverage: polls per 10-min bin and trains seen
  fig-v-6 countdown while 'At <own stop>' / 'Approaching <own stop>' / at departure, tube
Numbers the prose quotes go to numbers.json via put().
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
M = json.load(open(os.path.join(DATA, 'arrivals-metrics.json')))
L = M['lines']; MODES = ['tube', 'dlr', 'overground', 'elizabeth', 'tram']
COL = {'tube': INK, 'dlr': RED, 'overground': AMBER, 'elizabeth': GREEN, 'tram': GREY}

def bins(h):
    return sorted((int(float(k)), v) for k, v in h.get('bins', {}).items())

# fig v.1 residual
fig, ax = plt.subplots(figsize=(7.2, 2.6))
for m in MODES:
    h = M['residual'].get(m)
    if not h or not h['n']: continue
    xs, ys = zip(*bins(h)); og = m == 'overground'
    ax.step(xs, [y / h['n'] * 100 for y in ys], where='mid', color=COL[m], ls='--' if og else '-', zorder=3 if og else 2,
            label=f"{m} (n={h['n']:,})")
RESID_YMAX = 12   # the 0 s bin (38–97%) would flatten the ±30 s / ±60 s lobes that are the finding; its heights are printed
peaks = ', '.join(f"{m} {M['residual'][m]['bins'].get('0', 0) / M['residual'][m]['n'] * 100:.0f}%" for m in MODES if M['residual'].get(m, {}).get('n'))
ax.text(-117, RESID_YMAX * 0.95, '0 s bin (clipped):\n' + peaks.replace(', ', '\n'), fontsize=7, va='top')
ax.axvline(0, color=LIGHT, lw=1, zorder=0); ax.set_xlim(-120, 120); ax.set_ylim(0, RESID_YMAX)
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.3), ncol=3)
ax.set_xlabel('(previous countdown − elapsed) − new countdown, s   [<0: countdown stalled or went back up]'); ax.set_ylabel('% of pairs')
ax.set_title('Countdown advance residual between consecutive fresh polls, same train and station', loc='left')
fig.tight_layout(); save(fig, 'fig-v-1-residual')

# fig v.2 accuracy vs horizon
fig, ax = plt.subplots(figsize=(7.2, 2.8))
ACC_MIN_N = 1000   # sparse buckets (tram 3600 s: n=290) are noise and stretch the axis
for i, m in enumerate(MODES):
    d = M['accuracy'].get(m, {})
    pts = sorted((int(h), s) for h, s in d.items() if s['n'] >= ACC_MIN_N)
    if not pts: continue
    xs = [h * 1.05 ** (i - 2) for h, _ in pts]   # small horizontal offset: elizabeth and overground coincide
    ax.plot(xs, [s['p50'] for _, s in pts], color=COL[m], marker='o', ms=3, label=m)
    ax.fill_between(xs, [s['p10'] for _, s in pts], [s['p90'] for _, s in pts], color=COL[m], alpha=0.12, lw=0)
ax.axhline(0, color=LIGHT, lw=1, zorder=0); ax.set_xscale('log'); ax.set_ylim(-300, 300)
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.3), ncol=5)
ax.set_xlabel('countdown horizon at the observation, s (bucket upper edge)'); ax.set_ylabel('actual − predicted, s')
ax.set_title('Countdown error vs realised arrival (p50 line, p10–p90 band)\narrival = first "At <stop>" or final countdown; buckets with n ≥ 1,000', loc='left')
fig.tight_layout(); save(fig, 'fig-v-2-accuracy')

# fig v.3 vocabulary
classes = ['at', 'between', 'approaching', 'left', 'leaving', 'departed', 'sidings', 'other', 'empty']
shade = [INK, '#3b4a5e', '#5c6b7e', RED, '#d9536a', '#e8909d', AMBER, GREY, LIGHT]
names = [l for l in L if L[l]['rows'] > 0]
fig, ax = plt.subplots(figsize=(7.2, 0.28 * len(names) + 1.2))
left = [0.0] * len(names)
for c, col in zip(classes, shade):
    vals = [100 * L[l]['vocab'].get(c, 0) / L[l]['rows'] for l in names]
    ax.barh(names, vals, left=left, color=col, label=c); left = [a + b for a, b in zip(left, vals)]
ax.set_xlim(0, 100); ax.invert_yaxis(); ax.legend(ncol=5, loc='upper center', bbox_to_anchor=(0.5, -0.08)); ax.set_xlabel('% of prediction rows')
ax.set_title('currentLocation prefix per line', loc='left'); fig.tight_layout(); save(fig, 'fig-v-3-vocabulary')

# fig v.4 flicker
fl = [(l, L[l]) for l in names if L[l]['vid_obs'] > 0]
FLICK_XMAX = 30   # waterloo-city (~184) would flatten every other line; it is clipped and labelled
fl.sort(key=lambda ls: sum(ls[1]['flicker'].values()) / ls[1]['vid_obs'])
fig, ax = plt.subplots(figsize=(7.2, 0.24 * len(fl) + 1.2)); base = [0.0] * len(fl)
for gap, col, lab in (('1', INK, '1 poll'), ('2', RED, '2 polls'), ('3', AMBER, '3+ polls')):
    ys = [1000 * s['flicker'].get(gap, 0) / s['vid_obs'] for _, s in fl]
    ax.barh([l for l, _ in fl], ys, left=base, color=col, label=lab); base = [a + b for a, b in zip(base, ys)]
for i, tot in enumerate(base):
    if tot > FLICK_XMAX: ax.text(FLICK_XMAX * 0.99, i, f'{tot:.0f} →', ha='right', va='center', color='white', fontsize=7.5)
ax.set_xlim(0, FLICK_XMAX); ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.12), ncol=3)
ax.set_xlabel('episodes per 1,000 train-polls')
ax.set_title('Flicker: a vehicleId-keyed train absent for k fresh polls, then back', loc='left'); fig.tight_layout(); save(fig, 'fig-v-4-flicker')

# fig v.5 coverage
cp = M['coverage_polls']; xs = sorted(int(b) for b in cp)
fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 4.4), sharex=True)
bottom = [0] * len(xs)
for k, col in (('fresh', INK), ('stale', GREY), ('error', RED)):
    ys = [cp[str(x)].get(k, 0) for x in xs]
    a1.bar([x / 6 for x in xs], ys, bottom=bottom, width=1 / 6, align='edge', color=col, label=k)
    bottom = [a + b for a, b in zip(bottom, ys)]
a1.set_ylim(0, max(bottom) * 1.1); a1.legend(ncol=3, loc='upper center', bbox_to_anchor=(0.5, -0.06)); a1.set_ylabel('polls per 10 min'); a1.set_title('Sampling completeness and trains seen, by local time of day', loc='left')
for m, col in COL.items():
    tot = {}
    for l in names:
        if L[l]['mode'] != m: continue
        for b, v in M['coverage'][l].items(): tot[int(b)] = tot.get(int(b), 0) + v[2]
    if tot: a2.plot([b / 6 for b in sorted(tot)], [tot[b] for b in sorted(tot)], color=col, label=m)
a2.legend(ncol=5, loc='upper center', bbox_to_anchor=(0.5, -0.3)); a2.set_ylabel('max trains in bin'); a2.set_xlabel('local time (h)'); a2.set_xlim(0, 24)
fig.tight_layout(); save(fig, 'fig-v-5-coverage')

# fig v.6 consistency (tube, summed over lines)
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.4))
for ax, key, title in zip(axes, ('at_own', 'app_own', 'dep_tts'), ('"At <own stop>"', '"Approaching <own stop>"', 'first poll after departure')):
    acc = {}
    for l in names:
        if L[l]['mode'] == 'tube':
            for k, v in bins(L[l][key]): acc[k] = acc.get(k, 0) + v
    n = sum(acc.values()); top = max(acc) if acc else 0          # the histogram clamps its tail into the last bin
    xmax = 300 if key != 'dep_tts' else 600
    if n:
        ax.bar([k for k in acc if k < xmax], [acc[k] / n * 100 for k in acc if k < xmax], width=5, color=INK, align='edge')
        over = sum(v for k, v in acc.items() if k >= xmax) / n * 100
        if over >= 0.05:
            ax.bar([xmax], [over], width=xmax / 40, color=RED, align='edge')
            ax.annotate(f'≥{xmax} s: {over:.1f}%', (xmax, over), xytext=(-4, 4), textcoords='offset points', ha='right', fontsize=7, color=RED)
    ax.set_xlim(0, xmax * 1.05)
    ax.set_title(f'{title}\nn = {n:,}', loc='left', fontsize=8); ax.set_xlabel('countdown, s')
axes[0].axvline(M['constants']['AT_PLATFORM_S'], color=RED, lw=1, ls='--'); axes[0].set_ylabel('% of rows')
fig.suptitle('Countdown when currentLocation says where the train is (tube)', x=0.01, ha='left', fontsize=9.5)
fig.tight_layout(); save(fig, 'fig-v-6-consistency')

tube = {m: M['residual'].get(m, {}) for m in MODES}
put(arr_polls=M['polls'], arr_stale_polls=M['stale_polls'], arr_error_polls=M['error_polls'],
    arr_regress_pct_tube=round(100 * sum(L[l]['regress'] for l in names if L[l]['mode'] == 'tube') / max(1, sum(L[l]['pairs'] for l in names if L[l]['mode'] == 'tube')), 2),
    arr_stock_dup_pct=round(100 * M['stock'].get('sub', {}).get('dup', 0) / max(1, M['stock'].get('sub', {}).get('vids', 1)), 2),
    arr_dlr_rows_per_lead=M['dlr']['rows_per_lead'].get('mean'))

# ── numbers for findings.md / the prose (arr_* keys; build-numbers.py owns t_*) ──
from collections import Counter
def by_mode(mode): return [l for l in names if L[l]['mode'] == mode]
def msum(mode, key): return sum(L[l][key] for l in by_mode(mode))
def pc(a, b, nd=1): return round(100 * a / b, nd) if b else None
def band(h, lo, hi):   # share of a centred residual histogram with lo <= |bin| <= hi
    return pc(sum(v for k, v in h['bins'].items() if lo <= abs(int(float(k))) <= hi), h['n'])
def hist_merge(lines, key):
    acc = Counter()
    for l in lines: acc.update({int(float(k)): v for k, v in L[l][key].get('bins', {}).items()})
    return acc
N = {'arr_fresh_polls': M['polls'] - M['stale_polls'] - M['error_polls'], 'arr_back_polls': M.get('back_polls'),
     'arr_stale_pct': pc(M['stale_polls'], M['polls']), 'arr_days': len(M['days']),
     'arr_rows_total': sum(d['rows'] for d in M['days'].values())}
N.update({f"arr_polls_{d.replace('-', '')}": c['polls'] for d, c in M['days'].items()})
N['arr_sampler_gaps'] = len(M.get('gaps', [])); N['arr_sampler_gap_h'] = round(sum(g for _, g in M.get('gaps', [])) / 3600, 1)
ref = L['bakerloo']   # every line is in every body: one line's timestamp series is the body's
N.update(arr_ts_interval_p50=ref['ts_interval']['p50'], arr_ts_interval_p90=ref['ts_interval']['p90'], arr_ts_interval_mean=ref['ts_interval']['mean'],
         arr_age_p50=ref['age']['p50'], arr_age_p90=ref['age']['p90'])
TSF = os.path.join(DATA, 'arrivals-timestamps.json')
if os.path.exists(TSF):
    T = json.load(open(TSF)); tp = T['line_polls_pct']
    N.update(arr_ts_same_pct=tp.get('same'), arr_ts_back_pct=tp.get('back'), arr_ts_fwd_pct=round(tp.get('fwd', 0) + tp.get('sub1', 0), 2),
             arr_fwd_interval_mean_s=T['fwd_interval_mean_s'])
for m in ('tube', 'dlr', 'overground', 'elizabeth'):
    p = msum(m, 'pairs'); h = M['residual'][m]; rule = M['accuracy_rule'][m]; res = sum(rule.values())
    N.update({f'arr_{m}_pairs': p, f'arr_{m}_regress_pct': pc(msum(m, 'regress'), p, 2), f'arr_{m}_stall_pct': pc(msum(m, 'stall'), p),
              f'arr_{m}_resid_p10': h['p10'], f'arr_{m}_resid_p90': h['p90'], f'arr_{m}_resid_zero_pct': band(h, 0, 5),
              f'arr_{m}_resid_lobe30_pct': band(h, 20, 40), f'arr_{m}_resid_lobe60_pct': band(h, 50, 70),
              f'arr_{m}_arrival_censored_pct': pc(rule.get('censored', 0) + rule.get('censored-gap', 0), res),
              f'arr_{m}_arrival_at_pct': pc(rule.get('at', 0), res), f'arr_{m}_tracks': res})
    vo = msum(m, 'vid_obs')
    if vo:
        fl = Counter(); [fl.update(L[l]['flicker']) for l in by_mode(m)]
        N[f'arr_{m}_flicker_per1000'] = round(1000 * sum(fl.values()) / vo, 2)
        N[f'arr_{m}_flicker_gap1_share_pct'] = pc(fl.get('1', 0), sum(fl.values()))
        N[f'arr_{m}_flicker_gap3plus_share_pct'] = pc(fl.get('3', 0), sum(fl.values()))
    for h in ('30', '120', '300', '480', '900', '1800', '3600', '7200'):
        s = M['accuracy'][m].get(h)
        if s and s['n'] >= 1000: N.update({f'arr_{m}_acc{h}_p10': s['p10'], f'arr_{m}_acc{h}_p50': s['p50'], f'arr_{m}_acc{h}_p90': s['p90'], f'arr_{m}_acc{h}_n': s['n']})
for m in ('overground', 'elizabeth'):
    N[f'arr_{m}_undeparted_pct'] = pc(msum(m, 'undeparted'), msum(m, 'train_obs'))
    N[f'arr_{m}_first_tts_p50'] = L['elizabeth' if m == 'elizabeth' else 'windrush']['first_tts']['p50']
tube = by_mode('tube')
dv = Counter(); [dv.update(L[l]['dep_vocab']) for l in tube]; nd = sum(dv.values())
N['arr_tube_departures'] = nd; N['arr_tube_departed_missed_pct'] = pc(dv['departed'] + dv['leaving'], nd)
for l in ('northern', 'victoria', 'jubilee'):
    d = L[l]['dep_vocab']; N[f'arr_{l.replace("-", "_")}_departed_missed_pct'] = pc(d.get('departed', 0) + d.get('leaving', 0), sum(d.values()))
nm = Counter(); [nm.update(L[l]['near_mix']) for l in tube]; nn = sum(nm.values())
N.update(arr_tube_near_rows=nn, arr_tube_near_between_pct=pc(nm['between'], nn), arr_tube_near_at_other_pct=pc(nm['at'], nn),
         arr_tube_near_at_own_pct=pc(nm['at-own'], nn), arr_tube_near_app_own_pct=pc(nm['approaching-own'], nn))
for key in ('at_own', 'app_own', 'dep_tts'):
    acc = hist_merge(tube, key); n = sum(acc.values()); cut = 600 if key == 'dep_tts' else 300
    N[f'arr_tube_{key}_n'] = n; N[f'arr_tube_{key}_le15_pct'] = pc(sum(v for k, v in acc.items() if k < 15), n)
    N[f'arr_tube_{key}_over_pct'] = pc(sum(v for k, v in acc.items() if k >= cut), n)
    cum, q = 0, {}
    for k in sorted(acc):
        cum += acc[k]
        for p in (.1, .5, .9):
            if p not in q and cum >= p * n: q[p] = k
    N.update({f'arr_tube_{key}_p10': q.get(.1), f'arr_tube_{key}_p50': q.get(.5), f'arr_tube_{key}_p90': q.get(.9)})
hc = hist_merge(['hammersmith-city'], 'at_own'); N['arr_hammersmith_city_at_own_over300_pct'] = pc(hc.get(300, 0), sum(hc.values()))
for g in ('sub', 'og'):
    S = M['stock'].get(g, {})
    if S: N.update({f'arr_{g}_dup_pct': pc(S['dup'], S['vids'], 2), f'arr_{g}_margin_p50': S['margin']['p50'], f'arr_{g}_margin_p90': S['margin']['p90']})
met = L['metropolitan']
N.update(arr_met_vid000_pct=pc(met['vid_000'], met['rows']), arr_met_loc_key_pct=pc(met['ktype'].get('loc', 0), met['rows']),
         arr_met_tt_key_pct=pc(met['ktype'].get('tt', 0), met['rows']), arr_met_gone=met['gone'],
         arr_met_loc_life_p50=met['life'].get('loc', {}).get('p50'))
D = M['dlr']; N.update(arr_dlr_rows_per_train=round(D['rows_le_h'] / D['leads'], 2) if D['leads'] else None, arr_dlr_le480_pct=pc(D['rows_le_h'], D['rows']))
N['arr_wc_flicker_per1000'] = round(1000 * sum(L['waterloo-city']['flicker'].values()) / L['waterloo-city']['vid_obs'], 1)
N['arr_bakerloo_sidings_pct'] = pc(L['bakerloo']['vocab'].get('sidings', 0), L['bakerloo']['rows'])
put(**N)
print(json.dumps(N, indent=0))
