# Backend pipeline inventory (agent output, origin/main, 2026-09-29)

Feeds sections 2, 3, 4 and the appendix. Parameters: N_veh buses in the BODS response; B_siri SIRI XML size (∝ N_veh); N_route route-direction keys; N_pred TfL Arrivals rows; N_ev live diversion events; N_viewers concurrent browsers; F_day trace fixes per day; N_vessel AIS vessels; N_nr tracked National Rail trains.

## Stage map
| Stage | Components | Trigger |
|---|---|---|
| (a) Ingestion and parsing | BodsClient (SIRI-VM XML, string scan, every field copied), AisClient (WebSocket push), GbfsClient, SnapshotRecorder ×2 (line status, road disruptions), leaderboard samplers (TfL arrivals, Darwin boards), 14 proxy routes + 3 hand-rolled routes | timers / push for the first five; viewer request on cache miss for the routes |
| (b) In-memory state and caches | vehicle table + wire array, vessel map, bike stations, NR train timelines + path cache, leaderboard buckets, detector states / gates / route indexes / event store, trace buffer, TtlCache per route (bounded by entries, not bytes), per-route single-flight and back-off maps, baked data loaded at boot | — |
| (c) Online detection / derivation | DiversionDetector (synchronous inside the BODS poll), LeaderboardTracker (position inference + distance), NrSampler (clock-driven positions over Dijkstra paths), disruption resolver and closure shaper (inside proxy shape hooks, once per cache miss) | per poll / per tick / per miss |
| (d) Persistence | bus-traces (JSONL append, daily), bus-rollups (JSON per day), learned and prior routes (child scripts), coverage/latest.json, diversions transitions (JSONL), tube-status and road-disruptions snapshots (JSONL), leaderboard.json + daily archive, bus-stop gazetteer | flush timers, atomic tmp+rename for JSON |
| (e) Serving and egress | Fastify + compress (br q4, gzip) + CORS; direct-table routes (/api/buses, /api/vessels, /api/bikes); proxy routes; derived routes (leaderboard, diversions, coverage, learned routes, capabilities); /health; static files in production; no inbound rate limiting | viewer requests |
| (f) Batch jobs | learn-bus-routes and fetch-bus-prior as child processes (LearnerScheduler); in-process: rollup catch-up (hourly check), coverage build (24 h), detector index rebuild (24 h), trace maintenance (hourly) | self-scheduled from freshness stamps |

## Input streams
Timer-driven (independent of viewers):
| Stream | Protocol | Cadence | Timeout | Budget | On failure |
|---|---|---|---|---|---|
| BODS SIRI-VM | HTTP GET, bounding box | 15 s, re-entrancy guarded | 30 s | none | last good table served; records older than 5 min dropped at parse |
| AIS | WebSocket push (PositionReport, ShipStaticData) | push; reconnect 15 s | — | none | vessel TTL 10 min, prune 60 s; no idle watchdog |
| GBFS | HTTP GET | status 60 s, catalogue 6 h | 15 s | none | previous snapshot kept |
| TfL line status (recorder) | HTTP GET, window form, detail=true | 2 min, 1–2 calls per poll | 8 s | bypasses the TfL budget | falls back to Mode form |
| TfL road disruptions (recorder) | HTTP GET | 6 h | 8 s | bypasses budget | logged, next tick |
| TfL Arrivals (leaderboard sampler) | HTTP GET via the shared arrivals cache | 15 s tick | 8 s | TfL 60/min | stale any age |
| Darwin board (NR sampler) | HTTP GET via the shared board cache | one hub per 15 s tick over 17 hubs | 8 s | Darwin 40/min | stale any age |
| BODS dataset API (priors) | HTTP, child process | weekly | 120 s | none | skipped and counted |

