# Calibration data for "Architecture and stream-processing load"

Measured on **2026-09-29, 22:14 to 22:40 UTC (23:14 to 23:40 BST)** unless a row says otherwise.
Code under test: `origin/main` at commit `6875e27`. Production: london.pengrubin.com, uptime 15.07 days
(one process since 2026-09-14 20:39 UTC).

**Read this first: every live number below was taken late in the evening.** The bus feed held about
3,300 live vehicles; by day it holds 9,000 to 10,000 (section C, by hour). Sizes and rates that scale with
the fleet are therefore given per record as well as in total, and the formulas should be calibrated on the
per-record figures. Re-running the scripts at 08:00 to 18:00 UTC gives the daytime point.

## How to regenerate

All scripts are in `scripts/`; all outputs land in `data/`. Production is only ever read, sequentially,
at under one request per second.

```bash
cd ~/london-live-reports/02-architecture/scripts
python3 measure_endpoints.py --base https://london.pengrubin.com --rounds 5 --label london --out ../data   # A
python3 measure_endpoints.py --base https://london.pengrubin.com --rounds 5 --label london --out ../data \
        --only nr-board --nr-hubs VIC,CLJ --suffix=-nr-board --round-gap 30                                 # A, NR
python3 measure_bus_age.py   --base https://london.pengrubin.com --samples 5 --gap 15 --out ../data/bus-age.json   # G
python3 measure_endpoints.py --base https://dubai.pengrubin.com  --rounds 3 --label dubai  --out ../data   # F
python3 fit_memory.py        --samples ~/bus-archive/health-samples.jsonl --out ../data                    # C
python3 measure_storage.py   --out ../data/storage.csv                                                     # E
./run-local-profile.sh                                                                                     # D, 13 min
PROFILE=0 RUN_NAME=control-run QUIET_S=300 VIEWER_S=0 ./run-local-profile.sh                               # D control
python3 analyze_cpuprofile.py --run ~/london-live-worktrees/measure/tmp/profile-run \
        --persist ~/london-live-worktrees/measure/tmp/persist-profile-run \
        --control ~/london-live-worktrees/measure/tmp/control-run --out ../data/cpu-profile-summary.json   # D
python3 measure_upstreams.py --env ~/london-live-worktrees/measure/backend/.env \
        --manifest ~/london-live-worktrees/measure/data/manifest.json \
        --backend-src ~/london-live-worktrees/measure/backend/src --out ../data/upstream-polls.json        # B
python3 build_streams.py --data ../data                                                                    # B
```

The local run needs the worktree `~/london-live-worktrees/measure` (origin/main, `npm ci` in `backend/`,
`backend/.env` copied in). No script prints or stores a key, a URL with a query string, or an upstream
body; a scan of every file under `02-architecture/` for the five secret values in `.env` found none.

| File | Holds |
|---|---|
| `data/endpoints.csv`, `endpoints-nr-board.csv`, `endpoints-dubai.csv` | A, F: medians per endpoint |
| `data/endpoints-samples-*.csv` | A, F: every sample |
| `data/streams.csv`, `data/upstream-polls.json` | B |
| `data/memory-fit.json`, `data/memory-fit.png` | C |
| `data/cpu-profile-summary.json` | D, including the control run and what the run wrote to disk |
| `data/storage.csv` | E |
| `data/bus-age.json`, `data/bus-age-dubai.json` | G |

---

## A. Endpoint payloads (production)

**Method.** `curl` once with `Accept-Encoding: br` and once with `gzip`, without `--compressed`, so
`%{size_download}` is the wire size; the script decodes the brotli body for the raw size and the record
count. Five rounds between 22:16:39 and 22:22:32 UTC, about 85 s apart, 28 endpoints, medians reported.
The two `nr-board` rows were measured separately at 22:29 to 22:32 UTC.

**Caveats.** (1) These are edge-to-client bytes. Cloudflare may re-encode, so they are not the
origin-to-edge bytes Railway bills; for several bodies brotli is no smaller than gzip (buses, coverage),
which is what a low brotli quality looks like. (2) Response time is from one residential connection in
the UK and includes TLS setup. (3) Raw size comes from the brotli request and gzip from the next request,
about 1 s later, so live bodies can differ by a few records.

Bytes; time in ms; `age` in seconds.

