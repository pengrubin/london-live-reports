# Baked geometry (from origin/main@6875e27, 2026-09-28)

Source for section 3 of document 2. All numbers computed from the committed data/ files (equirectangular, same constants as the bake scripts).

## Serving
Static data is baked offline by four scripts and committed; the backend never calls TfL/Overpass for it at runtime (`backend/src/config.ts:103-104`). Prod serves `frontend/dist` then `data/` via fastifyStatic (`backend/src/app.ts:471-477`), hence relative URLs `/branches/…`, `/nr/…`.

## 1. Scripts

### bake-routes.mjs (TfL route geometry, stops, segments)
- Inputs: `GET /Line/{id}/Route/Sequence/{outbound|inbound}?excludeCrowding=true` per line×direction (`:57-62`); LINES now 25 (header says 19, stale). River lines (not Woolwich Ferry): Overpass `way["waterway"="river"]["name"="River Thames"]` cached at data/osm-cache/thames.json.
- Algorithm: dedupe lineStrings → polylines; stopPointSequences → branches {branchId, direction, stops[{id,name,lon,lat}]} (" Underground/Rail/DLR Station" stripped); per consecutive stop pair `trackSegment`: project both stops onto each polyline, accept if both within MAX_SNAP_M 250 m (RIVER_SNAP_M 600 m) and path ≤ 4× straight line (8× river), cut sub-polyline; else 2-point straight chord (`:319`). River: DOCK_TRIM_M 140 m + 10-step quadratic Bézier pier approaches. Coordinates 5 dp.
- Outputs: data/lines/<id>.json (GeoJSON LineStrings), data/stations/<id>.json (Points), data/branches/<id>.json `{lineId, branches:[{branchId,direction,stops,segments}]}` with segments[i] = stops[i]→stops[i+1], data/manifest.json (generatedAt 2026-07-23T23:47:47Z).

### bake-osm-geometry.mjs (OSM overlay, 19 lines)
- Overpass `rel["route"=…]["name"~…]` → ways railway ∈ {rail, subway, light_rail, narrow_gauge}; selectors: subway for 11 tube lines, light_rail for DLR, train + name regex for Elizabeth and 6 Overground lines. River skipped ("TfL geometry already follows the Thames"); tram and cable car not in the list (no reason given).
- Stitch ways into chains breaking at junctions; try trackSegment at 250 m then MAX_SNAP_RELAXED_M 400 m ("some tube stop coords are street-level entrances"); else Dijkstra over the node graph with SNAP_PENALTY 3; else keep the TfL segment unchanged. Stops never changed. Per-line osm/graph/keptTfL report printed to console only, not persisted.

### bake-runtimes.mjs (scheduled run times)
- `GET /Line/{id}/Timetable/{fromStopId}?direction=` once per (direction, first stop); walk stationIntervals → per-pair second deltas; keep 0 < s ≤ 1800; median per ordered pair, rounded; null when no sample; written as branch.runTimes[i] aligned with segments[i].

### bake-nr-graph.mjs (National Rail graph)
- Inputs: davwheat/uk-railway-stations stations.json (≥2000 rows sanity check); Overpass `way["railway"="rail"]["service"!~"."]` over 4 quadrants of bbox 51.25,-0.55,51.72,0.35.
- Snap each station to nearest rail node within SNAP_MAX_M 500 m (unsnappable stations dropped, logged only); nodes within ZONE_M 300 m belong to that station; one Dijkstra per station capped at PATH_CAP_M 25 km, a path may enter a foreign zone but not leave it; adjacency = cheapest settled node per foreign zone; undirected dedupe; drop segments with path/straight > MAX_PATH_RATIO 3; Douglas-Peucker 10 m only if output > 8 MiB (not triggered: 494 KB).
- Outputs: data/nr/stations.json [{crs,name,lat,lon}], data/nr/segments.json [{a,b,lenM,poly}].

## 2. Inventory

