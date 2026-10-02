# Validation design for document 2 (agent output, 2026-09-28)

Scripts: `02-tube/scripts/analyze-arrivals.py` (stdlib, streaming, ~2 min and <100 MB per day of samples; writes `data/arrivals-metrics.json` + 17 CSVs `m01..m12`), `02-tube/scripts/fig-arrivals.py` (fig-v-1..6, `put()` into numbers.json), `figstyle.py` copied from 01. Usage: `python3 scripts/analyze-arrivals.py --branches <london-live-2d>/data/branches --out data FILE...`. Identity rules ported verbatim from position-inference.ts (train_key, norm_station, STOCK_GROUP, DLR leading edges, RUN_HORIZON_S 480, AT_PLATFORM_S 15).

## Facts from the 17-minute sample that shaped the design
1. `timestamp` is per RESPONSE, not per row; 8 of 35 polls (23%) repeated the previous timestamp (cache/stale replays). Data age normally 5–14 s, but 44–59 s in some polls → backend stale-serving; worth a look for document 3.
2. DLR `id` is per station (cannot identify trains); TfL lists the next ~6 DLR trains per (direction, destination, stop) at a fixed 300 s spacing (149, 449, 749 …). Tube/OG/Elizabeth `id` is stable per (train, stop).
3. currentLocation vocabulary includes prefixes the inference's DEPARTED regex (/^(between|left)/) does NOT match: "Departed X" (Northern 393 rows, Victoria 34), "Leaving X" (Jubilee 135), "North/South of X" (Bakerloo). ≈2.6% of tube rows. Candidate code fix.
4. "At X" with countdown ≤ 15 s where X is the PREVIOUS stop is common (Northern 39 of ~250 near-platform rows): location text lags the countdown, mirror of the laggy "Approaching". Spelling variants the normaliser misses: "Plaform 1", "Kings Cross P7".
5. Elizabeth and all six Overground lines carry a vehicleId on 100% of rows: the "no id, no location" timetable branch is dead; the 480 s horizon acts on id-keyed trains.
6. Terminus trains are listed twice at one stop (Bakerloo at Elephant & Castle, 4–19% of rows on some lines).
7. Sample numbers: Metropolitan 18.4% "000" vehicleIds, Piccadilly 1.5%, DLR 100% empty; sub-surface cross-line duplicates 21.7% of listings (margin p50 630 s, so min-tts choice rarely ambiguous); OG duplicates 1.6%; tube countdown regressions 7–12% of pairs, stalls ~22%, residual p10/p90 ±35 s; 93% of Elizabeth rows beyond the 480 s horizon; tube tracks first appear at p50 ≈ 15 min ahead, OG/Elizabeth ≈ 65 min; location-keyed identities live 2 polls (p50).

## Metrics (12)
| # | Metric | Justifies / tests | Output |
|---|---|---|---|
| 1 | prediction-set size, update cadence, stale share, data age, duplicate listings | 10 s poll, 8 s cache, TTS_BLEND | m01, table |
| 2 | time-of-day coverage per 10-min bin | completeness, peak vs night | m02, fig-v-5 |
| 3 | vehicleId missing / "000" rate per line | currentLocation fallback, NO_VEHICLE_ID | m03 |
| 4 | currentLocation vocabulary by prefix class | DEPARTED, AT/APPROACHING regexes, SIDINGS | m04, fig-v-3 |
| 5 | countdown regression / residual (tts_prev − elapsed − tts_new) per mode | monotonic frac, TTS_BLEND, dead reckoning | m05, fig-v-1 |
| 6 | countdown accuracy vs realised arrival by horizon bucket (30 s … 3600 s); arrival = first "At <stop>" (rule at) else last countdown ≤ 45 s (rule reached); censored otherwise | ratio positioning, AT_PLATFORM_S, Approaching clamp, trust horizon | m06, fig-v-2 |
| 7 | flicker: vehicleId absent k polls then back, per 1,000 train-polls | RETAIN_MS 60 s, SUCCESSION_M | m07, fig-v-4 |
| 8 | S-stock / OG cross-line duplicate rate and min-tts margin | STOCK_GROUP dedup | m08 |
| 9 | DLR rows per train, leading edges via baked stop graph | DLR leading edge | m09 |
| 10 | timetable-horizon share; first-appearance horizon per line | RUN_HORIZON_S | m10 |
| 11 | location–countdown consistency: countdown while "At own", "Approaching own", at first poll after departure; near-platform prefix mix | At arm, APPROACHING_FRAC, AT_PLATFORM_S, DWELL_BUFFER_S, MIN/MAX_SEGMENT_RUN_S | m11, fig-v-6 |
| 12 | identity stability: key kinds, key lifetime, TfL id churn | synthetic identities, succession | m12 |

Hours suffice for 1, 3, 4, 8, 9, 12. ≥3 full days needed for 2, 6, 7, 10, 11 (and per-line splits of 5).

## Sampling bias to state in the document
- Sampler polls every 30 s; the map every 10 s against an 8 s cache. A regression that self-corrects within 30 s is invisible: metric 5 is a lower bound; a 1-poll flicker here is a 30 s absence, so metric 7 undercounts short flickers and overstates their length.
- 23% of polls were replays (same TfL timestamp), effective cadence ≈ 40 s; elapsed time uses the TfL timestamp so residuals are unbiased, pair counts are reduced.
- Arrival events observable only at poll granularity (±15 s), flooring metric 6's resolution and adding 0–30 s to "countdown at departure".
