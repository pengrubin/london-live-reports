# Tube position inference: rule catalogue (from origin/main, 2026-09-28)

Source of truth for sections 4–6 and Appendix B of document 2. Every row cites file:line on origin/main.

## Entry points

- `frontend/src/realtime/trains-controller.ts:98` `startTrains(map)`: poll + render loop for tube/DLR/Overground/Elizabeth/tram/cable car/river bus. Polls `GET /api/arrivals?lines=<25 manifest ids>` every `POLL_INTERVAL_MS = 10_000` (`:13`), gated by `registerPoll`.
- `frontend/src/realtime/nr-trains.ts:214` `startNrTrains(map)`: National Rail, own loop and layer.
- `backend/src/leaderboard.ts` `LeaderboardTracker.sample()` every 15 s: second consumer of the same pure functions through the same cache/budget (`makeCachedArrivalsFetcher`), credits only trains with a real vehicleId (synthetic identities excluded).
- Backend copies `backend/src/shared/{position-inference,nr-inference,types,geometry}.ts` are hand-maintained; diff vs frontend = non-null assertions plus `parseTime` resolving against Europe/London.

## Pipeline: raw Prediction[] → dot

1. `routes/arrivals.ts`: validate `lines`, TtlCache (8 s), RateBudget, fetch `/Line/{ids}/Arrivals`, key redacted from error bodies; raw TfL array forwarded unchanged.
2. `inferTrains(preds, branchesByLine, prevSegments)` (`position-inference.ts:304`):
   a. Cross-line ghost dedup (`:309-319`): `STOCK_GROUP` (`:96-108`) maps district/circle/hammersmith-city/metropolitan → `sub`, mildmay/windrush/weaver/lioness/suffragette/liberty → `og`; per (group, vehicleId) keep only the listing with the lowest timeToStation.
   b. `vidLocs` / `idlessDirs` (`:321-334`): currentLocation blocks already owned by a vehicleId'd train; id-less blocks with 2+ directions are split by direction.
   c. `dlrLeadingEdges` (`:133-155`) using `buildPrevStops` (`:119`): DLR rows have no vehicleId and no currentLocation and are echoed at every stop ahead; keep only the prediction not echoed by an earlier stop on the same `direction|destinationName|naptanId` chain.
   d. Collapse to one prediction per physical train (`:342-384`): key = `lineId:vehicleId` if vehicleId present (and not `'000'`); else `lineId|currentLocation` (+`|direction` if ambiguous); else DLR leading edge `dlr:dir|dest|naptanId`; else `lineId:tt:dest:naptanId` dropped when timeToStation > RUN_HORIZON_S. Also `byKeyStop` (per-stop freshest prediction) for the handoff.
   e. Per train (`:387-421`): horizon re-check for position-less rows (`:392`); `findCandidates` (`:162`) = branches where naptanId occurs in that direction; `pickCandidate` (`:177`) = previous poll's branch (hysteresis) > terminus matches destination > mid-branch stop over index 0; at-platform successor handoff (`:397-417`); `positionOnBranch` (`:233`).
