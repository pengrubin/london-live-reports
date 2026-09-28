"""Shared matplotlib style for every figure in the report (print-friendly, light)."""
import os, json, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(ROOT, 'figures'); DATA = os.path.join(ROOT, 'data')
NUMBERS = os.path.join(ROOT, 'numbers.json')

# palette: ink for primary series, bus red for emphasis, greys for context
INK = '#1f2a37'; RED = '#c8102e'; GREEN = '#2e8b57'; AMBER = '#d98c1e'; GREY = '#8a94a0'; LIGHT = '#d9dee4'
plt.rcParams.update({
    'font.family': 'sans-serif', 'font.size': 9, 'axes.titlesize': 9.5, 'axes.labelsize': 9,
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True, 'grid.alpha': 0.25,
    'grid.linewidth': 0.6, 'legend.frameon': False, 'legend.fontsize': 8, 'figure.dpi': 110,
    'savefig.dpi': 200, 'savefig.bbox': 'tight', 'axes.prop_cycle': matplotlib.cycler(color=[INK, RED, GREEN, AMBER, GREY]),
})

def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, name + '.png'))
    fig.savefig(os.path.join(FIG, name + '.svg'))
    plt.close(fig)
    print('wrote', name)

def put(**kv):
    """Merge measured numbers into numbers.json (the prose reads from it)."""
    try: cur = json.load(open(NUMBERS))
    except Exception: cur = {}
    cur.update(kv)
    json.dump(cur, open(NUMBERS, 'w'), indent=1, sort_keys=True)