Viewer-triggered (one fetch per cache miss, shared by all viewers):
| Stream | Cache TTL | Budget | Notes |
|---|---|---|---|
| TfL Arrivals, all lines | 8 s, 4 entries max | TfL | hand-rolled: no single-flight, no back-off |
| TfL stop arrivals / vehicle arrivals | 8 s | TfL | popup-driven, viewer-chosen keys |
| TfL line status / crowding / bike points | 60 s | TfL | popup-driven |
| TfL stop detail | 600 s | TfL | popup-driven |
| TfL lift disruptions | 300 s | TfL | single key |
| TfL disruptions (window form) | 60 s, stale ≤ 10 min | TfL | shaped inside the proxy, raw body never cached |
| TfL bus-stop closures + StopPoint batches ≤ 20 | 600 s, stale ≤ TTL + 10 min | TfL, one unit per batch | gazetteer grows permanently |
| TfL JamCam list | 600 s | TfL | media from TfL CDN directly |
| TfL road disruptions | 120 s | TfL | |
| Darwin board | 45 s | Darwin | same cache as the sampler |
| ADS-B (airplanes.live, fallback adsb.lol) | 4 s | ADS-B 60/min | one unit can cost 2 upstream calls |
| adsbdb callsign | 1 h | adsbdb 30/min | |
| EA tide gauges | 300 s | EA 10/min | one unit = 2 + N_gauges upstream calls |
| Ship photo / aircraft photo | 24 h | private 10 / 20 per min | image bytes cached |

Generic proxy behaviour: fresh hit → serve; miss → join in-flight fetch if any, else consume one budget unit and fetch; budget exhausted or fetch throws → serve stale (any age unless bounded) else 429 / 502; a throw arms a 30 s per-key back-off; a non-200 is passed through with the key redacted, not cached, and does not arm back-off.

## Component cards (scales-with line for each)
| Component | Work per input | State bound | Scales with |
|---|---|---|---|
| BodsClient | download + scan O(B_siri); table build O(N_veh) | table replaced wholesale each poll | B_siri ∝ N_veh, one poll per 15 s |
| TraceWriter | O(N_veh) per poll, only fixes whose time advanced; flush every 5 s | buffer cap 500,000 lines; 7 days, 2 GB on disk; per-vehicle maps pruned only above 20,000 ids | new fixes per day F_day |
| DiversionDetector | per routed bus: grid projection ~O(1) + state update; event scan O(N_ev) per fix; lifecycle tick 60 s; index rebuild 24 h over N_route files | per vehicle ≤ 32 recent s values, ≤ 2,000 excursion fixes, ≤ 4 pending, TTL 30 min; per route index ∝ vertices (≤ 2,500 at 25 m) + 256-sample gate; per event ≤ 500 members, ≤ 12 segments | N_veh_routed × (1 + N_ev) per poll; memory with N_route and vehicles active in 30 min |
| Learner (child process) | two passes over 3 days of traces; per key seed, fit, snap, gate, repair | chunk budget 4,000,000 fixes (~100 MB) | F_day × 3 + N_route; separate process |
| RollupWriter | one streaming pass per completed day, O(F_day) | transient per-day maps | F_day once a day |
| Coverage writer | resample all learned routes to 25 m pieces, 3×3 cell queries of 30 m cells; yields every 50 routes | 88 B per piece, transient | total learned route length, once a day; largest memory peak of the process |
| SnapshotRecorder | compact + compare with last write; append if changed or heartbeat | one payload per feed | fixed cadence |
| LeaderboardTracker | per 15 s: O(N_veh + N_vessel) haversine + inference O(N_pred × candidate branches) + O(N_nr); persist every 60 s is a synchronous stringify + write of all open buckets | three open buckets (day, week, month), one total per distinct vehicle per period; last-fix map TTL 15 min | feed sizes per tick; memory with distinct vehicles per open period; viewer-facing sort on /api/leaderboard |
| NrSampler | merge one board per tick; position per train; Dijkstra O(V²) on cache miss | train timelines pruned 120 s after last stop; path cache 300 | N_nr, ≤ 4 Darwin calls/min |
| AisClient | JSON.parse per frame, merge | vessel TTL 10 min | message rate in the box |
| GbfsClient | O(stations) per minute | stations in region | stations |
| Proxy routes | hit: serialise + compress O(payload); miss: fetch + shape | TtlCache default 300 entries | per-request CPU with N_viewers; upstream calls with distinct keys / TTL, capped by budget |

