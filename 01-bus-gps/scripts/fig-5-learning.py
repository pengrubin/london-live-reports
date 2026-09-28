#!/usr/bin/env python3
"""Section 5 figures from one day of fixes and the learned paths:
  fig-5-1 route 68: the fix cloud of one day over the learned inbound path
  fig-5-2 one vertex zoomed: points assigned to it, the corridor, the trimmed 20 %
  fig-5-4 a low-coverage route (244 outbound): where the fixes leave the path
"""
import json, os, sys, math
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import *
M_LAT = 110_540.0; M_LON = 111_320.0 * math.cos(math.radians(51.5))
def load(key):
    d = json.load(open(os.path.join(DATA, 'cases', key.replace(':', '_') + '.json')))
    xs = [x * M_LON for x, y in d['poly']]; ys = [y * M_LAT for x, y in d['poly']]; cum = [0.0]
    for i in range(1, len(xs)): cum.append(cum[-1] + math.hypot(xs[i]-xs[i-1], ys[i]-ys[i-1]))
    return xs, ys, cum, d.get('quality', {})
def project(P, px, py):
    xs, ys, cum, _ = P; best = (0.0, float('inf'), 0, 0.0)
    for i in range(len(xs)-1):
        ax, ay, bx, by = xs[i], ys[i], xs[i+1], ys[i+1]; dx, dy = bx-ax, by-ay; L2 = dx*dx+dy*dy
        t = 0 if L2 == 0 else max(0, min(1, ((px-ax)*dx+(py-ay)*dy)/L2)); dd = math.hypot(px-(ax+t*dx), py-(ay+t*dy))
        if dd < best[1]: best = (cum[i]+t*math.sqrt(L2), dd, i, t)
    return best
def fixes(path, key):
    return [json.loads(l) for l in open(path) if f'"k":"{key}"' in l]

# fig 5.1 / 5.2 : route 68 inbound
P = load('TFLO:68:inbound'); F = fixes(os.path.join(DATA, 'cases', '68-2026-09-25.jsonl'), 'TFLO:68:inbound')
pr = [(r['x']*M_LON, r['y']*M_LAT) + project(P, r['x']*M_LON, r['y']*M_LAT) for r in F]
ox, oy = P[0][0], P[1][0]
fig, ax = plt.subplots(figsize=(5.0, 6.4))
ax.scatter([p[0]-ox for p in pr], [p[1]-oy for p in pr], s=1.5, color=RED, alpha=0.35, label=f'{len(F)} fixes labelled 68 inbound, 25 Sep')
ax.plot([x-ox for x in P[0]], [y-oy for y in P[1]], lw=1.2, color=INK, label=f'learned path, {len(P[0])} vertices at 25 m, residual {P[3].get("meanResidualM")} m')
ax.set_aspect('equal'); ax.set_xlim(-3000, 6000); ax.set_xlabel('m east of the path start'); ax.set_ylabel('m north')
h, l = ax.get_legend_handles_labels(); fig.legend(h, l, loc='lower center', ncol=1, fontsize=7.5, bbox_to_anchor=(0.5, -0.02))
ax.set_title('Route 68 inbound: one day of raw fixes\nover the path learned from three days', loc='center')
fig.tight_layout(rect=(0, 0.06, 1, 1)); save(fig, 'fig-5-1-cloud-68')

# pick a mid-route vertex with plenty of support; corridor = clamp(30, p90 resid, 60)
res = sorted(p[3] for p in pr if p[3] <= 100); corridor = min(60, max(30, res[int(0.9*len(res))]))
vi = len(P[0]) // 2
best_v = max(range(20, len(P[0])-20), key=lambda v: sum(1 for p in pr if p[3] <= corridor and (p[4] if p[5] < 0.5 else p[4]+1) == v))
vx, vy = P[0][best_v], P[1][best_v]
pts = [(p[0]-vx, p[1]-vy, p[3]) for p in pr if (p[4] if p[5] < 0.5 else p[4]+1) == best_v and p[3] <= 100]
pts.sort(key=lambda p: p[2]); keep = max(4, math.ceil(len(pts) * 0.8)); kept, trimmed = pts[:keep], pts[keep:]
out = [(p[0]-vx, p[1]-vy) for p in pr if (p[4] if p[5] < 0.5 else p[4]+1) == best_v and p[3] > corridor]
fig, ax = plt.subplots(figsize=(4.6, 5.2))
ax.plot([x-vx for x in P[0][best_v-3:best_v+4]], [y-vy for y in P[1][best_v-3:best_v+4]], lw=1.2, color=INK, label='learned path (the seed is the previous night\'s result or a median journey)')
for sgn in (1, -1):  # corridor band, approximate normal at the vertex
    dx, dy = P[0][best_v+1]-P[0][best_v-1], P[1][best_v+1]-P[1][best_v-1]; L = math.hypot(dx, dy); nx, ny = -dy/L, dx/L
    ax.plot([x-vx+sgn*corridor*nx for x in P[0][best_v-3:best_v+4]], [y-vy+sgn*corridor*ny for y in P[1][best_v-3:best_v+4]], lw=0.8, ls='--', color=GREY)