| Endpoint | OK | Raw | gzip wire | br wire | Records | Total ms | x-cache | cf-cache-status | age | cache-control |
|---|---|---|---|---|---|---|---|---|---|---|
| /health | 5 | 991 | 454 | 466 | 37 components | 303 | - | DYNAMIC | - | - |
| /api/capabilities | 5 | 454 | 267 | 265 | 18 layers | 410 | - | DYNAMIC | - | - |
| /api/arrivals (25 lines) | 5 | 4,787,457 | 188,946 | 153,252 | 5,187 predictions | 568 | hit, miss | EXPIRED, HIT | 3 | no-store |
| /api/buses | 5 | 455,671 | 75,414 | 76,765 | 3,324 buses | 371 | - | EXPIRED | - | no-store |
| /api/diversions | 5 | 338,827 | 80,927 | 70,048 | 75 events | 402 | - | DYNAMIC | - | public, max-age=60 |
| /api/coverage | 5 | 7,346,485 | 808,173 | 875,024 | 49,367 features | 415 | - | HIT | 302 | public, max-age=21600 |
| /api/vessels | 5 | 14,109 | 2,909 | 2,955 | 66 vessels | 293 | - | EXPIRED | - | no-store |
| /api/aircraft | 5 | 58,635 | 10,727 | 10,836 | 113 aircraft | 900 | **stale** | STALE | 3,296,833 | no-store |
| /api/bikes (GBFS) | 5 | 2 | n/a | n/a | 0 | 324 | - | DYNAMIC | - | - |
| /api/bike-points (centre) | 5 | 16,483 | 1,088 | 1,028 | 6 places | 608 | miss | DYNAMIC | - | - |
| /api/road-disruptions | 5 | 287,127 | 34,655 | 32,763 | 128 | 528 | hit, miss | EXPIRED | - | no-store |
| /api/disruptions | 5 | 10,311 | 2,238 | 2,228 | 13 items | 707 | miss | DYNAMIC | - | - |
| /api/bus-stop-closures | 5 | 101,629 | 15,689 | 15,925 | 346 stops | 315 | hit, miss | DYNAMIC | - | - |
| /api/jamcams | 5 | 1,145,993 | 63,024 | 55,078 | 890 cameras | 334 | hit, miss | EXPIRED, HIT | 173 | no-store |
| /api/lift-disruptions | 5 | 5,802 | 1,601 | 1,574 | 16 | 305 | hit, miss | DYNAMIC | - | - |
| /api/leaderboard day, bus | 5 | 1,784 | 513 | 505 | top 20 | 297 | - | DYNAMIC | - | - |
| /api/leaderboard day, train | 5 | 2,165 | 451 | 413 | top 20 | 298 | - | DYNAMIC | - | - |
| /api/leaderboard day, ship | 5 | 1,716 | 510 | 485 | top 20 | 291 | - | DYNAMIC | - | - |
| /api/tide-gauges | 5 | 1,411 | 450 | 431 | 10 gauges | 317 | hit, miss | EXPIRED | - | no-store |
| /api/nr-board?crs=WAT | **0** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| /api/nr-board?crs=VIC | 5 | 14,032 | 2,249 | 2,226 | 18 services | 300 | hit, miss | DYNAMIC | - | - |
| /api/nr-board?crs=CLJ | 5 | 14,443 | 2,697 | 2,760 | 20 services | 721 | hit, miss | DYNAMIC | - | - |
| /api/bus-routes-index | 5 | 37,813 | 5,308 | 3,866 | 1,956 keys | 203 | - | EXPIRED, HIT | 173 | no-store |
| /bus-routes/learned/TFLO_88_inbound.json | 5 | 11,687 | 3,383 | 3,239 | 532 points | 125 | - | HIT | 31,900 | public, max-age=14400 |
| /manifest.json | 5 | 2,905 | 642 | 626 | 25 lines | 143 | - | HIT | 241 | public, max-age=3600 |
| /branches/central.json | 5 | 55,303 | 12,561 | 12,363 | 14 branches | 142 | - | HIT, REVALIDATED | 202 | public, max-age=3600 |
| /lines/central.json | 4 | 72,038 | 16,194 | 16,216 | 102 features | 208 | - | HIT, REVALIDATED | 162 | public, max-age=3600 |
| /stations/central.json | 5 | 7,598 | 1,221 | 1,197 | 49 features | 119 | - | HIT, REVALIDATED | 203 | public, max-age=3600 |
| /nr/segments.json | 5 | 494,362 | 124,659 | 124,150 | 579 segments | 196 | - | HIT, REVALIDATED | 202 | public, max-age=3600 |
| /nr/stations.json | 5 | 28,318 | 7,678 | 7,708 | 431 stations | 128 | - | HIT, REVALIDATED | 202 | public, max-age=3600 |

Per-record sizes for the formulas:

| Endpoint | Raw bytes per record | br bytes per record |
|---|---|---|
| /api/buses | 137.1 per bus | 23.1 |
| /api/arrivals | 923.0 per prediction | 29.5 |
| /api/vessels | 213.8 per vessel | 44.8 |
| /api/diversions | 4,518 per event | 934 |
| /api/coverage | 148.8 per feature | 17.7 |
| /api/road-disruptions | 2,243 per disruption | 256 |
| /api/bus-stop-closures | 293.7 per stop | 46.0 |

