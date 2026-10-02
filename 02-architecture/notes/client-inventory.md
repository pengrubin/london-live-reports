# Client stage inventory (agent output, origin/main, 2026-09-29)

Paths relative to frontend/src/. Feeds sections 2, 4.5 and 5 of the document.

## Cross-cutting
- `util/lifecycle.ts`: `registerPoll(fn, ms)` runs timers only while the page is visible; on return every poller fires once immediately (a burst of one request per poller). Reason in header: "a hidden page renders nothing, so every byte it polls is wasted, and the origin is billed per byte for it."
- Power saver: default ON on touch devices, OFF on desktop; only stretches the symbol render gate 66 ms → 300 ms. It does not change poll rates.
- `util/render-gate.ts`: 66 ms (~15 Hz) gate on GeoJSON rebuilds; reason: rebuilding a source every animation frame "churns hundreds of MB/min of feature garbage across five layers". Users: trains, NR, aircraft, bus icons. Not gated: vessels (500 ms loop), bus dots (1 Hz timer).
- `/api/capabilities` gates which layers start; failure falls back to the full London set.

## Request profile of one visible tab (req/min = 60 / T)
| Endpoint | T | req/min |
|---|---|---|
| /api/nr-board (17 hubs round-robin) | 4 s | 15 |
| /api/aircraft | 5 s | 12 |
| /api/arrivals (all lines, one request) | 10 s | 6 |
| /api/vessels | 10 s | 6 |
| /api/buses | 15 s | 4 |
| /api/leaderboard | 30 s | 2 |
| /api/bikes | 60 s | 1 |
| /api/disruptions | 90 s | 0.67 |
| /api/road-disruptions | 120 s | 0.5 |
| /api/tide-gauges | 300 s | 0.2 |
| Default total | | ≈ 47.4 |
| + diversions (90 s) + bus-stop-closures (300 s) when on | | ≈ 48.2 |

Startup one-shots: capabilities, manifest (fetched 3×), lines/stations/branches × L lines (branches ≈ 1.0 MB total), nr stations + segments, jamcams, bus-routes-index (~1,430 stems), pmtiles range requests, glyphs/sprites from protomaps.github.io. Coverage GeoJSON once on first toggle.

On-demand: learned bus routes `/bus-routes/learned/<key>.json` (up to ~200 KB each), client cache cap 600 FIFO, negative-caches 404s. At zoom < 12.5 every tracked bus is advanced at 1 Hz, so the whole fleet's routes are requested: a variable request source outside the periodic table.

Event-driven: train click 3 requests (vehicle-arrivals, line-status, leaderboard-rank); station click 5 (stop-arrivals, stop-detail, crowding, lift-disruptions, bike-points); bus/ship/NR click 1–2; aircraft click 2; JamCam media direct from TfL CDN.

Polling that ignores layer visibility (continues when the layer is hidden in the legend): trains, NR, aircraft, vessels, bikes, roadworks, tide. Polling that stops when hidden: buses, disruptions, diversions, closures. Not in the lifecycle registry (keeps ticking in a hidden tab): leaderboard 30 s, JamCam popup 60 s.

Code-reading observation (unverified at runtime): if the first NR board returns 503 (no Darwin token) the NR poll never resumes for the page's life.

## Client computation (parameters: N_T trains, P prediction rows, V_s vertices per segment, N_B buses, N_Bv buses in viewport+20%, V_r route vertices, N_A aircraft, N_S ships, N_NR NR trains, S_c calling points)
| Computation | Per poll | Per rendered frame | Caps | State per vehicle |
|---|---|---|---|---|
| Train inference | O(P + N_T·(branches·stops + V_s)) | none | — | none (uses previous segment map) |
| Train interpolator | O(N_T), projection only on segment change | O(N_T · V_s) | 15 Hz gate; no viewport culling; retention 60 s | ~10 fields + reference to shared segment |
| National Rail | O(services × calling points) per 4 s board | O(N_NR · (S_c + V_path)); Dijkstra O(n²) on 431 nodes on path-cache miss | path cache 300 FIFO; 60 km cutoff | calling pattern per rid |
| Bus raw model | O(N_B) | O(1) per advanced bus | advanced: N_B at zoom < 12.5 (1 Hz), N_Bv at zoom ≥ 12.5 (15 Hz) | ~30 scalars; TTL 5 min |
| Bus snap + Kalman | per new fix: windowed projection O(60) (full O(V_r) at most every 3 s) + O(1) filter step; ~110 updates/s fleet-wide | one exp + amortised O(1) arc walk | route cache 600; 3 Float64Array per route (24 B/vertex) shared across buses | 5 floats + 4 display fields |
| Aircraft | O(N_A) | O(N_A) dead reckoning + classifier | 15 Hz gate | position + velocity |
| Ships | O(N_S) | ~2 Hz, O(N_S · N_boats) dedupe against TfL boats | fade 30 s → 15 min | last fix |
| Diversions, closures, disruptions | rebuild features per poll (90–300 s) | none | — | payload only |
| Bus Flow | one parse + one setData | none | — | — |
| Leaderboard | none (server-ranked) | none | — | — |

## Why server computation does not grow with viewers
Inputs are viewer-independent (no viewport parameter on /api/buses or /api/arrivals), so every tab gets the same cached response and does its own inference, smoothing, filtering and geometry in the browser. The one server-side copy of the inference is the leaderboard (distance accumulation must be persistent and viewer-independent); it samples every 15 s through the same cache and budget as the public route, so it does not double-spend upstream quota.

## Render pipeline at fleet scale
Two tiers for buses: below zoom 12.5 a circle layer with all buses, 2 properties each, rebuilt at 1 Hz; at or above 12.5 a symbol layer of oriented icons for the viewport subset, rebuilt per gated frame. Filter colouring is a style expression, not a data rewrite. Hot paths are allocation-free (comments in buses.ts, bus-kalman.ts). No measured frame times exist in the source.

## Payload fields actually read
/api/buses: all 9 short-key fields. /api/arrivals: 11 of TfL's ~21 fields (lineId, lineName, vehicleId, naptanId, timeToStation, currentLocation, platformName, direction, destinationName, destinationNaptanId, towards); the rest of the 8.5 MB raw body is unused. /api/coverage: paint reads `b` only. Others: see agent transcript.

## Items to flag in the document
1. Per-tab origin load = Σ 60/T_i ≈ 47 requests/min, independent of what the viewer looks at.
2. Four places where "hidden tab pauses everything" is not strictly true.
3. Learned-route fetch fan-out at low zoom.
4. /api/arrivals carries ~2× more fields than the client reads: a payload-trimming lever.
