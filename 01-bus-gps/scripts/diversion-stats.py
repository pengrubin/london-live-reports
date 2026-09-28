#!/usr/bin/env python3
"""Aggregate the diversion event transition log into per-event rows.

Input : <archive>/diversions/YYYY-MM-DD.jsonl, one transition per line:
        {"t", "id", "transition", "event": {status, displayWorthy, startedAt,
         lastEvidenceAt, routes[], vehicles, members, centroid, severity?, tfl?}}
Output: data/diversion-events.csv (one row per event id) and
        data/diversion-summary.json (counts used by section 7.8).
"""
import json, glob, os, sys, csv
from collections import defaultdict, Counter

archive, out_dir = sys.argv[1], sys.argv[2]
events = {}
transitions = Counter()
for path in sorted(glob.glob(os.path.join(archive, 'diversions', '*.jsonl'))):
    with open(path) as f:
        for line in f:
            try: r = json.loads(line)
            except Exception: continue
            e = r.get('event') or {}
            ev = events.setdefault(r['id'], {'id': r['id'], 'first_t': r['t'], 'last_t': r['t'], 'transitions': [],
                                             'displayWorthy': False, 'max_vehicles': 0, 'max_members': 0,
                                             'routes': set(), 'severity': None, 'tfl_loc': None, 'tfl_dist': None,
                                             'startedAt': e.get('startedAt'), 'lastEvidenceAt': e.get('lastEvidenceAt'),
                                             'centroid': e.get('centroid'), 'final_status': None})
            ev['last_t'] = max(ev['last_t'], r['t']); ev['transitions'].append(r['transition'])
            ev['displayWorthy'] |= bool(e.get('displayWorthy'))
            ev['max_vehicles'] = max(ev['max_vehicles'], e.get('vehicles', 0))
            ev['max_members'] = max(ev['max_members'], e.get('members', 0))
            ev['routes'].update(e.get('routes', []))
            if e.get('severity'): ev['severity'] = e['severity']
            if e.get('lastEvidenceAt'): ev['lastEvidenceAt'] = max(ev['lastEvidenceAt'] or 0, e['lastEvidenceAt'])
            tfl = e.get('tfl')
            if isinstance(tfl, dict): ev['tfl_loc'] = tfl.get('loc'); ev['tfl_dist'] = tfl.get('dist')
            ev['final_status'] = e.get('status')
            transitions[r['transition']] += 1

rows = []
for ev in events.values():
    dur = (ev['lastEvidenceAt'] or ev['last_t']) - (ev['startedAt'] or ev['first_t'])
    outcome = 'recovered' if 'recovering' in ev['transitions'] else ('stale' if 'stale' in ev['transitions'] else 'other')
    rows.append({'id': ev['id'], 'startedAt': ev['startedAt'], 'lastEvidenceAt': ev['lastEvidenceAt'],
                 'duration_s': dur, 'displayWorthy': int(ev['displayWorthy']), 'severity': ev['severity'] or '',
                 'max_vehicles': ev['max_vehicles'], 'max_members': ev['max_members'], 'n_routes': len(ev['routes']),
                 'routes': ' '.join(sorted(ev['routes'])), 'outcome': outcome,
                 'tfl_matched': int(ev['tfl_loc'] is not None), 'tfl_dist_m': ev['tfl_dist'] if ev['tfl_dist'] is not None else '',
                 'lon': ev['centroid'][0] if ev['centroid'] else '', 'lat': ev['centroid'][1] if ev['centroid'] else ''})
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, 'diversion-events.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

shown = [r for r in rows if r['displayWorthy']]
def pct(a, b): return round(100.0 * a / b, 1) if b else None
summary = {
    'days': len(glob.glob(os.path.join(archive, 'diversions', '*.jsonl'))),
    'events_total': len(rows), 'events_displayed': len(shown),
    'displayed_by_severity': dict(Counter(r['severity'] for r in shown)),
    'displayed_by_outcome': dict(Counter(r['outcome'] for r in shown)),
    'displayed_tfl_matched': sum(r['tfl_matched'] for r in shown),
    'displayed_tfl_matched_pct': pct(sum(r['tfl_matched'] for r in shown), len(shown)),
    'displayed_duration_s_p50': sorted(r['duration_s'] for r in shown)[len(shown) // 2] if shown else None,
    'displayed_routes_p50': sorted(r['n_routes'] for r in shown)[len(shown) // 2] if shown else None,
    'transitions': dict(transitions),
}
with open(os.path.join(out_dir, 'diversion-summary.json'), 'w') as f: json.dump(summary, f, indent=1)
print(json.dumps(summary, indent=1))