**Two things found that are not calibration data but affect it:**

1. `/api/aircraft` is not live. Every sample came back `x-cache: stale`, and the timestamp inside the body
   (`now`) is 2026-08-21, 39 days before the measurement. Both ADS-B upstreams answered HTTP 403 to the
   local backend and to a direct request. The 58,635 bytes are the size of the last good response.
2. `/api/nr-board?crs=WAT` answered HTTP 500 on four samples and failed the TLS handshake on the fifth.
   Darwin itself answered 500 for WAT when asked directly; VIC and CLJ are fine.

---

## B. Input streams

**Method.** Size of one poll: `measure_upstreams.py` issues the backend's own request shapes with
`Accept-Encoding: gzip` and records wire and decoded bytes (3 polls 15 s apart for BODS and TfL arrivals,
1 for the rest, 22:33 to 22:35 UTC). Cadence: undici's diagnostics channels inside the local run count
every outbound request and its wire bytes per upstream, separately for the phase with no viewer and the
phase with one. Full table with per-day figures: `data/streams.csv`.

| Stream | Interval | Wire bytes per poll | Decoded bytes per poll | Records per poll | Records/s | Decoded bytes/s | Decoded per day |
|---|---|---|---|---|---|---|---|
| BODS SIRI-VM, London bbox | 15 s (24 requests in 360 s) | 1,113,296 (gzip) | 7,262,015 | 8,273 `VehicleActivity` | 551.5 | 484,134 | 41.8 GB |
| of which newer than 5 min (kept) | 15 s | - | - | 3,221 direct; 3,314 median in the run | 215 to 221 | - | - |
| of which new fixes (written to trace) | 15 s | - | 88,851 as JSONL | 1,026 | 68.4 | 5,923 | 0.51 GB |
| TfL arrivals, 25 lines, no viewer | 15.0 s | 179,097 (gzip) | 4,143,133 | 4,487 predictions, 327 vehicle ids | 299.1 | 276,209 | 23.9 GB |
| TfL arrivals, one viewer at 10 s | 8.8 s (41 in 360 s) | 179,097 | 4,143,133 | 4,487 | 509.9 | 470,811 | 40.7 GB |
| Darwin departure boards | 15.0 s, one of 17 hubs | 86,922 (not compressed) | 86,922 | 19 services | 1.27 | 5,795 | 0.50 GB |
| TfL line status, 7-day window | 120 s | 13,164 | 359,259 | 20 lines | 0.17 | 2,994 | 0.26 GB |
| TfL line status by mode | 120 s | 1,571 | not measured | - | - | - | - |
| TfL road disruptions | 120 s at most (cache TTL) | 35,236 | 288,112 | 129 | 1.07 | 2,401 | 0.21 GB |
| TfL bus stop disruptions | 300 s (viewer poll) | 11,497 | 155,603 | 375 | 1.25 | 519 | 0.04 GB |
| EA tide gauges | 300 s, 11 requests per refresh | 7,960 | not measured | 10 gauges | 0.03 | - | - |
| AIS vessels | WebSocket push | not measured | not measured | 66 vessels in the table | - | - | - |
| ADS-B aircraft | upstream down (403) | - | 58,635 stale | 113 stale | - | - | - |
| GBFS bikes | not configured in London | - | - | 0 | - | - | - |

Per-record sizes: SIRI-VM is **877.8 decoded bytes per `VehicleActivity`** (134.6 on the wire); a TfL
prediction is **923.4 decoded bytes** (39.9 on the wire).

**The bus feed is 7.26 MB per poll, not 7.5 MB**, and the difference from the comment in
`bods-client.ts` is within what the fleet does over a day. It is confirmed at 1.11 MB on the wire by both
the direct polls and the 48 polls the local run made. Note what the size is made of: at 23:33 BST only
3,221 of 8,273 elements (39 %) were newer than five minutes. The feed keeps vehicles that stopped
reporting, so its size falls much less at night than the live fleet does, and parse cost follows the
8,273, not the 3,221.

**Caveats.** Rates for on-demand feeds (road disruptions, bus stop closures, tide gauges, aircraft) are
upper bounds set by a cache TTL or a viewer's poll interval; with nobody watching they are not fetched at
all, apart from the two archive recorders (line status every 2 min, road disruptions every 6 h). Behind
Cloudflare, viewer count does not convert one-to-one into origin requests. The first attempt at the direct
polls sent `urllib`'s default User-Agent and was refused with 403 by TfL and Darwin (8 requests, no data);
the numbers above are from the second attempt with `User-Agent: node`, which is what the backend sends.

---

## C. Memory coefficients from production samples

