#!/usr/bin/env python3
"""Hand-laid diagrams: fig-3-1 pipeline, fig-7-2 event lifecycle state machine.
Layout rule: every label sits in its own clear space; arrows never cross text."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
SUB = '#4a5563'

def box(ax, x, y, w, h, title, sub='', fc='#f3f5f7', ec=INK, fs=8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.08', fc=fc, ec=ec, lw=1))
    if sub:
        ax.text(x + w/2, y + h*0.68, title, ha='center', va='center', fontsize=fs, fontweight='bold', color=INK)
        ax.text(x + w/2, y + h*0.3, sub, ha='center', va='center', fontsize=6.3, color=SUB, linespacing=1.15)
    else:
        ax.text(x + w/2, y + h/2, title, ha='center', va='center', fontsize=fs, fontweight='bold', color=INK)
def arrow(ax, p, q, color=INK, rad=0.0, ls='-'):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle='-|>', mutation_scale=9, lw=0.9, color=color, ls=ls, connectionstyle=f'arc3,rad={rad}'))
def label(ax, x, y, text, color=SUB, ha='center', va='center'):
    ax.text(x, y, text, ha=ha, va=va, fontsize=6.5, color=color, bbox=dict(boxstyle='square,pad=0.15', fc='white', ec='none'))

# ── fig 3.1 pipeline: four columns, four rows; boxes 2.0 wide, gaps 0.4
fig, ax = plt.subplots(figsize=(7.2, 4.9)); ax.set_xlim(0, 10); ax.set_ylim(0, 6.1); ax.axis('off')
W, H = 2.0, 0.95; C = [0.3, 2.7, 5.1, 7.5]; R = [4.9, 3.5, 2.05, 0.6]
box(ax, C[0], R[0], W, H, 'BODS SIRI-VM', 'every 15 s, ~7.5 MB XML\n~8.9k vehicles', fc='#fde8ea', ec=RED)
box(ax, C[1], R[0], W, H, 'Parser', 'string scan, no DOM\nevery field copied')
box(ax, C[2], R[0], W, H, '/api/buses', 'short-key rows\ni, l, o, r, d, x, y, b, t')
box(ax, C[3], R[0], W, H, 'Browser', 'snap + Kalman filter\nrender at ≤ 15 Hz')
box(ax, C[1], R[1], W, H, 'TraceWriter', 'JSONL {k, i, x, y, t}\n7 days, 2 GB cap')
box(ax, C[2], R[1], W, H, 'DiversionDetector', 'project → (s, d)\nexcursions → events')
box(ax, C[3], R[1], W, H, '/api/diversions', 'red, amber,\ngreen, grey')
box(ax, C[0], R[2], W, H, 'fetch-bus-prior', 'weekly, BODS timetables\n(none for TfL routes)')
box(ax, C[1], R[2], W, H, 'learn-bus-routes', 'nightly, last 3 days\nseed, fit, snap, gate')
box(ax, C[2], R[2], W, H, 'learned paths', 'one JSON per key\npoly + quality', fc='#e9f4ee', ec=GREEN)
box(ax, C[1], R[3], W, H, 'RollupWriter', 'hourly, per key per day\njourneys, speed, residual')
box(ax, C[2], R[3], W, H, 'CoverageWriter', 'daily corridor merge\n7-day journeys/day')
box(ax, C[3], R[3], W, H, 'Bus Flow layer', 'one GeoJSON')
mid = lambda c: c + W/2
# live row
arrow(ax, (C[0]+W, R[0]+H/2), (C[1], R[0]+H/2)); arrow(ax, (C[1]+W, R[0]+H/2), (C[2], R[0]+H/2)); arrow(ax, (C[2]+W, R[0]+H/2), (C[3], R[0]+H/2))
arrow(ax, (mid(C[1]), R[0]), (mid(C[1]), R[1]+H))                                  # parser -> tracewriter
arrow(ax, (C[1]+W, R[0]+0.15), (C[2], R[1]+H-0.1))                                  # parser -> detector (short diagonal in the gap)
arrow(ax, (C[2]+W, R[1]+H/2), (C[3], R[1]+H/2))                                      # detector -> api
# batch
arrow(ax, (mid(C[1]), R[1]), (mid(C[1]), R[2]+H)); label(ax, mid(C[1])+0.55, (R[1]+R[2]+H)/2, 'traces, 3 days')
gx = C[1]-0.2  # tracewriter -> rollup: one continuous path down the gap, single arrowhead at the end
ax.plot([C[1], gx, gx], [R[1]+0.25, R[1]+0.25, R[3]+H/2], color=GREY, lw=0.9)
arrow(ax, (gx, R[3]+H/2), (C[1], R[3]+H/2), color=GREY)
label(ax, C[1]-0.3, 1.75, 'traces', ha='right')
arrow(ax, (C[0]+W, R[2]+H/2), (C[1], R[2]+H/2))
arrow(ax, (C[1]+W, R[2]+H/2), (C[2], R[2]+H/2), color=GREEN)
arrow(ax, (mid(C[2]), R[2]+H), (mid(C[2]), R[1]), color=GREEN); label(ax, mid(C[2])-0.15, (R[2]+H+R[1])/2, 'projection target', color=GREEN, ha='right')
arrow(ax, (mid(C[2]), R[2]), (mid(C[2]), R[3]+H), color=GREEN)
yy = R[1]+H+0.22; xx = C[2]+W+0.2
ax.plot([C[2]+W, xx, xx, C[3]+W/2], [R[2]+H/2, R[2]+H/2, yy, yy], color=GREEN, lw=0.9)
arrow(ax, (C[3]+W/2, yy), (C[3]+W/2, R[0]), color=GREEN); label(ax, C[3]+W/2+0.15, yy, 'snap targets', color=GREEN, ha='left')
arrow(ax, (C[1]+W, R[3]+H/2), (C[2], R[3]+H/2)); label(ax, (C[1]+W+C[2])/2, R[3]+H+0.12, 'rollups', va='bottom')
arrow(ax, (C[2]+W, R[3]+H/2), (C[3], R[3]+H/2))
ax.text(0.3, R[1]+H/2, 'live path\n(every poll)', fontsize=8, color=RED, fontweight='bold', va='center')
ax.text(0.3, R[3]+H/2, 'batch path\n(self-scheduled,\nno cron)', fontsize=8, color=INK, fontweight='bold', va='center')
fig.tight_layout(); save(fig, 'fig-3-1-pipeline')

# ── fig 7.2 lifecycle
fig, ax = plt.subplots(figsize=(7.2, 4.3)); ax.set_xlim(0, 10); ax.set_ylim(-0.5, 6.3); ax.axis('off')
BW, BH = 1.9, 1.0
box(ax, 0.4, 2.6, BW, BH, 'pending', 'excursion seen,\n< 2 vehicles', ec=GREY)
box(ax, 3.2, 2.6, BW, BH, 'active', 'displayed: red (road)\nor amber (partial)', fc='#fde8ea', ec=RED)
box(ax, 6.1, 4.3, BW, BH, 'recovering', 'green', fc='#e9f4ee', ec=GREEN)
box(ax, 6.1, 0.9, BW, BH, 'stale', 'grey', fc='#eef0f2', ec=GREY)
box(ax, 8.7, 2.6, 1.1, BH, 'gone', '', ec=GREY)
arrow(ax, (2.3, 3.1), (3.2, 3.1)); label(ax, 2.75, 3.85, '2 vehicles')
arrow(ax, (5.1, 3.45), (6.1, 4.75), rad=-0.15); label(ax, 4.6, 5.6, '20 min quiet, and 2 vehicles\ndrove 90 % of every band')
arrow(ax, (5.1, 2.75), (6.1, 1.45), rad=0.15); label(ax, 4.9, 0.45, '90 min without\nany evidence')
arrow(ax, (6.1, 4.45), (5.1, 3.2), color=RED, rad=-0.3); label(ax, 4.05, 4.55, 'new excursion:\nreactivated', color=RED)
arrow(ax, (8.0, 4.7), (8.7, 3.5), color=GREY, rad=-0.1); label(ax, 8.75, 4.75, 'after 10 min', ha='left')
arrow(ax, (8.0, 1.5), (8.7, 2.7), color=GREY, rad=0.1); label(ax, 8.75, 1.3, 'after 6 h', ha='left')
arrow(ax, (1.35, 2.6), (1.35, 1.4), color=GREY); label(ax, 1.55, 2.0, '45 min without a\nsecond vehicle:\ndiscarded', ha='left')
ax.text(0.4, -0.05, 'Bands only grow: sA = min(sExit), sB = max(sRejoin) over all members. A new excursion during recovery restarts the quiet timer.', fontsize=7, color=SUB)
ax.text(0.4, -0.4, 'The TfL road-disruption match (nearest record within 250 m of a band-segment midpoint) is shown in the popup and never changes the state.', fontsize=7, color=SUB)
fig.tight_layout(); save(fig, 'fig-7-2-lifecycle')
