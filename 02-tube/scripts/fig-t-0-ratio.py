#!/usr/bin/env python3
"""Schematic of the ratio model: f = 1 - t/T along the segment into the next stop, and its arms."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
from matplotlib.patches import FancyArrowPatch
fig, ax = plt.subplots(figsize=(7.2, 3.0)); ax.axis('off'); ax.set_xlim(0, 10); ax.set_ylim(0, 3.3)
# the segment: a gentle curve from stop i-1 (x=1) to stop i (x=9)
import math
xs = [1 + 8 * k / 100 for k in range(101)]; ys = [1.6 + 0.35 * math.sin(math.pi * (x - 1) / 8) for x in xs]
ax.plot(xs, ys, color=INK, lw=3, solid_capstyle='round')
for x, y, name in ((1, 1.6, 'stop $i-1$\n(previous)'), (9, 1.6, 'stop $i$\n(next: the row with the smallest countdown)')):
    ax.plot(x, y, 'o', ms=9, mfc='white', mec=INK, mew=1.6, zorder=3); ax.text(x, 1.15, name, ha='center', va='top', fontsize=8, color=INK)
# the train at f = 0.6
f = 0.6; k = int(f * 100); tx, ty = xs[k], ys[k]
ax.plot(tx, ty, 's', ms=11, color=RED, zorder=4); ax.text(tx + 0.22, ty + 0.02, 'train', ha='left', va='center', fontsize=8, color=RED)
# brace-like annotations: countdown t to stop i, run time T over the whole segment
ax.annotate('', xy=(9, 2.3), xytext=(1, 2.3), arrowprops=dict(arrowstyle='<->', color=GREY, lw=1)); ax.text(5, 2.36, 'run time $T$ (scheduled + 30 s dwell, or length / 12 m/s)', ha='center', va='bottom', fontsize=8, color=GREY)
ax.annotate('', xy=(9, 0.55), xytext=(tx, 0.55), arrowprops=dict(arrowstyle='<->', color=RED, lw=1)); ax.text((tx + 9) / 2, 0.62, 'countdown $t$', ha='center', va='bottom', fontsize=8, color=RED)
ax.annotate('', xy=(tx, 0.3), xytext=(1, 0.3), arrowprops=dict(arrowstyle='<->', color=INK, lw=1)); ax.text((1 + tx) / 2, 0.05, '$f = 1 - t/T$ of the arc length', ha='center', va='bottom', fontsize=8, color=INK)
# arms
ax.text(9.0, 3.2, '"At stop $i$" or $t \\leq 15$ s: $f = 1$', ha='right', va='top', fontsize=7.5, color=INK)
ax.text(9.0, 3.0, '"Approaching stop $i$": $f \\geq 0.85$', ha='right', va='top', fontsize=7.5, color=INK)
ax.text(1.0, 3.2, '"Between" / "Left" and $t > T$: $T := t + 20$ s', ha='left', va='top', fontsize=7.5, color=INK)
ax.text(1.0, 3.0, 'displayed $f$ never decreases', ha='left', va='top', fontsize=7.5, color=INK)
fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01); save(fig, 'fig-t-0-ratio')