**Method.** `~/bus-archive/health-samples.jsonl`: 5,363 good samples at 300 s, 2026-09-04 to 2026-09-29,
21 restarts. Ordinary least squares (numpy) of `heapUsedMB` and `rssMB` on the `/health` counters. The
first 30 minutes after each restart are dropped. The fit is reported on the **longest single-process
window**, because the code changed between restarts: 2026-09-14 21:09 UTC to 2026-09-29 22:18 UTC,
**n = 2,484**, with three sampler outages (22 to 25 and 25 to 28 September are the long ones). Figure: `data/memory-fit.png`.

### Heap used

| Model | R² | Residual sd, MB | Intercept, MB | per `vehicleStates` | per `lbVehicleTotals` | per uptime day |
|---|---|---|---|---|---|---|
| M1 vehicleStates | 0.291 | 24.7 | 233.0 | 5.09 KB | - | - |
| M3 lbVehicleTotals | 0.658 | 17.2 | 161.7 | - | 0.349 KB | - |
| **M4 vehicleStates + lbVehicleTotals** | **0.811** | **12.8** | **146.1** | **3.76 KB** (se 0.08) | **0.316 KB** (se 0.004) | - |
| M5 M4 + uptime | 0.814 | 12.7 | 160.0 | 3.85 KB | 0.249 KB | 1.08 MB |
| M6 M5 + events, members, passages | 0.816 | 12.6 | 152.9 | 3.89 KB | 0.254 KB | 0.98 MB |
| M8 all 14 counters | 0.827 | 12.2 | - | - | - | - |

Recommended for the document: **heapUsedMB = 146 + 0.00367 x vehicleStates + 0.000309 x lbVehicleTotals**,
residual sd 13 MB. At the window medians (7,777 and 298,223) this gives 146 + 28.5 + 92.2 = 267 MB against
a measured median of 264 MB. Pooling all seven usable segments (n = 5,276, several builds) gives 3.93 KB
and 0.289 KB with R² 0.47: the coefficients hold across builds, the intercept and the noise do not.

Ranges in the window: `vehicleStates` 56 to 10,288 (median 7,777); `lbLastFixes` 135 to 9,100;
`lbVehicleTotals` 195,381 to 474,533; heap 207 to 477 MB (median 264); RSS 532 to 927 MB (median 859).

By hour (UTC, medians): `vehicleStates` runs from about 1,000 at 01:00 to 03:00 to about 10,100 at 08:00
and 15:00 to 17:00; heap runs from 236 MB to 282 MB over the same cycle.

### Resident set size: no usable fit

| Model | R² | Residual sd, MB |
|---|---|---|
| M1 vehicleStates | 0.009 | 96 |
| M4 vehicleStates + lbVehicleTotals | 0.059 | 94 |
| M5 M4 + uptime | 0.256 | 83 |

RSS does not follow the counters. It sits on plateaus (about 600, 730, 860 and 900 MB) and moves between
them in steps; the residuals have lag-1 autocorrelation 0.98, so 2,484 samples carry the information of
about 20 independent ones. The coefficients in the larger RSS models change sign between models and must
not be quoted. For the document, RSS is a **level, not a function**: median 859 MB, 5th to 95th percentile
603 to 908 MB, that is roughly 3.2 times heap used.

### What the regression can and cannot identify

- **It can** separate a daily-cycle term from a slowly accumulating term, because the two are nearly
  uncorrelated (`vehicleStates` against `lbVehicleTotals`, r = 0.19; variance inflation 1.0 in M4).
- **It cannot** say which structure the daily-cycle 3.76 KB belongs to. `vehicleStates` and `lbLastFixes`
  correlate at r = 0.995, and the vehicle table, the wire array, the trace writer's two maps and the
  in-flight XML all rise and fall with them. The coefficient is the cost of one more live bus across all
  of these together, not the size of a `vehicleStates` entry.
- **It cannot** separate leaderboard growth from uptime. `lbVehicleTotals` and uptime correlate at
  r = 0.95 in this window (variance inflation 10 once both are in), and the per-id caches correlate with
  uptime at 0.93 to 0.97. Adding uptime moves the leaderboard coefficient from 0.316 to 0.249 KB; the
  honest statement is 0.25 to 0.32 KB per entry, with an unresolved 0 to 1.1 MB per day that may be
  fragmentation, the caches, or the leaderboard itself. A window that contains a month rollover (the
  month bucket empties while uptime continues) would separate them; this one does not.
- **It cannot** price the diversion event store: `events`, `eventMembers` and `eventPassages` add 0.002 to
  R², and `events` and `eventPassages` correlate at 0.92.
- Standard errors assume independent samples. Heap residuals in M4 have lag-1 autocorrelation 0.15
  (effective n about 1,850), so they are roughly right for heap and meaningless for RSS.
- `heapUsedMB` is read at an arbitrary point in the garbage-collection cycle; the 13 MB residual is mostly
  that, and no counter will remove it.

---