3. `positionOnBranch` (`:233-298`):
   - Dwelling arm if stopIndex == 0, or timeToStation ≤ AT_PLATFORM_S (15 s), or currentLocation arm == 'at' (for the train's OWN next stop only): place at the stop, segmentFrac = 1.
   - Moving arm: segment = segments[stopIndex-1]; runTime = `segmentRunTime` (`:221-231`): baked `runTimes[i]` if ≥ 20 s → min(300, scheduled + DWELL_BUFFER_S 30); else clamp(polyline length / AVG_SPEED_MS 12, 45..300). If currentLocation matches `DEPARTED = /^(between|left) /i` and tts + 20 > runTime, stretch runTime = tts + 20. frac = 1 − min(1, tts/runTime). If arm == 'approaching', frac = max(frac, 0.85). `pointAtFraction` → lngLat + bearing. Output carries `runTimeS` and `segmentKey = lineId:branchId:direction:stopIndex`.
4. `interpolator.update(trains, receivedAt)` (`interpolator.ts:93-162`): snap if no prior state / no segment / retarget > SNAP_M 1500 m; else countdown EMA `tts = 0.5·new + 0.5·(prev − elapsed)` (TTS_BLEND, `:34`); same segment → targetFrac updated (forward only); segment change → `projectFraction` carry-over, frac = min(carried, target). Absence: synthetic identity → hand over to a just-born synthetic state on same line+direction within SUCCESSION_M 300 m; else drop after RETAIN_MS 60 s (ARRIVED_RETAIN_MS 12 s when next stop == destination and frac ≥ 0.97).
5. `interpolator.frame(dt)` (`:179-210`): ease = 1 − exp(−dt/TAU_MS 4000); dead-reckoned target from extrapolated countdown each frame, target = max(polled, dead-reckoned); frac never decreases; opacity fades over FADE_MS 10 s.
6. `trains-controller.ts:47 toFeatureCollection` → `setData` on the `trains-dots` symbol layer.

## Rule table

| Name | Value | File:line | Does | Recorded reason (verbatim where it exists) | Modes |
|---|---|---|---|---|---|
| RUN_HORIZON_S | 480 s | position-inference.ts:18 | drop position-less predictions further out | "Position-less predictions further out than this are timetable, not live." Overground/Elizabeth predictions are timetable-reaching (~2 h ahead) | Overground, Elizabeth; also gates DLR leading edge (`:141`) |
| AVG_SPEED_MS | 12 m/s | :20 | fallback speed for segment run time | no recorded numeric reason | all rail, fallback only |
| MIN_SEGMENT_RUN_S / MAX_SEGMENT_RUN_S | 45 / 300 s | :21-22 | clamps on run time | no recorded reason | all rail |
| AT_PLATFORM_S | 15 s | :24 | at-platform trigger and handoff trigger | "Below this countdown the train is effectively at the platform." | all rail |
| NO_VEHICLE_ID | '000' | :26 | TfL's placeholder id treated as absent | none | all rail |
| SIDINGS | /sidings?\b/i | :27 | such currentLocation = no usable location | none (stabling, not in service) | all rail |
| DEPARTED | /^(between\|left) /i | :29 | proves the train left its previous stop | "currentLocation prefixes proving the train has left its previous stop." | all rail |
| DEPARTED_MARGIN_S | 20 s | :30 | stretches runTime when countdown exceeds it after departure | "If the countdown still exceeds our scheduled run time, the schedule is the wrong bound — stretch it so the ratio stays past the platform and keeps advancing instead of pinning a moving train at the stop it already left." | all rail |
| APPROACHING_FRAC | 0.85 | :38 | forward-only clamp for "Approaching <own next stop>" | "TfL's timeToStation is often laggy-high (the Metropolitan-line failure: tts freezes ~45-60s stale while the train is already at/near the platform)... never move it BACKWARD". Commit e90122e "fix: Metropolitan lag — trust currentLocation" | all rail |
| normStation | — | :50-60 | tolerant station-name equality | "'At King's Cross St. Pancras Platform 3' matches the baked 'King's Cross St. Pancras'" | all rail |
| currentLocationArm own-next-stop guard | — | :87-94 | at/approaching arms fire only for the train's own next stop | "'At Aldgate Platform' while the next stop is Liverpool Street ... is a terminus/interchange dwell of a different listing; snapping on it caused the false jumps seen in diagnosis." | all rail |
| STOCK_GROUP | sub / og | :97-108 | one vehicleId namespace across lines sharing stock | "one physical sub-surface train is listed on several lines that share S-stock (District/Circle/H&C/Met) → keep only the most-live listing" | sub-surface four; six Overground lines |
| DLR leading edge | — | :132-155 | collapse per-stop echoes | "DLR predictions carry NO vehicleId and NO currentLocation, and each train is listed against every stop ahead → keep only the leading edge." | DLR |
| pickCandidate hysteresis | — | :172-202 | sticky branch, then destination match | "hysteresis — prediction jitter must not teleport it between branches" | branching lines |
| DWELL_BUFFER_S | 30 s | :219 | added to baked scheduled run time | "TfL timetables carry whole-minute granularity and exclude terminal dwell, so the raw scheduled figure systematically undershoots the observed countdown (probe: 60s scheduled vs 74–89s live)." | lines with runTimes |
| scheduled ≥ 20 s | — | :223 | trust baked figure only if ≥ 20 s | none | lines with runTimes |
| at-platform successor handoff | — | :397-417 | position by the successor stop's countdown once at platform | "TfL leaves a stale 'due' at the stop a train just left, which would pin the dot there." | all rail |
| TAU_MS | 4000 ms | interpolator.ts:16 | ease constant | "~63% of the arc gap closed per TAU" | display |
| SNAP_M | 1500 m | :18 | retarget beyond = re-identification, snap | "snap, don't glide" | display |
| RETAIN_MS | 60 s | :25 | coasting retention when absent | "The feed drops vehicles for 1–3 polls routinely (probe: 44 flickers / 281 vehicles in 2 min, gaps up to 30s)... capped at the current segment's end" | display |
| ARRIVED_RETAIN_MS | 12 s | :30 | quick release at own destination | "short workings end mid-line — release it quickly" | display |
| FADE_MS | 10 s | :32 | opacity fade | | display |
| TTS_BLEND | 0.5 | :34 | countdown EMA across polls | "absorbs the feed's ±10s oscillation before positioning" | display |
| SUCCESSION_M | 300 m | :36 | synthetic identity hand-over | "Synthetic identities drift as the train moves ('Between A and B' → 'Between B and C')" | synthetic identities |
| forward-only frac | — | :115-120, 191-194 | never rewinds | "TfL countdown regressions (probe: 94 in 2 min) can therefore never drag a train backwards." | display |
| projectFraction carry-over | — | :121-130 | continuity across segment change | "old segment's end is the new one's start" | display |
| dead-reckoned target | — | :184-190 | per-frame extrapolation, max(target, extrapolated) | "continuous motion between polls" | display |
| HUBS | 17 CRS | nr-trains.ts:22 | boards polled round-robin | "their calling points cover trains across the bbox" | NR |
| BOARD_STAGGER_MS | 4000 ms | nr-trains.ts:24 | one board per 4 s, ~70 s cycle | | NR |
| NR_GATEWAYS | 27 stations | nr-trains.ts ~:95-140; nr-inference.ts:70-104 | remap first out-of-box calling point to outermost in-box station | "Fast trains leave a London terminus and their FIRST calling point lies OUTSIDE the in-box station graph (e.g. Euston→Milton Keynes, Paddington→Reading) ... the train never renders even while physically crossing visible London track." | NR |
| MAX_PATH_M | 60,000 m | nr-inference.ts | Dijkstra give-up | | NR |
| PATH_CACHE_MAX | 300 | nr-trains.ts, nr-inference.ts | FIFO polyline cache | | NR |
| FINISHED_GRACE_MS | 120 s | nr-inference.ts | prune finished journeys | | NR |
| stopTime precedence | actual > estimate > scheduled | nr-inference.ts | best known time per calling point | | NR |
| consecutive-CRS dedupe | — | nr-trains.ts, nr-inference.ts | no zero-length legs | | NR |
| MIN_MOVE_M / MAX_GAP_MS | 5 m / 300 s | leaderboard.ts | jitter floor, track restart | | leaderboard only |
| MAX_SPEED_RAIL_BUS_MS / MAX_SPEED_NR_TRAIN_MS | 40 / 65 m/s | leaderboard.ts | teleport guards | "National Rail runs InterCity stock (~200 km/h)" | leaderboard only |
| synthetic exclusion | — | leaderboard.ts | no distance credit for currentLocation identities | "crediting them would invent distance" | leaderboard only |

## Data contracts

Prediction fields read: `lineId` (req), `vehicleId` ('000' = absent), `naptanId` (req), `timeToStation` (req), `currentLocation`, `platformName`, `direction`, `destinationName`, `destinationNaptanId`, `towards`, `stationName` (read, unused for placement), `lineName`. Everything else is forwarded by the proxy but never read.

Branch file `data/branches/<lineId>.json`: `{ lineId, branches: [{ branchId, direction, stops: [{id, name, lon, lat}], segments: [[lon,lat][]], runTimes?: (number|null)[] }] }`. Segments from TfL Route/Sequence + OSM stitching (`scripts/bake-routes.mjs`); `runTimes[i]` = rounded median of TfL Timetable samples 0 < s ≤ 1800 for the ordered stop pair (`scripts/bake-runtimes.mjs`), null when no sample.

NR graph: `data/nr/stations.json` `{crs,name,lat,lon}` (~431), `data/nr/segments.json` `{a,b,lenM,poly}`. Darwin fields consumed: calling points `{crs,name,st,et?,at?}`, services `{rid,std,etd?,platform?,operator?,origin,destination,cancelled,callingPoints[]}`.

## Known gaps (admitted in code or docs)

- NR path is coarser than tube (docs/ROADMAP.md); no interpolator, positions are pure functions of the clock.
- docs/ARCHITECTURE.md describes a backend train-tracker + WebSocket that was never built; inference is frontend-side, backend only reuses the pure functions for the leaderboard.
- Equirectangular geometry (geometry.ts:2), "accurate to well under a metre at London scale".
- AVG_SPEED_MS, MIN/MAX_SEGMENT_RUN_S carry no measured justification (unlike DWELL_BUFFER_S and RETAIN_MS, which cite probes).
- No ground truth anywhere; validation is unit tests on fixtures plus the probes quoted in comments.
- Backend copies drift risk; in sync as of 2026-09-28.
- NR trains are credited into the leaderboard's 'tube' bucket.
