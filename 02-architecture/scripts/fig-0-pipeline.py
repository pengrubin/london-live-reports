#!/usr/bin/env python3
"""Summary figure: the six stages as a pipeline, every arrow labelled with its
measured rate and every box with its measured cost (daytime calibration)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
N = json.load(open(os.path.join(os.path.dirname(DATA), 'numbers.json')))
SUB = '#4a5563'

def box(ax, x, y, w, h, title, lines, fc='#f3f5f7', ec=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.08', fc=fc, ec=ec, lw=1))
    ax.text(x + w/2, y + h - 0.22, title, ha='center', va='center', fontsize=8.5, fontweight='bold', color=INK)
    ax.text(x + w/2, y + (h - 0.4)/2, '\n'.join(lines), ha='center', va='center', fontsize=6.6, color=SUB, linespacing=1.25)
def arrow(ax, p, q, label='', color=INK, above=True, rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle='-|>', mutation_scale=9, lw=0.9, color=color, connectionstyle=f'arc3,rad={rad}'))
    if label:
        ax.text((p[0]+q[0])/2, (p[1]+q[1])/2 + (0.13 if above else -0.13), label, ha='center', va='bottom' if above else 'top', fontsize=6.4, color=color, bbox=dict(boxstyle='square,pad=0.12', fc='white', ec='none'))

fig, ax = plt.subplots(figsize=(7.2, 4.4)); ax.set_xlim(0, 10); ax.set_ylim(0, 5.6); ax.axis('off')
W, H = 1.75, 1.45
# top row: live path
box(ax, 0.2, 3.7, W, H, 'Upstream feeds', [f"bus GPS {N['bus_wire_mb']} MB / {N['bus_poll_s']} s", f"train predictions {N['arrivals_wire_kb']} KB / 15 s", 'rail boards, status, AIS,', 'ADS-B, bikes, tides'], fc='#fde8ea', ec=RED)
box(ax, 2.3, 3.7, W, H, '1 Ingest + parse', [f"{N['bus_records_per_s']} bus records / s", f"{N['cpu_ms_bods_parse'] + N['cpu_ms_io_glue'] + N['cpu_ms_undici']:.0f} ms CPU / 15 s", f"{N['parse_us_per_element']} µs per record"])
box(ax, 4.4, 3.7, W, H, '2 State + caches', [f"{N['bus_live_day']:,} live vehicles", f"heap {N['heap_fit_intercept_mb']} MB + {N['heap_fit_kb_per_vehicle_state']} KB", 'per vehicle state', f"prod heap p50 {N['prod_heap_median_mb']:.0f} MB"])
box(ax, 6.5, 3.7, W, H, '3 Online detection', [f"{N['bus_live_day']:,} projections / 15 s", f"{N['cpu_ms_detector']} ms CPU / 15 s", f"{N['detector_us_per_bus']} µs per vehicle", f"+ leaderboard {N['cpu_ms_leaderboard']} ms"])
box(ax, 8.4, 3.7, 1.45, H, '5 Serve', [f"{N['tab_requests_per_min']} req / min", 'per open tab', f"{N['tab_kb_per_min']/1000:.1f} MB / min", '(brotli)'], fc='#e9f4ee', ec=GREEN)
# bottom row: persistence and batch
box(ax, 2.3, 1.2, W, H, '4 Persist', [f"{N['new_fixes_per_s_day']} new fixes / s", f"{N['trace_gz_mb_per_day']} MB / day (gz)", f"{N['cpu_ms_trace']} ms CPU / 15 s", '7 days kept'])
box(ax, 4.4, 1.2, W, H, '6 Batch (nightly)', ['route learner: 3 days', f"of traces, ~30 min", 'separate process', 'rollups, corridors'], fc='#eef0f2', ec=GREY)
box(ax, 6.5, 1.2, W, H, 'Browser', [f"{N['tab_requests_per_min']} req / min", 'inference, smoothing,', 'filtering: all client-side', 'server CPU ∝ viewers: ~0'], fc='white', ec=INK)
# arrows
arrow(ax, (0.2+W, 4.42), (2.3, 4.42), f"{N['bus_decoded_mb']} MB XML / 15 s")
arrow(ax, (2.3+W, 4.42), (4.4, 4.42), f"{N['bus_live_day']:,} vehicles")
arrow(ax, (4.4+W, 4.42), (6.5, 4.42), 'per poll')
arrow(ax, (6.5+W, 4.42), (8.4, 4.42), 'events')
arrow(ax, (3.175, 3.7), (3.175, 1.2+H), f"{N['new_fixes_per_poll_day']:,} new fixes / 15 s", above=False)
arrow(ax, (2.3+W, 1.9), (4.4, 1.9), 'traces', color=GREY)
arrow(ax, (5.275, 1.2+H), (5.275, 3.7), 'learned paths', color=GREEN)
arrow(ax, (8.4+0.7, 3.7), (7.375, 1.2+H), f"buses {N['ep_buses_br_kb']:.0f} KB, trains {N['ep_arrivals_br_kb']:.0f} KB (brotli)", color=GREEN, rad=0.0, above=False)
ax.text(0.2, 0.7, f"Measured {N['cal_day_date']} {N['cal_day_window']} (weekday daytime): production feeds, local replica on {N['cal_machine']}.", fontsize=6.6, color=SUB)
ax.text(0.2, 0.42, f"Whole process: {N['cpu_process_ms_control']:.0f} ms CPU per 15 s poll = {N['cpu_process_util_control_pct']}% of one core. Production heap p50 {N['prod_heap_median_mb']:.0f} MB, RSS p50 {N['prod_rss_median_mb']:.0f} MB.", fontsize=6.6, color=SUB)
fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01); save(fig, 'fig-0-pipeline')