## D. CPU by stage (local run)

**Method.** `origin/main` in its own worktree, `PORT=3999`, `PERSIST_DIR` a temp dir inside the worktree,
started as `node --cpu-prof --import tsx --import preload-metrics.mjs src/server.ts` (what `npm start`
runs, minus the tsx wrapper process). **The profiler attached; the `process.cpuUsage()` fallback was not
needed**, though the preload records it anyway because the profile covers only the main thread. 60 s
warm-up excluded, then 360 s with pollers only and 360 s with one synthetic viewer polling at the
frontend's intervals with `Accept-Encoding: br`. 22:14:44 to 22:27:44 UTC, Node v24.13.0, Apple M4.
A second run without the profiler (22:33 to 22:39 UTC, 271 s) is the control.

The persist dir was seeded from the archive (1,953 learned routes, 7 rollups, a fresh learner marker) so
that the diversion detector ran and the daily learner did not.

Each sample is attributed to the deepest stack frame that belongs to a stage-owning file; shared helpers
pass their time up to the caller.

Milliseconds of main-thread CPU per 15 s bus poll:

| Stage | Pollers only | With one viewer | Per record (pollers only) |
|---|---|---|---|
| BODS parse + vehicle table (`bods-client.ts`) | 31.6 | 33.2 | 3.8 µs per XML element (8,273) |
| BODS UTF-8 decode of the XML body | 2.6 | 2.9 | 0.36 ms per MB |
| Trace writer | 1.6 | 1.3 | 1.6 µs per new fix (1,026) |
| Diversion detector (projection, events) | 8.4 | 9.9 | 2.5 µs per live bus (3,314) |
| Leaderboard sampling (position inference, NR sampler, persist) | 24.2 | 28.7 | `inferTrains` alone 7.0 |
| JSON.parse of upstream bodies (TfL, Darwin, EA) | 15.9 | 28.6 | 3.8 ms per MB parsed |
| Upstream fetch, undici client | 26.2 | 31.0 | not separable by upstream |
| Node I/O glue: TLS, sockets, streams, zlib bindings | 34.9 | 64.2 | not separable by upstream |
| Serve: routes, serialise, compress (main-thread part) | 0.6 | 33.0 | `serialize` 19.1 |
| Status and disruption shaping | 0.5 | 1.1 | |
| AIS stream | 0.6 | 1.0 | |
| Garbage collection | 36.9 | 40.7 | |
| `(program)`, native code outside JS | 18.9 | 23.0 | |
| Measurement overhead (the preload) | 0.8 | 1.4 | |
| **Main thread busy** | **203.7** | **300.8** | |
| Idle | 14,796 | 14,699 | |

| Whole process | Pollers only | With one viewer | Control, no profiler |
|---|---|---|---|
| Main-thread utilisation | 1.36 % | 2.01 % | not available |
| `process.cpuUsage()`, user + system, per 15 s | 832.9 ms | 1,035.7 ms | **423.7 ms** |
| **Average CPU utilisation of one core** | 5.55 % | 6.90 % | **2.82 %** |
| Process minus main-thread busy, per 15 s | 629 ms | 735 ms | about 220 ms |

**The profiler roughly doubles process CPU** (833 ms against 424 ms per 15 s for the same work). The
stage split above is a split of the main thread and its proportions are sound; the absolute utilisation
to quote is the control's **2.8 % of one M4 core, 424 ms per 15 s**, at 3,300 live buses and no viewer.
One viewer added 97 ms per 15 s on the main thread and 203 ms per 15 s process-wide with the profiler on
(129 successful responses in 360 s: 36 arrivals, 24 buses, 36 vessels and 33 others, served straight from
the origin with no edge cache in front; a further 72 aircraft requests were answered 502).

The backend's own log agrees with the profile: `BODS poll: N vehicles, parse M ms` had a median of 44 ms
(95th percentile 49, maximum 52) over 48 polls, against 31.6 + 1.6 + 8.4 = 41.6 ms attributed to the same
synchronous block.

Memory during the run, from `/health` every 30 s:

| | Profiled run | Control |
|---|---|---|
| RSS peak after warm-up | 606 MB | 758 MB |
| RSS median | 543 MB | - |
| Heap used, peak / median | 218 / 183 MB | 189 / 178 MB |
| External, peak | 103 MB | - |
| OS high-water mark (start-up included) | 795 MB | - |

Counters at the end of the run: `vehicleStates` 4,466, `lbLastFixes` 4,393, `lbVehicleTotals` 12,465,
`routeIndexes` 1,953, `shapeGates` 1,130, `events` 11. Putting these in the production heap formula gives
146 + 16.4 + 3.9 = 166 MB, against a measured median of 183 MB.

**Caveats.**
- Night-time load, as above. Parse cost scales with the 8,273 elements in the feed, detector and trace
  cost with the live fleet, so daytime will raise the last two about threefold and the first much less.
