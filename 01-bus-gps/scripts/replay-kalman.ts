// Offline replay of the frontend's along-route Kalman filter on one vehicle's
// day of BODS fixes, using the production module verbatim (scripts/vendor/
// bus-kalman.ts is a copy of frontend/src/realtime/bus-kalman.ts at origin/main).
//
// Reproduces what buses.ts does per fix: project the fix onto the learned
// polyline -> (s, d); snap hysteresis on d (50 m on / 80 m off); while
// snapped, kfStep with the route's measurement variance; between fixes the
// displayed arc length coasts with kfCoastS. Emits one CSV row per fix plus
// one per 5 s of display time so the coast curve can be drawn.
//
// usage: tsx replay-kalman.ts <fixes.jsonl> <learned.json> <key> <out.csv>
import { readFileSync, writeFileSync } from 'node:fs';
import {
  kfInit, kfStep, kfCoastS, measurementVariance, cumulativeLengthsM, pointAtArclen,
  KF_COAST_TAU_S, type BusKfState, type ArcPoint,
} from './vendor/bus-kalman';

const [fixesPath, learnedPath, key, outPath] = process.argv.slice(2);
const SNAP_ON_M = 50, SNAP_OFF_M = 80, SNAP_LOCAL_WINDOW = 30;
const M_LAT = 110_540, M_LON = 111_320 * Math.cos((51.5 * Math.PI) / 180);

const learned = JSON.parse(readFileSync(learnedPath, 'utf8')) as { poly: [number, number][]; quality?: { meanResidualM?: number } };
const n = learned.poly.length;
const xs = new Float64Array(n), ys = new Float64Array(n);
learned.poly.forEach(([lon, lat], i) => { xs[i] = lon * M_LON; ys[i] = lat * M_LAT; });
const cum = cumulativeLengthsM(xs, ys);
const rVar = measurementVariance(learned.quality?.meanResidualM);

/** Nearest point on the polyline; searches segs [lo, hi] only. Returns {s, d, seg}. */
function project(px: number, py: number, lo: number, hi: number) {
  let best = { s: 0, d: Infinity, seg: 0 };
  for (let i = Math.max(0, lo); i < Math.min(n - 1, hi); i++) {
    const ax = xs[i], ay = ys[i], bx = xs[i + 1], by = ys[i + 1];
    const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
    let t = L2 > 0 ? ((px - ax) * dx + (py - ay) * dy) / L2 : 0; t = Math.max(0, Math.min(1, t));
    const d = Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
    if (d < best.d) best = { s: cum[i] + t * Math.sqrt(L2), d, seg: i };
  }
  return best;
}

type Fix = { k: string; i: string; x: number; y: number; t: number };
const fixes = readFileSync(fixesPath, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as Fix)
  .filter((f) => f.k === key).sort((a, b) => a.t - b.t);

const rows: string[] = ['kind,t,z_s,d_m,snapped,kf_s,kf_v,sigma_s,result,disp_s'];
let snapped = false, st: BusKfState | null = null, seg = 0, lastFixT = 0;
const pt: ArcPoint = { x: 0, y: 0, seg: 0, tx: 0, ty: 0 } as unknown as ArcPoint;
let accepted = 0, gated = 0, resets = 0, offRoute = 0;
for (let idx = 0; idx < fixes.length; idx++) {
  const f = fixes[idx];
  const px = f.x * M_LON, py = f.y * M_LAT;
  let p = snapped ? project(px, py, seg - SNAP_LOCAL_WINDOW, seg + SNAP_LOCAL_WINDOW) : project(px, py, 0, n);
  if (!snapped && p.d >= SNAP_ON_M) p = project(px, py, 0, n);
  const tMs = f.t * 1000;
  // display coast samples between the previous fix and this one
  if (st && snapped && lastFixT > 0) {
    for (let tt = lastFixT + 5; tt < f.t; tt += 5) rows.push(`coast,${tt},,,1,,,,,${kfCoastS(st, tt * 1000).toFixed(1)}`);
  }
  if (!snapped && p.d < SNAP_ON_M) { snapped = true; seg = p.seg; st = kfInit(p.s, 0, tMs); }
  else if (snapped && p.d > SNAP_OFF_M) { snapped = false; st = null; offRoute++; }
  let result = '';
  if (snapped && st) {
    if (idx > 0 && tMs === st.tMs) result = 'dup';
    else {
      const r = kfStep(st, p.s, tMs, rVar); result = r;
      if (r === 'accepted') accepted++; else if (r === 'gated') gated++; else resets++;
      if (r === 'reset') { st = kfInit(p.s, 0, tMs); }
      pointAtArclen(xs, ys, cum, st.s, seg, pt); seg = pt.seg;
    }
  }
  rows.push(`fix,${f.t},${p.s.toFixed(1)},${p.d.toFixed(1)},${snapped ? 1 : 0},${st ? st.s.toFixed(1) : ''},${st ? st.v.toFixed(2) : ''},${st ? Math.sqrt(st.pS).toFixed(1) : ''},${result},${st ? st.s.toFixed(1) : ''}`);
  lastFixT = f.t;
}
writeFileSync(outPath, rows.join('\n') + '\n');
console.log(JSON.stringify({ fixes: fixes.length, accepted, gated, resets, snapReleases: offRoute, rSigmaM: Math.sqrt(rVar).toFixed(1), routeLengthM: Math.round(cum[n - 1]), coastTauS: KF_COAST_TAU_S }));
