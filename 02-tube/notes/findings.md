# Findings: TfL Arrivals feed vs the inference rules (agent output, 2026-10-01)

Inputs: `~/bus-archive/arrivals/2026-09-28 … 2026-10-01.jsonl.gz` (10-01 frozen at 23:40 BST). Scripts: `analyze-arrivals.py` → `data/arrivals-metrics.json` + `data/arrivals/m*.csv`; `check-timestamps.py` → `data/arrivals-timestamps.json`; `fig-arrivals.py` → `figures/fig-v-1..6` + `arr_*` keys. Four-day run: 171 s, 104 MB max RSS.

Sample: 8,736 polls, 57.0 M rows, 5 error polls, 5,721 polls in which some line's timestamp moved forward. Per day 1,004 / 2,598 / 2,417 / 2,722. 22 lines returned rows; rb4, woolwich-ferry, cable car none.

## Script changes
1. Analyzer tolerates a truncated last gzip member; records `day_hours` and `gaps`.
2. Method fix: 10.24% of line-polls carry a TfL timestamp OLDER than one already seen; they were counted as fresh, now stale (878 whole polls). 1-poll flickers fell 8,259→4,390 (tube), 1,869→1,048 (OG), 716→377 (Elizabeth); regression/stall shares moved <0.2 points.

## Coverage (BST, weekdays only)
Mon 28 Sep 16:38–24:00; Tue 29 full, gap 19:21–21:42; Wed 30 full, gaps 07:54–09:25 (AM peak) and 17:45–20:07 (PM peak); Thu 1 Oct 00:00–23:40. Gaps total 6.2 h (laptop asleep, not confirmed). AM peak covered Tue+Thu, PM peak Mon+Tue+Thu. No weekend, no Night Tube. Trains per fresh poll: tube 345, Overground 202, DLR 112, Elizabeth 91.