- An Apple M4 is not Railway's shared vCPU, and production pins Node 22 where this ran Node 24. Use the
  proportions and the per-record costs' order of magnitude, not the milliseconds.
- Download cost is not attributable to one upstream. The undici and Node I/O rows serve every feed; by
  wire bytes BODS is 79 % of what came in with no viewer (74.3 of 93.6 KB/s), which is an apportionment,
  not a measurement.
- Brotli and gzip work, file writes and upstream gunzip run on libuv's thread pool and appear only in
  the difference between process CPU and main-thread busy time. That difference also contains V8's
  compiler and GC helper threads, so compression cannot be read off it.
- macOS RSS is not comparable with a Linux container's: it fell from 606 to 230 MB between two samples
  with no change in heap, which is the OS compressing pages.
- `/api/aircraft` returned 502 throughout (upstream 403), so aircraft cost nothing here and is unmeasured.
- The daily jobs are not in the table: the learner was deliberately suppressed, the rollup writer had no
  finished day to roll up, and the coverage writer ran once inside the excluded warm-up.
- Event-loop utilisation was recorded but read 0.95 on a thread the profiler shows 1.4 % busy; it has
  been discarded rather than explained.

---

## E. Storage rates

**Method.** File sizes as `ls -l` reports them, from `~/bus-archive` (**the external volume was not
mounted**, so the trace window is the six days the local copy keeps). Complete days only, last seven
where available. Raw trace size comes from decompressing 2026-09-28 to a pipe and counting bytes and
lines; fix counts for other days come from that day's rollup.

| Dataset | Window | Bytes per day, median (min to max) | Records per day | Bytes per record | Per year |
|---|---|---|---|---|---|
| Bus traces, raw JSONL (as on the server) | 2026-09-28 | 756,699,468 | 8,735,814 fixes | 86.62 | 276 GB |
| Bus traces, gzip (as archived) | 09-23 to 09-28 | 143,776,728 (98.9 M to 146.2 M) | 8,752,345 fixes | 16.43 | 52.5 GB |
| Bus rollups | 09-22 to 09-28 | 302,932 (214 K to 304 K) | 2,142 route-directions | 141.5 | 111 MB |
| Diversion log | 09-22 to 09-28 | 1,308,330 (946 K to 1,335 K) | 5,411 transitions | 241.8 | 478 MB |
| Tube status | 09-22 to 09-28 | 4,725,349 (1.75 M to 6.12 M) | 131 snapshots | 35,635 | 1.72 GB |
| Road disruptions | 09-22 to 09-28 | 163,267 (152 K to 171 K) | 4 snapshots | 40,817 | 60 MB |
| Leaderboard day archive | 09-22 to 09-28 | 2,300,319 (1.62 M to 2.34 M) | 22,930 vehicle totals | 100.3 | 840 MB |
| Learned route snapshot, tar.gz | 09-21 to 09-28 | 8,293,205 | about 1,950 route files | - | 3.0 GB |

Gzip ratio on traces is 5.27. On 2026-09-28 the file held 8,735,814 lines and the rollup reports the same
number of fixes, from 8,860 vehicles on 152,634 journeys: **986 fixes per vehicle per day, 101 fixes per
second averaged over the day**. The local run wrote 86.6 bytes per fix and 68.4 fixes per second at night,
which agrees with both.

**Caveats.** At 757 MB a day raw, the writer's 2 GB cap holds 2.8 days, so the 7-day retention constant
in `trace-writer.ts` is never the binding limit. Sunday 09-27 is 31 % below the weekday median. The
tube-status figure varies threefold day to day because a snapshot is written on change, not on a timer.
`arrivals/` in the archive is the local sampler's own recording, not server state, and its only complete
file (124 MB gzip for 2026-09-28) covers a partial day; it is in `storage.csv` but not in this table.

---

## F. Second calibration point: Dubai

**Method.** Same script, three rounds, 22:24 to 22:27 UTC (02:24 local). `/health` read once at 22:28.

| | Dubai | London, same evening |
|---|---|---|
| Uptime | 15.08 days | 15.07 days |
| RSS | **117 MB** | 756 MB |
| Heap used | **30 MB** | 304 MB |
| Heap total | 36 MB | 371 MB |
| External | 8 MB | 73 MB |
| Buses | 0 (no feed) | 3,324 |
| Vessels | 0 | 66 |
| Trains | not inferred (`trainPositions: false`) | 327 vehicle ids |
| Bike stations (GBFS) | 213 | 0 |
| Leaderboard entries | 0 | 474,384 |
| Manifest lines | 4 | 25 |

