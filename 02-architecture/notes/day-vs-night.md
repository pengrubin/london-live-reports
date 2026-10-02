# Day vs night calibration (two runs of the same scripts)

Night: 2026-09-29 22:14–22:40 UTC (`data-night-2026-09-29/`). Day: 2026-09-30 12:40–13:13 UTC (`data/`). Same code (origin/main 6875e27 in the measure worktree), same machine (Apple M4, Node 24.13), same method.

| Quantity | Night | Day | Reading |
|---|---|---|---|
| BODS elements per poll | 8,273 | 8,454 | the feed carries almost the same number of records day and night |
| Elements newer than 5 min (kept) | 3,314 | 6,416 | live fleet doubles; the rest are stale records the parser drops |
| BODS wire / decoded bytes per poll | 1.11 MB / 7.26 MB | 1.14 MB / 7.59 MB | +3–5% only: input volume is set by records carried, not by live vehicles |
| Logged parse ms per poll (parse + table + wire + sinks) | 44 | 42 | flat |
| Main-thread busy ms per 15 s, no viewer | 203.7 | 201.2 | flat: CPU is dominated by fixed per-poll work |
| Process CPU ms per 15 s, no profiler (control) | 423.7 (2.8% of a core) | 434.9 (2.9%) | flat |
| Heap used during run, median / peak MB | 183 / 218 | 193 / 237 | +10 MB for +3,700 vehicle states ≈ 2.7 KB each, consistent with the OLS slope 3.67 KB |
| RSS during run, median / peak MB | 543 / 606 | 598 / 664 | RSS moves with heap plus ~55 MB |
| vehicleStates at end of run | 4,466 | 8,191 | 30-min TTL window of distinct vehicles |
| /api/buses raw / brotli | 456 KB / 77 KB | 876 KB / 136 KB | ∝ live vehicles (135 B raw, 21 B br per bus) |
| /api/arrivals raw / brotli | 4.79 MB / 153 KB | 7.12 MB / 217 KB | ∝ predictions; 29× compression |
| /api/diversions raw | 339 KB | 161 KB | fewer live events at 13:00 than 23:00 (night stale events linger) |
| /api/vessels raw | 14 KB | 23 KB | 66 → 109 vessels |
| Bus fix age at response, p50 / p95 | 46.5 / 181.5 s | 32.0 / 155.1 s | operators report more often by day |
| Train arrivals predictions per poll | 4,487 | 8,084 | doubles; 7.4 MB decoded per fetch by day |

## Consequences for the formulas
1. Ingest and parse cost scale with **records carried by the feed** (≈ constant ~8.4k for London), not with live vehicles. Use N_records for stages 1–2 and N_live for stages 3–5.
2. Serving cost and egress scale with live vehicles (bus body) and with predictions (arrivals body).
3. Heap: 146 MB base + 3.7 KB per vehicle state + 0.3 KB per leaderboard total (OLS, R² 0.81); day-run delta confirms the slope within 30%.
4. Process CPU at London scale is ≈ 3% of one core regardless of time of day; a second core is not needed for the live path, but the nightly learner is a separate process that takes a core for ~30 min.
5. aircraft: night run had the stale 39-day body; day run after PR #56/#57: live, 87–92 aircraft, 55 KB raw.