ax.scatter([p[0] for p in kept], [p[1] for p in kept], s=10, color=INK, label=f'kept {len(kept)} nearest 80 %')
ax.scatter([p[0] for p in trimmed], [p[1] for p in trimmed], s=10, facecolors='none', edgecolors=AMBER, label=f'trimmed {len(trimmed)} (worst 20 %)')
ax.scatter([p[0] for p in out], [p[1] for p in out], s=8, color=RED, alpha=0.6, label=f'outside corridor ({len(out)})')
mx = sum(p[0] for p in kept)/len(kept); my = sum(p[1] for p in kept)/len(kept)
ax.scatter([0], [0], s=60, marker='s', color=INK, zorder=5); ax.scatter([mx], [my], s=70, marker='*', color=GREEN, zorder=6, label='trimmed mean (new vertex)')
ax.set_aspect('equal'); ax.set_xlim(-70, 70); ax.set_ylim(-70, 70); ax.set_xlabel('m'); ax.set_ylabel('m'); ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=6.5)
ax.set_title(f'One vertex: corridor ±{corridor:.0f} m, points assigned to it', loc='left', fontsize=8.5)
fig.tight_layout(); save(fig, 'fig-5-2-vertex-zoom')
put(learn_case_route='68 inbound', learn_case_fixes=len(F), learn_case_corridor_m=round(corridor), learn_case_vertex_points=len(pts), learn_case_vertex_trimmed=len(trimmed))

# fig 5.4: low coverage example 244 outbound
P2 = load('TFLO:244:outbound'); F2 = fixes(os.path.join(DATA, 'cases', '244-outbound-2026-09-25.jsonl'), 'TFLO:244:outbound')
pr2 = [(r['x']*M_LON, r['y']*M_LAT) + project(P2, r['x']*M_LON, r['y']*M_LAT) for r in F2]
res2 = sorted(p[3] for p in pr2 if p[3] <= 100); cor2 = min(60, max(30, res2[int(0.9*len(res2))])) if res2 else 30
inside = sum(1 for p in pr2 if p[3] <= cor2)
ox, oy = P2[0][0], P2[1][0]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
ax.scatter([p[0]-ox for p in pr2 if p[3] <= cor2], [p[1]-oy for p in pr2 if p[3] <= cor2], s=1.5, color=GREY, alpha=0.4, label=f'inside corridor ({inside})')
ax.scatter([p[0]-ox for p in pr2 if p[3] > cor2], [p[1]-oy for p in pr2 if p[3] > cor2], s=2, color=RED, alpha=0.6, label=f'outside corridor ({len(pr2)-inside})')
ax.plot([x-ox for x in P2[0]], [y-oy for y in P2[1]], lw=1.2, color=INK, label=f'learned path (coverage {P2[3].get("coverage")}, {P2[3].get("journeys")} journeys)')
ax.set_aspect('equal'); ax.set_xlabel('m east of the path start'); ax.set_ylabel('m north'); ax.legend(loc='lower right', fontsize=7.5)
ax.set_title('Route 244 outbound: a path whose fix cloud it only partly covers', loc='left'); fig.tight_layout(); save(fig, 'fig-5-4-low-coverage')
put(lowcov_case_route='244 outbound', lowcov_case_fixes=len(F2), lowcov_case_inside_pct=round(100*inside/len(pr2), 1), lowcov_case_coverage=P2[3].get('coverage'))