| Dubai endpoint | Raw | gzip | br | Records | Total ms |
|---|---|---|---|---|---|
| /health | 856 | 353 | 349 | 31 components | 280 |
| /api/capabilities | 539 | 326 | 319 | 18 layers | 347 |
| /api/bikes | 19,290 | 5,397 | 5,707 | 213 stations | 324 |
| /api/buses, /api/vessels, /api/tide-gauges, /api/bus-routes-index | 2 | - | - | 0 | 263 to 291 |
| /api/diversions | 38 | - | - | 0 events | 321 |
| /api/leaderboard (each mode) | 75 to 77 | 88 to 90 | 68 to 73 | 0 | 298 to 300 |
| /manifest.json | 811 | 342 | 321 | 4 lines | 299 |
| /lines/red.json | 9,438 | 2,828 | 2,737 | 2 features | 282 |
| /stations/red.json | 5,317 | 941 | 915 | 34 features | 298 |
| /api/coverage, /branches/red.json | 404 | | | | |
| /api/aircraft | 502 | | | | |

**What this point is.** Dubai carries no vehicle stream at all, so it is the **zero-load intercept**, not
a second point on the slope: the same build, idle, costs 30 MB of heap and 117 MB of RSS. The London heap
formula's intercept is 146 MB; the 116 MB between the two is London's fixed structures (1,953 route
indexes, the baked rail graph, the gazetteer, cached arrivals bodies), which this comparison bounds but
does not itemise.

**Caveats.** Every Dubai response is `cf-cache-status: DYNAMIC`, and its static files carry
`max-age=0` where London's carry `max-age=3600`: nothing in Dubai is edge-cached. Response times around
290 ms are one connection from the UK and say nothing about users in the Gulf.

---

## G. End-to-end latency for buses

**Method.** Five `GET /api/buses` 15 s apart, 22:23:34 to 22:24:34 UTC. For every bus, age = local clock
at first byte minus `t` (RecordedAtTime, ms). The local clock ran 0.5 s ahead of the response `Date`
header, which has 1 s resolution. 16,341 bus-samples in total.

| Statistic | Age, seconds |
|---|---|
| Minimum | 15.5 |
| 5th percentile | 20.5 |
| 25th percentile | 31.5 |
| **Median** | **46.5** |
| 75th percentile | 65.5 |
| 90th percentile | 102.5 |
| 95th percentile | 181.5 |
| 99th percentile | 283.1 |
| Maximum | 310.5 |
| Mean | 60.1 |

| Sample (UTC) | Buses | Median age | Under 30 s | Under 60 s | Over 120 s |
|---|---|---|---|---|---|
| 22:23:34 | 3,278 | 42.5 | 28.5 % | 72.6 % | 8.5 % |
| 22:23:49 | 3,267 | 46.5 | 21.1 % | 67.9 % | 8.7 % |
| 22:24:04 | 3,271 | 42.5 | 28.7 % | 73.0 % | 8.4 % |
| 22:24:19 | 3,265 | 47.5 | 19.8 % | 67.5 % | 8.5 % |
| 22:24:34 | 3,260 | 51.5 | 10.3 % | 62.0 % | 8.6 % |

**Reading it.** Nothing is ever younger than 15 s: that floor is upstream of this system (vehicle to
operator to BODS). The body of the distribution, 20 to 80 s, is a vehicle's own reporting interval (a new
fix about every 48 s, from 0.31 new fixes per vehicle per poll) plus the 15 s poll. The tail from 80 to
310 s, a steady 8.5 % of vehicles, is buses that have stopped reporting and are kept until the parser's
five-minute cutoff. The median drifts from 42.5 to 51.5 s across consecutive samples because the samples
land at different points in the 15 s poll cycle.

**Caveats.** This is age at the server's response, as asked: it excludes the browser's own 15 s poll and
the render. All five responses were `cf-cache-status: EXPIRED` with no `age` header, so the edge cache
added nothing here; when it does serve a hit it can add up to its TTL. Night-time fleet. Dubai returns no
buses, so there is no second point.

---

## Per-stage summary

Night-time values, 2026-09-29 22:14 to 22:40 UTC. CPU is main-thread milliseconds per 15 s on an Apple M4
with the profiler attached, no viewer unless stated.

