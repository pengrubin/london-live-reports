#!/usr/bin/env python3
"""Measurement B (part 2): assemble data/streams.csv from the measured pieces.

    python3 build_streams.py --data ../data

No new measurement happens here. Each row joins
    size of one poll      <- upstream-polls.json      (measure_upstreams.py)
    request cadence, wire <- cpu-profile-summary.json (local run, undici counters)
    served record counts  <- endpoints.csv            (production)
and states which of the three each number came from.
"""

import argparse
import csv
import json
import os
import statistics

SECONDS_PER_DAY = 86_400
QUIET = "quiet (pipeline only, no viewer)"
VIEWER = "viewer (pipeline + one synthetic viewer)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    args = parser.parse_args()
    data = args.data

    polls = {f["feed"]: f for f in json.load(open(os.path.join(data, "upstream-polls.json")))["feeds"]}
    run = json.load(open(os.path.join(data, "cpu-profile-summary.json")))
    endpoints = {r["endpoint"]: r for r in csv.DictReader(open(os.path.join(data, "endpoints.csv")))}
    nr = list(csv.DictReader(open(os.path.join(data, "endpoints-nr-board.csv"))))

    def cadence(fragment, phase):
        for row in run["upstream_requests_by_phase"][phase]["by_upstream"]:
            if fragment in row["upstream"]:
                return row
        return None

    def poll_medians(fragment):
        feed = next(f for name, f in polls.items() if fragment in name)
        ok = [s for s in feed["samples"] if s["status"] == 200]
        if not ok:
            return None, feed
        med = lambda key: statistics.median([s[key] for s in ok if s.get(key) is not None] or [0])  # noqa: E731
        return {"wire": med("wire_bytes"), "decoded": med("decoded_bytes"), "records": med("records"),
                "at": f"{ok[0]['at_utc']}..{ok[-1]['at_utc']}", "samples": ok}, feed

    rows = []

    def add(stream, upstream, transport, interval_s, trigger, wire, decoded, records, unit, measured,
            method, caveat):
        per_s = (lambda v: round(v / interval_s, 2) if v is not None and interval_s else "")
        per_day = (lambda v: int(v / interval_s * SECONDS_PER_DAY) if v is not None and interval_s else "")
        rows.append({
            "stream": stream, "upstream": upstream, "transport": transport,
            "poll_interval_s": interval_s if interval_s else "", "trigger": trigger,
            "wire_bytes_per_poll": wire if wire is not None else "",
            "decoded_bytes_per_poll": decoded if decoded is not None else "",
            "records_per_poll": records if records is not None else "", "record_unit": unit,
            "records_per_s": per_s(records), "wire_bytes_per_s": per_s(wire),
            "decoded_bytes_per_s": per_s(decoded), "wire_bytes_per_day": per_day(wire),
            "decoded_bytes_per_day": per_day(decoded), "measured_utc": measured, "method": method,
            "caveat": caveat,
        })

    bods, _ = poll_medians("BODS")
    fresh = statistics.median([s["records_fresh_within_5min"] for s in bods["samples"]])
    logged = run["bus_polls_logged"]
    add("bus positions", "DfT BODS SIRI-VM datafeed, London bbox", "HTTPS GET, gzip, XML",
        15, "timer, unconditional (bods-client.ts POLL_INTERVAL_MS)",
        int(bods["wire"]), int(bods["decoded"]), int(bods["records"]), "VehicleActivity element",
        bods["at"],
        f"3 direct polls for size; cadence from the local run: {cadence('bus-data', QUIET)['requests']} "
        f"requests in 360 s, median logged interval {logged['poll_interval_s_median']} s",
        f"measured 23:33 BST: only {int(fresh)} of {int(bods['records'])} elements were newer than 5 min "
        f"(the rest are dropped by the parser), and the local run kept {logged['vehicles_median']:.0f} "
        f"vehicles per poll; by day the kept count is about 9-10 thousand (memory-fit.json, by hour)")
    written = run["files_written_by_the_run"]["bus-traces"]
    add("bus positions, after de-duplication (new fixes only)", "derived from the stream above",
        "in process", 15, "every bus poll; a fix is kept when RecordedAtTime changed", None,
        int(written["bytes"] / written["polls_in_run"]), written["new_fixes_per_poll"], "GPS fix",
        "2026-09-29T22:14Z..22:27Z",
        f"trace file written by the local run: {written['lines']} lines, {written['bytes']} bytes in "
        f"{written['polls_in_run']} polls",
        "night-time; the first poll writes every vehicle once, which inflates the mean by about 6 %")

    arrivals, _ = poll_medians("Arrivals")
    vehicles = statistics.median([s["distinct_vehicle_ids"] for s in arrivals["samples"]])
    quiet, busy = cadence("/Arrivals", QUIET), cadence("/Arrivals", VIEWER)
    add("train arrival predictions (no viewer)", "TfL Unified API /Line/{25 ids}/Arrivals",
        "HTTPS GET, gzip, JSON", quiet["mean_interval_s"],
        "leaderboard sampler, 15 s, through the 8 s cache shared with /api/arrivals",
        int(arrivals["wire"]), int(arrivals["decoded"]), int(arrivals["records"]), "prediction",
        arrivals["at"],
        f"3 direct polls for size; cadence from the local run quiet phase ({quiet['requests']} requests "
        f"in 360 s); undici counted {quiet['wire_bytes_per_completed_request']} wire bytes per request",
        f"{vehicles:.0f} distinct vehicleIds behind {int(arrivals['records'])} predictions at 23:35 BST; "
        f"production served {endpoints['arrivals (25 lines)']['records_median']} predictions in "
        f"{endpoints['arrivals (25 lines)']['raw_bytes_median']} bytes 15 min earlier")
    add("train arrival predictions (one viewer polling at 10 s)", "TfL Unified API /Line/{25 ids}/Arrivals",
        "HTTPS GET, gzip, JSON", busy["mean_interval_s"],
        "sampler + viewer misses on the 8 s cache; floor is one fetch per 8 s however many viewers",
        int(arrivals["wire"]), int(arrivals["decoded"]), int(arrivals["records"]), "prediction",
        arrivals["at"],
        f"cadence from the local run viewer phase ({busy['requests']} requests in 360 s)",
        "in production Cloudflare sits in front, so viewer count does not translate one-to-one into origin requests")

    darwin_quiet = cadence("GetDepBoardWithDetails", QUIET)
    nr_raw = statistics.median([float(r["raw_bytes_median"]) for r in nr])
    nr_records = statistics.median([float(r["records_median"]) for r in nr])
    add("National Rail departure boards", "Darwin LDBWS GetDepBoardWithDetails (Rail Data Marketplace)",
        "HTTPS GET, identity, JSON", darwin_quiet["mean_interval_s"],
        "nr-sampler.ts: one of 17 hubs per 15 s leaderboard sample, 45 s cache",
        darwin_quiet["wire_bytes_per_completed_request"], darwin_quiet["wire_bytes_per_completed_request"],
        int(nr_records), "train service",
        "2026-09-29T22:15Z..22:27Z",
        "bytes and cadence from the local run (undici counters, response is not compressed so wire = "
        "decoded); records from production /api/nr-board for VIC and CLJ",
        f"upstream answered HTTP 500 for WAT throughout (production /api/nr-board?crs=WAT also 500); "
        f"the proxy reshapes a board to about {int(nr_raw)} bytes before serving it")

    status, _ = poll_medians("Status/{from}")
    status_quiet = cadence("/Status/{from}", QUIET)
    add("rail line status, 7-day window with detail", "TfL /Line/{20 ids}/Status/{from}/to/{to}",
        "HTTPS GET, gzip, JSON", status_quiet["mean_interval_s"], "status recorder, every 2 min (status-recorder.ts pollMs)",
        int(status["wire"]), int(status["decoded"]), int(status["records"]), "line", status["at"],
        f"1 direct poll for size; cadence from the local run quiet phase ({status_quiet['requests']} in 360 s)",
        "one viewer adds /api/disruptions fetches on top (90 s poll): 7 requests in 360 s in the viewer phase")
    mode_quiet = cadence("/Line/Mode/", QUIET)
    add("rail line status by mode (no detail)", "TfL /Line/Mode/{modes}/Status", "HTTPS GET, gzip, JSON",
        mode_quiet["mean_interval_s"], "status recorder, every 2 min (status-recorder.ts pollMs), alongside the window form",
        mode_quiet["wire_bytes_per_completed_request"], None, None, "line", "2026-09-29T22:15Z..22:27Z",
        "local run, undici counters (wire bytes only)", "decoded size not measured")

    road, _ = poll_medians("Road/all")
    add("road disruptions", "TfL /Road/all/Disruption", "HTTPS GET, gzip, JSON", 120,
        "on demand: /api/road-disruptions, 120 s cache; plus the archive recorder every 6 h",
        int(road["wire"]), int(road["decoded"]), int(road["records"]), "disruption", road["at"],
        "1 direct poll for size; interval is the cache TTL, i.e. the fastest the upstream can be asked",
        "with no viewer only the 6-hourly recorder asks: none in the quiet phase, 2 in 360 s with one viewer")
    stops, _ = poll_medians("StopPoint/Mode/bus")
    add("bus stop closures", "TfL /StopPoint/Mode/bus/Disruption", "HTTPS GET, gzip, JSON", 300,
        "on demand: /api/bus-stop-closures, viewers poll at 300 s",
        int(stops["wire"]), int(stops["decoded"]), int(stops["records"]), "stop disruption", stops["at"],
        "1 direct poll for size; interval is the viewer poll interval",
        "stop ids missing from the baked gazetteer cost extra /StopPoint/{ids} lookups: 14 on the first "
        "request of the first local run, none once the resolved ids had been written back")

    tide = endpoints["tide-gauges"]
    add("tide gauges", "Environment Agency flood-monitoring API", "HTTPS GET, gzip, JSON", 300,
        "on demand: /api/tide-gauges, 300 s cache; one refresh = 1 readings + 10 per-station requests",
        4400 + 10 * 356, None, int(float(tide["records_median"])), "gauge", "2026-09-29T22:21Z..22:27Z",
        "local run viewer phase, undici counters (wire bytes); records from production",
        "plus a 24 KB station catalogue once an hour; decoded size not measured")

    vessels = endpoints["vessels"]
    add("vessel positions", "aisstream.io", "WebSocket push", None, "continuous stream", None, None,
        int(float(vessels["records_median"])), "vessel in table (not messages)", vessels["measured_utc"],
        "table size from production /api/vessels", "inbound message rate and bytes NOT measured: the "
        "stream is a WebSocket and neither the log nor undici's request counters see its frames")
    aircraft = endpoints["aircraft"]
    add("aircraft positions", "airplanes.live, fallback adsb.lol", "HTTPS GET, JSON", None,
        "on demand: /api/aircraft, 4 s cache, viewers poll at 5 s; no rate given, the feed is down", None,
        int(float(aircraft["raw_bytes_median"])), int(float(aircraft["records_median"])), "aircraft",
        aircraft["measured_utc"],
        "size of the body production serves; both upstreams answered HTTP 403 from the measuring machine",
        "NOT LIVE: production answers x-cache: stale and the body's own timestamp is 2026-08-21, "
        "39 days old. The size is that of the last good response, not of today's traffic")
    add("docked bikes (GBFS)", "not configured for London (GBFS_URL unset)", "HTTPS GET, JSON", 60,
        "timer (gbfs-client.ts STATUS_POLL_MS) when configured", None, None, 0, "station",
        endpoints["bikes (GBFS)"]["measured_utc"], "production /api/bikes returns []",
        "Dubai runs this feed: 213 stations, 19 KB served (endpoints-dubai.csv); upstream size not measured")

    fields = ["stream", "upstream", "transport", "poll_interval_s", "trigger", "wire_bytes_per_poll",
              "decoded_bytes_per_poll", "records_per_poll", "record_unit", "records_per_s",
              "wire_bytes_per_s", "decoded_bytes_per_s", "wire_bytes_per_day", "decoded_bytes_per_day",
              "measured_utc", "method", "caveat"]
    with open(os.path.join(data, "streams.csv"), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row["stream"], "|", row["poll_interval_s"], "|", row["wire_bytes_per_poll"], "|",
              row["decoded_bytes_per_poll"], "|", row["records_per_poll"], "|", row["records_per_s"], "|",
              row["decoded_bytes_per_s"], "|", row["decoded_bytes_per_day"], "|", row["wire_bytes_per_day"])


if __name__ == "__main__":
    main()
