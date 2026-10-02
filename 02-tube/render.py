#!/usr/bin/env python3
"""Fill {{key}} placeholders in report.template.qmd from numbers.json and
render with Quarto (HTML + PDF). Unknown keys fail loudly, so the prose can
never drift from the data. Nested keys use dots: {{journeys.complete.n_per_day_median}}.
Formatting suffixes: {{key|int}} thousands separators, {{key|1}} one decimal, {{key|pct}}.

  python3 render.py            # fill + render both formats
  python3 render.py --fill     # only write report.qmd
"""
import json, re, sys, os, subprocess
ROOT = os.path.dirname(os.path.abspath(__file__))
nums = json.load(open(os.path.join(ROOT, 'numbers.json')))
def lookup(path):
    v = nums
    for p in path.split('.'):
        if isinstance(v, dict) and p in v: v = v[p]
        elif isinstance(v, list) and p.isdigit(): v = v[int(p)]
        else: raise KeyError(path)
    return v
def fmt(v, spec):
    if spec == 'int': return f'{int(round(float(v))):,}'
    if spec == 'pct': return f'{float(v):.0f}%'
    if spec and spec.isdigit(): return f'{float(v):,.{int(spec)}f}'
    if isinstance(v, float): return f'{v:,.1f}' if abs(v) >= 100 else f'{v:g}'
    if isinstance(v, int): return f'{v:,}'
    return str(v)
missing = []
def sub(m):
    key, spec = m.group(1), m.group(2)
    try: return fmt(lookup(key), spec)
    except KeyError: missing.append(key); return m.group(0)
src = open(os.path.join(ROOT, 'report.template.qmd')).read()
out = re.sub(r'\{\{([a-zA-Z0-9_.]+)(?:\|([a-z0-9]+))?\}\}', sub, src)
if missing:
    print('MISSING numbers:', sorted(set(missing))); sys.exit(1)
open(os.path.join(ROOT, 'report.qmd'), 'w').write(out)
print('filled report.qmd')
if '--fill' not in sys.argv:
    env = dict(os.environ, PATH=os.path.expanduser('~/.local/bin') + ':' + os.environ['PATH'])
    subprocess.run(['quarto', 'render', 'report.qmd'], cwd=ROOT, env=env, check=True)