| Stage | Input rate | Output rate | CPU | Memory | Storage | Source of each number |
|---|---|---|---|---|---|---|
| 1. BODS download | 1 request per 15 s; 1.11 MB gzip, 74.2 KB/s on the wire | 7.26 MB XML per poll, 484 KB/s, 41.8 GB/day decoded | shared rows: undici 26.2 + Node I/O 34.9 across all upstreams; BODS is 79 % of inbound bytes (apportioned) | one 7.3 MB body in flight; external peak 103 MB | none | B direct polls; D undici counters; D profile |
| 2. BODS decode + parse | 8,273 `VehicleActivity` per poll, 551 per s | 3,314 live buses per poll (3,221 by direct count); 39 % of elements kept | 2.6 decode + 31.6 parse = 34.2; 3.8 µs per element | part of 3.76 KB per live bus (heap, all per-bus structures together) | none | B; D profile; D server log; C model M4 |
| 3. Trace writer | 3,314 buses per poll | 1,026 new fixes per poll, 68.4 per s (day average 101 per s) | 1.6; 1.6 µs per fix | two per-vehicle maps, inside the 3.76 KB | 86.6 B per fix raw, 757 MB/day; 16.4 B gzip, 144 MB/day | D run output; E archive |
| 4. Diversion detector | 3,314 buses per poll against 1,953 route indexes | 5,411 transition lines per day; 75 events served | 8.4; 2.5 µs per bus | not separable: events add 0.002 to R² | 241.8 B per line, 1.31 MB/day | D profile; E; A; C |
| 5. TfL arrivals fetch + parse | 1 request per 15 s (8.8 s with a viewer); 179 KB gzip | 4.14 MB JSON, 4,487 predictions, 327 vehicle ids | JSON.parse 15.9 (28.6 with a viewer); 3.8 ms per MB | up to 4 cached bodies of 4 to 5 MB | none on the server | B direct polls; D undici counters; D profile |
| 6. Leaderboard sampling | 3,314 buses + 327 trains + 66 vessels + 1 Darwin board (87 KB) per 15 s | top-20 responses; 22,930 vehicle totals per day | 24.2 (`inferTrains` 7.0) | 0.25 to 0.32 KB per `lbVehicleTotals` entry; 92 MB at the median 298 K | 100.3 B per vehicle, 2.30 MB/day; live file rewritten each minute (1.16 MB after a 13 min run) | D profile; C models M4, M5; E; D run output |
| 7. Status and disruption recorders | line status every 120 s (13 KB gzip, 359 KB decoded); road disruptions every 6 h | 131 status snapshots and 4 road snapshots per day | 0.5 | not separable | 4.73 MB/day status; 0.16 MB/day road | B; D undici counters; E |
| 8. Serve: serialise + compress | one viewer: 129 responses in 360 s | arrivals 4.79 MB raw to 153 KB br; buses 456 KB to 77 KB; 23 br bytes per bus, 30 per prediction | 33.0 main thread for one viewer; +203 process-wide | response buffers, transient | none | D viewer phase; A |
| 9. Garbage collection | - | - | 36.9 (18 % of main-thread busy) | heap residual sd 13 MB | - | D profile; C |
| 10. Whole process | 93.6 KB/s inbound on the wire, no viewer | - | main thread 203.7 (1.36 %); process **424 ms per 15 s, 2.8 % of a core, without the profiler** | production: heap = 146 + 0.00367 x buses + 0.000309 x leaderboard entries MB (median 264); RSS median 859 MB. Idle build (Dubai): heap 30, RSS 117 MB | 0.77 GB/day raw on the server, 99 % of it traces | D control run; C; F; E |
| 11. Source to response | vehicle fix | served position | - | - | - | G: median age 46.5 s, 5th to 95th percentile 20.5 to 181.5 s |

## Not measured, and why

| What | Why |
|---|---|
| Daytime load (9,000 to 10,000 live buses) | The measurement ran at 23:15 to 23:40 BST. Only section C covers the daily cycle. |
| CPU on production hardware and Node 22 | Local run on an Apple M4 with Node 24.13; Node 22 is not installed on this machine. |
| AIS inbound message rate and bytes | WebSocket frames are invisible to the log and to undici's request counters. Only the table size (66 vessels) is known. |
| Aircraft upstream size, rate and CPU | Both ADS-B networks answer 403; production has been serving a body from 2026-08-21. |
| Darwin board for Waterloo | Upstream answers 500 for WAT. VIC and CLJ measured instead. |
| Compression cost on its own | It runs on the thread pool; only the process-minus-main-thread difference is available, and that includes V8 helper threads. |
| Download cost per upstream | undici and Node I/O time is shared by all feeds; only a byte-share apportionment is given. |
| Daily batch jobs (learner, rollups, coverage) | Learner suppressed on purpose (it would call TfL about 700 times); no finished day to roll up; coverage ran inside the excluded warm-up. |
| Origin-to-Cloudflare bytes | Public requests see the edge-to-client leg only. |
| RSS as a function of load | It does not behave as one (R² 0.06); reported as a level. |
| Memory of the diversion event store and of each cache | Collinear with other counters or too small to detect; see section C. |
| Decoded size of line-status-by-mode and the EA tide responses | Wire bytes only, from the undici counters. |
| Trace history beyond six days, and the external archive | `/Volumes/大龟壳` was not mounted; the local copy keeps six days of traces. |
| A second point on the load slope | Dubai has no vehicle feeds, so it fixes the intercept only. |
