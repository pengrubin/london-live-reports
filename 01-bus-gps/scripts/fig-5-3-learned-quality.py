#!/usr/bin/env python3
"""Fig 5.3: distribution of meanResidualM and coverage over every learned route
(latest snapshot), TfL vs other operators. Numbers: counts, quantiles, gate."""
import json, glob, os, sys
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
snap = sorted(glob.glob(os.path.join(DATA, 'learned', '*')))[-1]
res = {'TFLO': [], 'other': []}; cov = {'TFLO': [], 'other': []}; jn = []
for f in glob.glob(os.path.join(snap, 'routes', '*.json')):
    d = json.load(open(f)); q = d.get('quality', {}); g = 'TFLO' if d.get('key', '').startswith('TFLO:') else 'other'
    if 'meanResidualM' in q: res[g].append(q['meanResidualM'])
    if 'coverage' in q: cov[g].append(q['coverage'])
    if 'journeys' in q: jn.append(q['journeys'])
fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.7))
axes[0].hist([res['TFLO'], res['other']], bins=range(0, 37, 1), stacked=True, color=[INK, GREY], label=['TfL routes', 'other operators'])
axes[0].axvline(35, color=RED, lw=1, ls='--'); axes[0].text(34.5, axes[0].get_ylim()[1] * 0.9, 'gate 35 m', ha='right', color=RED, fontsize=8)
axes[0].set_xlabel('mean residual of fixes to learned path (m)'); axes[0].set_ylabel('routes'); axes[0].legend()
axes[1].hist([cov['TFLO'], cov['other']], bins=[i / 50 for i in range(20, 51)], stacked=True, color=[INK, GREY])
axes[1].axvline(0.9, color=RED, lw=1, ls='--'); axes[1].text(0.895, axes[1].get_ylim()[1] * 0.9, 'repair below 0.9', ha='right', color=RED, fontsize=8)
axes[1].set_xlabel('coverage (share of fixes inside the corridor)'); axes[1].set_ylabel('routes')
fig.suptitle(f'Quality of every learned route, snapshot {os.path.basename(snap)}', x=0.01, ha='left', fontsize=9.5)
fig.tight_layout(); save(fig, 'fig-5-3-learned-quality')
q = lambda a, p: sorted(a)[min(len(a) - 1, int(p * len(a)))]
allr = res['TFLO'] + res['other']; allc = cov['TFLO'] + cov['other']
put(learned_snapshot=os.path.basename(snap), learned_routes_total=len(allr), learned_routes_tflo=len(res['TFLO']),
    learned_residual_p50=q(allr, .5), learned_residual_p90=q(allr, .9), learned_residual_max=max(allr),
    learned_residual_tflo_p50=q(res['TFLO'], .5), learned_coverage_p50=q(allc, .5), learned_coverage_p10=q(allc, .1),
    learned_coverage_below_0_9=sum(1 for c in allc if c < 0.9), learned_journeys_p50=q(jn, .5))
