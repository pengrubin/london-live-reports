// One synthetic viewer + /health sampler for the LOCAL profiling run (D).
// Talks only to http://127.0.0.1:<port> - never to production.
//
//   node synthetic-viewer.mjs --port 3999 --out <dir> --warmup 60 --quiet 360 --viewer 360
//
// Phases:
//   warmup  : nothing but /health every 30 s (pollers start, indexes build)
//   quiet   : still only /health - the pipeline's own cost, no viewer
//   viewer  : one browser's worth of polling, at the frontend's own intervals
//             (frontend/src/layers/*.ts POLL_INTERVAL_MS), Accept-Encoding: br
//
// Writes health.jsonl (every 30 s, all phases), viewer-requests.jsonl (one row
// per request: path, status, wire bytes, ms, x-cache) and phases.json.

import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { request } from 'node:http';
import { join } from 'node:path';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, arg, i, all) => {
    if (arg.startsWith('--')) pairs.push([arg.slice(2), all[i + 1]]);
    return pairs;
  }, []),
);
const PORT = Number(args.port ?? 3999);
const OUT = args.out;
const WARMUP_S = Number(args.warmup ?? 60);
const QUIET_S = Number(args.quiet ?? 360);
const VIEWER_S = Number(args.viewer ?? 360);
const HEALTH_INTERVAL_MS = 30_000;

const LINES = [
  'bakerloo', 'central', 'circle', 'district', 'hammersmith-city', 'jubilee', 'metropolitan',
  'northern', 'piccadilly', 'victoria', 'waterloo-city', 'dlr', 'elizabeth', 'liberty', 'lioness',
  'mildmay', 'suffragette', 'weaver', 'windrush', 'tram', 'london-cable-car', 'rb1', 'rb4', 'rb6',
  'woolwich-ferry',
].join(',');

// path -> poll interval (ms), taken from the frontend source on origin/main.
const VIEWER_POLLS = [
  [`/api/arrivals?lines=${LINES}`, 10_000],
  ['/api/buses', 15_000],
  ['/api/aircraft', 5_000],
  ['/api/vessels', 10_000],
  ['/api/bikes', 60_000],
  ['/api/diversions', 90_000],
  ['/api/disruptions', 90_000],
  ['/api/road-disruptions', 120_000],
  ['/api/bus-stop-closures', 300_000],
  ['/api/tide-gauges', 300_000],
  ['/api/leaderboard?period=day&mode=bus', 30_000],
];

mkdirSync(OUT, { recursive: true });

function get(path, encoding) {
  return new Promise((resolve) => {
    const started = performance.now();
    const req = request(
      { host: '127.0.0.1', port: PORT, path, method: 'GET', headers: { 'accept-encoding': encoding } },
      (res) => {
        let bytes = 0;
        const chunks = [];
        res.on('data', (chunk) => {
          bytes += chunk.length;
          if (encoding === 'identity') chunks.push(chunk);
        });
        res.on('end', () =>
          resolve({
            path: path.split('?')[0],
            status: res.statusCode,
            wireBytes: bytes,
            ms: Math.round(performance.now() - started),
            xCache: res.headers['x-cache'] ?? null,
            contentEncoding: res.headers['content-encoding'] ?? 'identity',
            body: encoding === 'identity' ? Buffer.concat(chunks) : null,
          }),
        );
      },
    );
    req.on('error', (err) => resolve({ path: path.split('?')[0], status: 0, error: String(err.code ?? err) }));
    req.setTimeout(30_000, () => req.destroy(new Error('timeout')));
    req.end();
  });
}

async function health(phase) {
  const res = await get('/health', 'identity');
  if (res.status !== 200) return;
  try {
    const body = JSON.parse(res.body.toString('utf8'));
    appendFileSync(
      join(OUT, 'health.jsonl'),
      `${JSON.stringify({ at: Date.now(), phase, uptimeS: body.uptimeS, memory: body.memory, components: body.components })}\n`,
    );
  } catch {
    // ignore a malformed health body
  }
}

let phase = 'warmup';
const t0 = Date.now();
const phases = {
  startedAt: t0,
  warmup: [t0, t0 + WARMUP_S * 1000],
  quiet: [t0 + WARMUP_S * 1000, t0 + (WARMUP_S + QUIET_S) * 1000],
  viewer: [t0 + (WARMUP_S + QUIET_S) * 1000, t0 + (WARMUP_S + QUIET_S + VIEWER_S) * 1000],
};
writeFileSync(join(OUT, 'phases.json'), JSON.stringify(phases, null, 2));

void health(phase);
const healthTimer = setInterval(() => void health(phase), HEALTH_INTERVAL_MS);
const viewerTimers = [];

setTimeout(() => {
  phase = 'quiet';
}, WARMUP_S * 1000);

setTimeout(() => {
  if (VIEWER_S <= 0) return; // control runs have no viewer phase
  phase = 'viewer';
  for (const [path, everyMs] of VIEWER_POLLS) {
    const poll = async () => {
      const res = await get(path, 'br');
      const { body: _body, ...row } = res;
      appendFileSync(join(OUT, 'viewer-requests.jsonl'), `${JSON.stringify({ at: Date.now(), ...row })}\n`);
    };
    void poll();
    viewerTimers.push(setInterval(() => void poll(), everyMs));
  }
}, (WARMUP_S + QUIET_S) * 1000);

setTimeout(async () => {
  for (const timer of viewerTimers) clearInterval(timer);
  clearInterval(healthTimer);
  phase = 'end';
  await health('end');
  process.exit(0);
}, (WARMUP_S + QUIET_S + VIEWER_S) * 1000);
