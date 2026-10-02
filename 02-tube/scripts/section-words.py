#!/usr/bin/env python3
"""Word count per top-level section of report.qmd, with the share of the body, to check the agreed proportions."""
import re, sys
txt = open(sys.argv[1] if len(sys.argv) > 1 else 'report.qmd').read()
body = txt.split('\n---\n', 2)[-1]
parts = re.split(r'\n(?=# )', body); rows = []
for part in parts:
    title = part.split('\n', 1)[0].lstrip('# ').split(' {')[0]
    words = len(re.sub(r'!\[.*?\]\(.*?\)\{.*?\}', '', part).split())
    rows.append((title, words))
total = sum(w for _, w in rows)
for t, w in rows: print(f"{w:6} {100*w/total:5.1f}%  {t}")
print(f"{total:6} total")
