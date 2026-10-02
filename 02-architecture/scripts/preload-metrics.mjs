// Preload for the local profiling run (measurement D). Loaded with
//   node --import <this file> ...
// so that no repository file is edited. It does two things:
//
//   1. every METRICS_INTERVAL_MS it appends process.cpuUsage(), memoryUsage(),
//      resourceUsage().maxRSS and event-loop utilisation to METRICS_OUT (JSONL);
//   2. it counts outbound HTTP requests per upstream through undici's
//      diagnostics channels: request count, status, and WIRE bytes received
//      (body chunks as they come off the socket, i.e. before gzip decoding).
//
// SECRETS: upstream URLs carry API keys in the query string. Only the origin
// and a sanitised pathname are ever recorded - the query string is dropped
// before anything is stored, and no request or response body is recorded.

import diagnosticsChannel from 'node:diagnostics_channel';
import { appendFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';

const METRICS_OUT = process.env.METRICS_OUT;
const METRICS_INTERVAL_MS = 30_000;
const UPSTREAM_FLUSH_MS = 30_000;

if (METRICS_OUT) {
  const startedAt = Date.now();
  let lastElu = performance.eventLoopUtilization();

  /** request object -> { key, bytes, status, encoding, startedMs } */
  const inFlight = new WeakMap();
  /** key -> aggregate since the last flush */
  let upstream = new Map();

  const sanitise = (origin, path) => {
    const pathname = String(path ?? '').split('?')[0];
    // Collapse id lists (25 line ids, 20 stop ids) and long ids to keep keys few.
    const collapsed = pathname
      .split('/')
      .map((seg) => (seg.includes(',') ? '{list}' : seg.length > 24 ? '{id}' : seg))
      .join('/');
    return `${origin}${collapsed}`;
  };

  const bump = (key) => {
    let agg = upstream.get(key);
    if (!agg) {
      agg = { requests: 0, completed: 0, wireBytes: 0, status: {}, encodings: {}, totalMs: 0 };
      upstream.set(key, agg);
    }
    return agg;
  };

  diagnosticsChannel.subscribe('undici:request:create', ({ request }) => {
    const key = sanitise(request.origin, request.path);
    inFlight.set(request, { key, bytes: 0, startedMs: performance.now() });
    bump(key).requests += 1;
  });
  diagnosticsChannel.subscribe('undici:request:headers', ({ request, response }) => {
    const state = inFlight.get(request);
    if (!state) return;
    state.status = response.statusCode;
    const headers = response.headers ?? [];
    for (let i = 0; i + 1 < headers.length; i += 2) {
      if (String(headers[i]).toLowerCase() === 'content-encoding') {
        state.encoding = String(headers[i + 1]);
      }
    }
  });
  diagnosticsChannel.subscribe('undici:request:bodyChunkReceived', ({ request, chunk }) => {
    const state = inFlight.get(request);
    if (state) state.bytes += chunk.length;
  });
  diagnosticsChannel.subscribe('undici:request:trailers', ({ request }) => {
    const state = inFlight.get(request);
    if (!state) return;
    const agg = bump(state.key);
    agg.completed += 1;
    agg.wireBytes += state.bytes;
    agg.totalMs += performance.now() - state.startedMs;
    agg.status[state.status ?? 0] = (agg.status[state.status ?? 0] ?? 0) + 1;
    const enc = state.encoding ?? 'identity';
    agg.encodings[enc] = (agg.encodings[enc] ?? 0) + 1;
  });

  const write = (record) => {
    try {
      appendFileSync(METRICS_OUT, `${JSON.stringify(record)}\n`);
    } catch {
      // measurement must never take the server down
    }
  };

  const sample = () => {
    const elu = performance.eventLoopUtilization(lastElu);
    lastElu = performance.eventLoopUtilization();
    const cpu = process.cpuUsage();
    const mem = process.memoryUsage();
    write({
      kind: 'proc',
      at: Date.now(),
      sinceStartMs: Date.now() - startedAt,
      cpuUserUs: cpu.user,
      cpuSystemUs: cpu.system,
      rss: mem.rss,
      heapUsed: mem.heapUsed,
      heapTotal: mem.heapTotal,
      external: mem.external,
      arrayBuffers: mem.arrayBuffers,
      maxRssKb: process.resourceUsage().maxRSS,
      eventLoopUtilisation: elu.utilization,
    });
  };

  const flushUpstream = () => {
    const snapshot = upstream;
    upstream = new Map();
    write({ kind: 'upstream', at: Date.now(), byKey: Object.fromEntries(snapshot) });
  };

  sample();
  setInterval(sample, METRICS_INTERVAL_MS).unref();
  setInterval(flushUpstream, UPSTREAM_FLUSH_MS).unref();
  process.on('exit', () => {
    sample();
    flushUpstream();
  });
}