| Line | Mode | Physical branches | Stops | km | Straight chords | RunTimes filled |
|---|---|---:|---:|---:|---:|---:|
| Bakerloo | tube | 1 | 25 | 23.29 | 0/24 | 48/48 |
| Central | tube | 7 | 49 | 73.28 | 0/49 | 98/98 |
| Circle | tube | 2 | 36 | 26.63 | 0/36 | 72/72 |
| District | tube | 7 | 60 | 62.69 | 0/59 | 118/118 |
| Hammersmith & City | tube | 1 | 29 | 25.59 | 0/28 | 56/56 |
| Jubilee | tube | 1 | 27 | 36.93 | 0/26 | 52/52 |
| Metropolitan | tube | 11 | 35 | 95.34 | 0/48 | 66/68 |
| Northern | tube | 10 | 52 | 60.49 | 0/53 | 106/106 |
| Piccadilly | tube | 8 | 53 | 89.42 | 0/63 | 104/104 |
| Victoria | tube | 1 | 16 | 21.45 | 0/15 | 30/30 |
| Waterloo & City | tube | 1 | 2 | 2.15 | 0/1 | 2/2 |
| DLR | dlr | 16 | 45 | 43.09 | 0/59 | 91/92 |
| Elizabeth line | elizabeth-line | 12 | 43 | 135.41 | 0/42 | 0/84 |
| Liberty | overground | 1 | 3 | 5.30 | 0/2 | 0/4 |
| Lioness | overground | 1 | 19 | 28.40 | 0/18 | 0/36 |
| Mildmay | overground | 4 | 29 | 46.80 | 0/32 | 0/54 |
| Suffragette | overground | 1 | 13 | 23.27 | 0/12 | 0/24 |
| Weaver | overground | 5 | 25 | 37.62 | 0/24 | 0/48 |
| Windrush | overground | 6 | 29 | 37.74 | 0/28 | 0/56 |
| Trams | tram | 9 | 39 | 36.80 | 16/54 | 71/71 |
| IFS Cloud Cable Car | cable-car | 1 | 2 | 1.11 | 1/1 | 2/2 |
| RB1 | river-bus | 10 | 18 | 56.58 | 0/29 | 34/34 |
| RB4 | river-bus | 1 | 2 | 0.27 | 0/1 | 2/2 |
| RB6 | river-bus | 22 | 23 | 55.28 | 0/29 | 50/50 |
| Woolwich Ferry | river-bus | 1 | 2 | 0.30 | 1/1 | 2/2 |
| Total | | 140 | | ≈1025 | 18/734 (2.5%) | 1004/1313 (76.5%) |

Geometry source: OSM railway relation for 19 lines (11 tube, DLR, Elizabeth, 6 Overground) with per-segment TfL fallback; OSM Thames centreline for RB1/RB4/RB6; TfL Route/Sequence only for Trams, Cable Car, Woolwich Ferry (README's "real OSM geometry" claim for tram/cable car is wrong).

National Rail: 431 stations, 579 segments, 1,373 km, 2.69 neighbours/station, segment length 45 m / 1,880 m median / 12,742 m max, 41.4 polyline points per segment.

## 3. Run-time coverage
segmentRunTime (position-inference.ts:221-231): scheduled ≥ 20 s → min(300, scheduled + 30); else clamp(45, 300, length / 12 m/s). 1,004/1,313 gaps (76.5%) use scheduled + 30 s; 309 (23.5%) use the geometric fallback, 306 of them on the 7 lines with zero scheduled coverage (Elizabeth + six Overground names, whose TfL line ids postdate the original bake; likely the Timetable API did not serve them). Remaining 3 fallbacks: one gap each on Metropolitan and DLR. No timing field in the NR graph.

## 4. Limitations
1. Per-segment provenance (OSM vs TfL fallback) not persisted; only "is a 2-point chord" is observable.
2. NR station snapping silently drops stations > 500 m from rail; dropped list not archived.
3. NR adjacency is geometric, not timetable topology; some real pairs exist only as multi-hop chains.
4. OSM overlay covers 19/25 lines; Tram has 29.6% straight chords.
5. 18/734 segments are straight chords (16 tram + cable car + ferry, the last two genuine single spans).
6. No automated re-bake: branches/lines/stations last touched 2026-07-24; data/nr never re-baked since 2026-07-23.
7. docs/ARCHITECTURE.md describes different scripts/outputs than shipped.
8. Overground/Elizabeth run-time coverage is 0%: every train there is positioned by the geometric fallback.
9. Coordinates 5 dp (~1.1 m).
10. NR DP simplification is conditional on output size (latent behaviour change).