## What does and does not scale with viewers
Does NOT: every timer-driven ingest, detection, persistence and batch job; upstream calls for fixed-key routes (one cache entry serves all viewers); upstream budgets are hard ceilings; single-flight on generic proxy routes; the leaderboard sampler piggybacks on the public arrivals cache.
DOES: egress bytes (payload × requests; the origin sets no Cache-Control on /api/buses or /api/arrivals, explicit cache headers only on diversions 60 s, coverage 6 h, learned routes 1 h, ship photos 24 h); per-request JSON serialisation of cached objects; per-request compression (no response-level cache); per-request logging; per-request O(N) work on /api/vessels (copy), /api/leaderboard (sort), /api/diversions (payload rebuild), learned route files (disk read); popup-driven proxy calls with viewer-chosen keys; concurrent-miss bursts on /api/arrivals (no single-flight).

## /health instrumentation
memory {rssMB, heapUsedMB, heapTotalMB, externalMB}; components: vehicleStates, routeIndexes, shapeGates, events, eventMembers, eventPassages, lbBuckets, lbVehicleTotals, lbLastFixes, cache sizes (arrivals, stopArrivals, vehicleArrivals, stopDetail, crowding, liftDisruptions, bikePoints, disruptions, busStopClosures), disruption and closure resolve counters with last parse ms, cache eviction counters, upstreamAssertionsSurvived, httpParserFixed.
NOT exposed (only in logs or files): bus count and parse ms per poll, trace buffer sizes, vessel / bike / NR train counts, several cache sizes, batch outcomes, event-loop lag, CPU.

## Process model
One Node process runs everything except the two learner scripts (child processes, 45 min timeout, not signalled on shutdown). All timers are unref'd. Timers: BODS 15 s; trace flush 5 s; leaderboard sample 15 s, persist 60 s; GBFS 60 s; AIS prune 60 s; line-status recorder 2 min; road recorder 6 h; detector lifecycle 60 s, index rebuild 24 h; rollup check 1 h; coverage 24 h; learner 24 h. Shutdown runs onClose hooks then exits.

## Design principles (quoted in code)
1. Secrets never leave the server (error bodies redacted; non-200 on shaped routes becomes a throw; tracker logs host and path only).
2. Optional features are key-gated, never absent (routes exist and return [] or 503).
3. Never throw from a poll loop or runtime writer ("Losing a batch is fine; blocking or ballooning memory is not").
4. Per-upstream budgets so one feed cannot starve another.
5. Piggyback rather than double-spend (samplers share the public caches).
6. Bound memory in entries and, where bodies are large, by a small entry cap.
7. Serve stale rather than nothing, but bound staleness where meaning decays.
8. Fail closed on geometry.
9. Pure CPU work must not stall the loop (yield during long builds).

## Findings that are defects or doc drift (not for the document body; candidates for fixes)
- Comments say coverage rebuilds every 6 h; the constant is 24 h. sync-archive says traces kept ~3 days; retention is 7.
- TraceWriter per-vehicle maps are never pruned below 20,000 ids.
- TraceWriter.stop() does not await its final flush: up to 5 s of fixes lost on shutdown.
- /api/arrivals and the two sampler fetchers lack single-flight; concurrent misses each spend a budget unit.
- Non-200 upstream responses on generic routes are neither cached nor backed off.
- AIS has no idle watchdog (already in deferred fixes).
- /api/leaderboard-status reads and parses the whole leaderboard file on every unauthenticated request.
- Request logging is on for every request (the Railway log-rate-limit drops seen on 2026-09-25).
- Status recorder calls bypass the TfL budget.