## The 12 metrics (J justified / C contradicted / U undecided)
- M1 cadence (J): stale polls 34.5% = 2,132 identical replays + 878 older bodies; per line-poll 24.3% same, 10.24% back, 65.5% forward. Effective fresh cadence mean 46.5 s (p50 44, p90 75). Data age p50 11 s, p90 43 s. Same-stop duplicate listings tube 7.8% (W&C 35%, Met 17%, Victoria 11%). An 8 s cache cannot replay a body 30 s later nor serve an older one after a newer one: cause is upstream or stale-serving; log x-cache to verify.
- M3 vehicleId (J): DLR 100% missing; Metropolitan 25.0% '000'; Jubilee 1.24%, District 0.34%, others <0.05%; Elizabeth/OG 100% present. Fallback load-bearing only on the Metropolitan (22.1% location-keyed, 2.8% timetable-keyed rows).
- M4 vocabulary (C for DEPARTED): tube rows at 42.6%, between 36.1%, approaching 8.7%, left 6.8%, departed 1.8%, sidings 1.7%, other 0.9%, leaving 0.6%. **currentLocation is 100% empty on Overground, Elizabeth, DLR, tram, river**: location rules are tube-only. DEPARTED misses "Departed" (Northern 7.6% of rows, Victoria 4.7%), "Leaving" (Jubilee 5.8%), Bakerloo "North/South of". Bakerloo sidings 15.8% of rows. SIDINGS misses "Neasden/Lillie Bridge Depot" (~4,600 rows). "Finchley Central Platform 3" (24,871 rows) matches no arm.
- M5 residual (J): tube 14.56 M pairs, regress 9.66%, stall 27.5%, p10/p90 −35/+30, 0 s bin 48.2%, ±20–40 s 33.7%, ±50–70 s 12.3%. DLR 1.19 M pairs, 13.21% / 34.1%, −35/+35. Overground 11.34 M, 0.27% / 1.2%, 0/0, zero bin 98.1%. Elizabeth 6.89 M, 0.41% / 1.2%, zero bin 98.0%. Per tube line regression 7.4% (H&C) to 15.0% (Bakerloo). **Surprise: tube/DLR residuals cluster at ±30 and ±60 s: countdowns refresh less often than the response timestamp, freeze a step, then catch up; most of the stall share is this stepping.** OG/Elizabeth tick exactly with the clock.
- M6 accuracy (U tube; J that OG/Elizabeth are self-consistent), error p10/p50/p90 s (actual − predicted): ≤30 s tube 0/0/30, DLR 0/0/60, OG 0/0/0; ≤120 s tube −30/0/60, DLR 0/30/90, OG 0/0/30, Eliz 0/0/20; ≤300 s tube −30/20/110, DLR 0/40/100, OG 0/0/60, Eliz 0/0/40; ≤480 s tube −50/30/130; ≤900 s tube −90/20/190; ≤1800 s tube −190/0/230. DLR arrives 30–50 s later than predicted at the median. Caveat: 50.2% of tube tracks censored; only 2.2% of arrivals from the "At" rule; OG/Elizabeth zero median partly circular.
- M7 flicker (U value, J need): per 1,000 train-polls tube 13.1 (65.5% of episodes last 3+ polls, 19.8% one poll), Overground 1.28 (80.4% one poll), Elizabeth 1.16, Victoria 21.9, Waterloo & City 195.8. A 1-poll absence spans 46–92 s here; long tube absences exceed RETAIN_MS.
- M8 stock groups (J): sub-surface 24.12% of vehicleId listings duplicated; margin p50 630 s, p90 1,440 s. **Every frequent pair includes H&C**: District+H&C 53,091, Circle+H&C 40,256, H&C+Met 37,096; Circle+District 6. Overground 1.91%, all Mildmay+Windrush, margin p50 2,040 s.
- M9 DLR (J): 54.3% of DLR rows within 480 s; 3.32 rows and 2.41 stop keys per leading-edge train; without the rule ~3 dots per train.
- M10 horizon (J need, U value): 92.9% of Elizabeth and OG rows position-less beyond 480 s; on the nearest stop 61.5% (Elizabeth) and 69.7% (OG) of train-observations beyond 480 s with no location; trains first appear ~2 h ahead (p50 7,080 s) vs 630–1,680 s on tube lines. With vehicleId always present the rule acts only through the position-less re-check.
- M11 location–countdown (J AT_PLATFORM_S, C DEPARTED, U 0.85): countdown ≤15 s (n 166,557): "Between" 41.3%, "At other" 18.9%, "Approaching own" 23.5%, "At own" 6.3%. "At own" (n 21,712): countdown p50 15 s, p90 35 s, 44.4% below 15 s, 7.3% ≥300 s (H&C 53.7% of its own "At" rows; terminus dwells, stations to verify). "Approaching own" (n 84,017): p50 15, p90 45 s. First poll after departure (n 287,368): p50 60 s, p90 170 s, 3.6% ≥600 s. DEPARTED misses 6.2% of tube departures: Northern 21.4%, Jubilee 12.6%, Victoria 8.0%.
- M12 identity (J): TfL id changes 0.0%; vehicleId keys ≥98.8% of rows on every tube line except Metropolitan (74.9%); Metropolitan location identities live p50 2 polls; 20,334 Met trains opened/closed vs 1,241 Northern.

## Sampling-bias caveats
1. Effective fresh cadence 46.5 s (p50 44, p90 75) against the map's 10 s/8 s cache: M5 lower bound; M7 undercounts short flickers, a 1-poll absence is 46–92 s.
2. 34.5% stale polls (24.3% identical, 10.24% older); residuals use TfL timestamps so unbiased, pair counts shrink.
3. Events resolved to 0–46 s; M6 conditioned on uncensored tracks (50% censored); weekdays only, 6.2 h gaps over one AM and one PM peak.

## Surprises, by consequence
1. 10.24% of line-polls older than an already-seen body. 2. Tube/DLR countdowns move in ~30 s steps. 3. currentLocation empty on every non-tube mode. 4. DEPARTED misses 21% of Northern departures. 5. All sub-surface duplicates involve H&C; H&C "At own" rows often show ≥300 s. 6. W&C flicker 196 per 1,000.
