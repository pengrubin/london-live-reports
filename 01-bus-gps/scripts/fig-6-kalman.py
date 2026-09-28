#!/usr/bin/env python3
"""Figures 6.1-6.3 from the Kalman replay CSV (scripts/replay-kalman.ts).
  fig-6-1 lateral distance d(t) with the 50/80 m snap hysteresis and snap state
  fig-6-2 arc length: raw projection z, filtered s with ±2σ, coast between fixes (a 40-min window)
  fig-6-3 coast policy: linear extrapolation vs decaying coast (analytic)
"""
import csv, os, sys, math, datetime as dt
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA, 'cases', 'kf-11-LTZ1502.csv')
rows = list(csv.DictReader(open(path)))
fx = [r for r in rows if r['kind'] == 'fix']; co = [r for r in rows if r['kind'] == 'coast']
t0 = int(fx[0]['t']); H = lambda t: (int(t) - t0) / 3600
ts = [H(r['t']) for r in fx]; sn = [int(r['snapped']) for r in fx]
# do not bridge label gaps (fixes carrying the other direction label live in another file)
d = [float(r['d_m']) if i == 0 or int(fx[i]['t']) - int(fx[i-1]['t']) <= 600 else float('nan') for i, r in enumerate(fx)]

# fig 6.1: d(t) and snap state, whole day
fig, ax = plt.subplots(figsize=(7.2, 2.6))
ax.plot(ts, [min(x, 400) if x == x else x for x in d], lw=0.7, color=INK, label='distance from raw fix to learned path (capped 400 m; breaks = fixes labelled outbound)')
ax.plot([ts[0], ts[-1]], [50, 50], color=GREEN, lw=0.9, ls='--'); ax.plot([ts[0], ts[-1]], [80, 80], color=RED, lw=0.9, ls='--')
ax.set_xlim(ts[0] - 0.3, ts[-1] + 3.2); ax.text(ts[-1] + 0.3, 50, 'snap on < 50 m', ha='left', va='center', fontsize=7.5, color=GREEN); ax.text(ts[-1] + 0.3, 80, 'release > 80 m', ha='left', va='center', fontsize=7.5, color=RED)
ax.fill_between(ts, 0, [400 if s else 0 for s in sn], step='mid', color=GREEN, alpha=0.08, label='snapped (filter active)')
ax.set_ylim(0, 400); ax.set_xlabel(f'hours since first fix ({dt.datetime.fromtimestamp(t0, dt.UTC):%Y-%m-%d %H:%M} UTC)'); ax.set_ylabel('m')
ax.set_title('One vehicle, one day: lateral distance to the learned path and snap state (route 11, LTZ1502)', loc='left'); ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.3), ncol=2, fontsize=7.5)
fig.tight_layout(); save(fig, 'fig-6-1-snap-hysteresis')

# fig 6.2: s(t) window — pick the longest snapped stretch with the most fixes
best = None; start = 0
for i in range(1, len(fx) + 1):
    if i == len(fx) or not sn[i] or int(fx[i]['t']) - int(fx[i - 1]['t']) > 600:
        if sn[start] and (best is None or i - start > best[1] - best[0]): best = (start, i)
        start = i
a, b = best; w = fx[a:b]; wt0 = int(w[0]['t']); wt1 = min(int(w[-1]['t']), wt0 + 40 * 60)
w = [r for r in w if int(r['t']) <= wt1]; cw = [r for r in co if wt0 <= int(r['t']) <= wt1]
M = lambda t: (int(t) - wt0) / 60
fig, ax = plt.subplots(figsize=(7.2, 3.2))
ax.plot([M(r['t']) for r in cw], [float(r['disp_s']) for r in cw], lw=0.8, color=GREY, label='displayed position between fixes (decaying coast)')
s = [float(r['kf_s']) for r in w]; sig = [float(r['sigma_s']) for r in w]
ax.fill_between([M(r['t']) for r in w], [x - 2 * g for x, g in zip(s, sig)], [x + 2 * g for x, g in zip(s, sig)], color=INK, alpha=0.12, label='filtered s ± 2σ')
ax.plot([M(r['t']) for r in w], s, lw=1, color=INK, label='filtered arc length s')
ax.scatter([M(r['t']) for r in w], [float(r['z_s']) for r in w], s=9, color=RED, zorder=3, label='raw fix projected onto path (z)')
g = [r for r in w if r['result'] == 'gated']
if g: ax.scatter([M(r['t']) for r in g], [float(r['z_s']) for r in g], s=30, facecolors='none', edgecolors=AMBER, zorder=4, label='gated (rejected, >3σ)')
ax.set_xlabel('minutes'); ax.set_ylabel('arc length along learned path (m)')
ax.set_title(f'Along-route filter over a {len(w)}-fix stretch; σ_meas = 1.25 × route residual, floor 8 m', loc='left'); ax.legend(loc='upper left', fontsize=7.5)
fig.tight_layout(); save(fig, 'fig-6-2-kalman-track')

# fig 6.3: coast policy (analytic)
tau = 12; v = 8
tt = [i / 10 for i in range(0, 601)]
fig, ax = plt.subplots(figsize=(7.2, 2.4))
ax.plot(tt, [v * t for t in tt], color=GREY, lw=1, ls='--', label='linear extrapolation at last speed (8 m/s)')
ax.plot(tt, [v * tau * (1 - math.exp(-t / tau)) for t in tt], color=INK, lw=1.3, label='decaying coast, τ = 12 s')
ax.axhline(v * tau, color=RED, lw=0.8, ls=':'); ax.text(59, v * tau + 8, 'bound v·τ = 96 m', ha='right', fontsize=8, color=RED)
ax.set_ylim(0, 300); ax.set_xlabel('seconds since the last accepted fix'); ax.set_ylabel('displayed advance (m)')
ax.set_title('What the map shows while a bus is silent', loc='left'); ax.legend(loc='upper left', fontsize=7.5)
fig.tight_layout(); save(fig, 'fig-6-3-coast-policy')

acc = sum(r['result'] == 'accepted' for r in fx); gat = sum(r['result'] == 'gated' for r in fx); rst = sum(r['result'] == 'reset' for r in fx)
sig_all = sorted(float(r['sigma_s']) for r in fx if r['sigma_s'])
put(kf_case_vehicle='TFLO:LTZ1502', kf_case_route='11 inbound', kf_case_day='2026-09-25', kf_case_fixes=len(fx), kf_case_accepted=acc,
    kf_case_gated=gat, kf_case_resets=rst, kf_case_snapped_pct=round(100 * sum(sn) / len(sn), 1),
    kf_case_sigma_s_p50=sig_all[len(sig_all) // 2], kf_case_window_fixes=len(w))
print('fixes', len(fx), 'accepted', acc, 'gated', gat, 'resets', rst, 'window', len(w))
