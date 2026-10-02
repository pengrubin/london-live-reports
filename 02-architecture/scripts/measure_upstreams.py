#!/usr/bin/env python3
"""Measurement B (part 1): size of one poll of each upstream feed.

    python3 measure_upstreams.py --env ~/london-live-worktrees/measure/backend/.env \
        --manifest ~/london-live-worktrees/measure/data/manifest.json \
        --backend-src ~/london-live-worktrees/measure/backend/src --out ../data/upstream-polls.json

Makes the same requests the backend makes (same URL shapes, from backend/src),
asking for gzip, and records for each: HTTP status, wire bytes (compressed, as
received), decoded bytes, and record count. Three samples 15 s apart for the two
heavy feeds (BODS SIRI-VM, TfL arrivals), one for the rest: 12 requests total.

SECRETS. Keys are read from the .env file into memory and used only to build
the request. This script never prints or stores a URL, a header, a key, or a
response body. On a non-200 it records the status code and nothing else,
because TfL error bodies echo the app key.
"""

import argparse
import gzip
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

LONDON_BBOX = "-0.55,51.25,0.35,51.72"  # region.ts DEFAULT_BBOX
STALE_AFTER_S = 300  # bods-client.ts STALE_AFTER_MS
HEAVY_SAMPLES = 3
HEAVY_GAP_S = 15
TIMEOUT_S = 40
RAIL_MODES_WITH_STATUS = {"tube", "dlr", "elizabeth-line", "overground", "tram"}


def read_env(path):
    values = {}
    with open(os.path.expanduser(path)) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def get(url, headers=None):
    """Returns (status, wire_bytes, decoded_bytes, decoded_body|None, seconds). Never raises."""
    # urllib's default User-Agent is refused (403) by TfL's and Darwin's front doors;
    # the backend's fetch announces itself as "node", so this does too.
    request = urllib.request.Request(
        url, headers={"Accept-Encoding": "gzip", "User-Agent": "node", **(headers or {})})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            wire = response.read()
            encoding = response.headers.get("Content-Encoding", "identity")
            status = response.status
    except urllib.error.HTTPError as err:
        err.read()  # drain; the body is deliberately discarded
        return err.code, None, None, None, time.time() - started, "n/a"
    except Exception as err:  # noqa: BLE001 - name only, never the message (may hold the URL)
        return 0, None, None, None, time.time() - started, type(err).__name__
    decoded = gzip.decompress(wire) if encoding == "gzip" else wire
    return status, len(wire), len(decoded), decoded, time.time() - started, encoding


SKIP = []


def measure(name, url, count, headers=None, samples=1, gap=0.0, poll_interval_s=None, cadence_note=""):
    if any(fragment in name for fragment in SKIP):
        return None
    rows = []
    for i in range(samples):
        tick = time.time()
        status, wire, decoded_len, body, seconds, encoding = get(url, headers)
        row = {"at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": status,
               "wire_bytes": wire, "decoded_bytes": decoded_len, "content_encoding": encoding,
               "seconds": round(seconds, 2)}
        if status == 200 and body is not None:
            try:
                row.update(count(body))
            except Exception as err:  # noqa: BLE001
                row["count_error"] = type(err).__name__
        rows.append(row)
        print(f"  {name}: status {status}, wire {wire}, decoded {decoded_len}", flush=True)
        if i < samples - 1:
            time.sleep(max(0.0, gap - (time.time() - tick)))
    return {"feed": name, "poll_interval_s": poll_interval_s, "cadence_note": cadence_note, "samples": rows}


def count_siri(body):
    text = body.decode("utf-8", errors="replace")
    activities = text.count("<VehicleActivity>")
    now = time.time()
    fresh = 0
    for stamp in re.findall(r"<RecordedAtTime>([^<]+)</RecordedAtTime>", text):
        try:
            if now - datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() <= STALE_AFTER_S:
                fresh += 1
        except ValueError:
            continue
    return {"records": activities, "records_fresh_within_5min": fresh,
            "decoded_bytes_per_record": round(len(body) / activities, 1) if activities else None}


def count_json_array(body):
    doc = json.loads(body)
    if isinstance(doc, list):
        out = {"records": len(doc)}
        if doc and isinstance(doc[0], dict) and "vehicleId" in doc[0]:
            out["distinct_vehicle_ids"] = len({p.get("vehicleId") for p in doc})
            out["distinct_lines"] = len({p.get("lineId") for p in doc})
        out["decoded_bytes_per_record"] = round(len(body) / len(doc), 1) if doc else None
        return out
    if isinstance(doc, dict):
        lists = {k: len(v) for k, v in doc.items() if isinstance(v, list)}
        if lists:
            key = max(lists, key=lists.get)
            return {"records": lists[key], "records_basis": key}
    return {"records": None}


def darwin_base(backend_src):
    """The LDBWS base URL exactly as darwin-client.ts spells it (RDM_BASE)."""
    with open(os.path.join(os.path.expanduser(backend_src), "darwin-client.ts")) as fh:
        return re.search(r"RDM_BASE\s*=\s*'([^']+)'", fh.read()).group(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--backend-src", required=True, help="backend/src of the measured commit")
    parser.add_argument("--skip", default="", help="comma-separated feed-name fragments to leave out; "
                        "their earlier results in --out are kept")
    args = parser.parse_args()
    SKIP.extend(fragment for fragment in args.skip.split(",") if fragment)
    env = read_env(args.env)
    with open(os.path.expanduser(args.manifest)) as fh:
        manifest_lines = json.load(fh)["lines"]
    line_ids = ",".join(sorted(line["id"] for line in manifest_lines))
    rail_ids = ",".join(sorted(l["id"] for l in manifest_lines if l.get("mode") in RAIL_MODES_WITH_STATUS))
    today = datetime.now(timezone.utc).date()

    feeds = []
    if env.get("BODS_API_KEY"):
        feeds.append(measure(
            "BODS SIRI-VM (all-London bbox)",
            f"https://data.bus-data.dft.gov.uk/api/v1/datafeed/?boundingBox={LONDON_BBOX}"
            f"&api_key={env['BODS_API_KEY']}",
            count_siri, samples=HEAVY_SAMPLES, gap=HEAVY_GAP_S, poll_interval_s=15,
            cadence_note="bods-client.ts POLL_INTERVAL_MS, unconditional"))
    if env.get("TFL_APP_KEY"):
        key = env["TFL_APP_KEY"]
        feeds.append(measure(
            f"TfL /Line/{{{len(manifest_lines)} ids}}/Arrivals",
            f"https://api.tfl.gov.uk/Line/{line_ids}/Arrivals?app_key={key}",
            count_json_array, headers={"Accept": "application/json"}, samples=HEAVY_SAMPLES,
            gap=HEAVY_GAP_S, poll_interval_s=15,
            cadence_note="leaderboard.ts SAMPLE_INTERVAL_MS 15 s through an 8 s cache shared with "
                         "/api/arrivals; viewers polling at 10 s can raise it to at most one per 8 s"))
        feeds.append(measure(
            "TfL /Line/{rail ids}/Status/{from}/to/{to} (detail)",
            f"https://api.tfl.gov.uk/Line/{rail_ids}/Status/{today}/to/{today + timedelta(days=7)}"
            f"?detail=true&app_key={key}",
            count_json_array, headers={"Accept": "application/json"},
            cadence_note="status recorder and /api/disruptions; see upstream request log for the rate"))
        feeds.append(measure(
            "TfL /Road/all/Disruption",
            f"https://api.tfl.gov.uk/Road/all/Disruption?stripContent=false&app_key={key}",
            count_json_array, headers={"Accept": "application/json"},
            cadence_note="road-disruptions recorder and /api/road-disruptions (120 s cache)"))
        feeds.append(measure(
            "TfL /StopPoint/Mode/bus/Disruption",
            f"https://api.tfl.gov.uk/StopPoint/Mode/bus/Disruption?app_key={key}",
            count_json_array, headers={"Accept": "application/json"},
            cadence_note="/api/bus-stop-closures"))
    if env.get("DARWIN_TOKEN"):
        feeds.append(measure(
            "Darwin LDBWS GetDepBoardWithDetails (WAT)",
            f"{darwin_base(args.backend_src)}/GetDepBoardWithDetails/WAT?numRows=20&timeWindow=120",
            lambda body: {"records": len(json.loads(body).get("trainServices") or [])},
            headers={"x-apikey": env["DARWIN_TOKEN"], "Accept": "application/json"},
            cadence_note="nr-sampler.ts: one of 17 hubs per 15 s sample, 45 s cache"))
    feeds.append(measure(
        "ADS-B airplanes.live /v2/point (30 nm)",
        "https://api.airplanes.live/v2/point/51.5/-0.12/30",
        lambda body: {"records": len(json.loads(body).get("ac") or [])},
        headers={"Accept": "application/json"},
        cadence_note="on demand only: /api/aircraft, 4 s cache, viewers poll at 5 s"))

    feeds = [feed for feed in feeds if feed is not None]
    if SKIP and os.path.exists(args.out):
        with open(args.out) as fh:
            earlier = json.load(fh)["feeds"]
        measured_now = {feed["feed"] for feed in feeds}
        feeds = [f for f in earlier if f["feed"] not in measured_now] + feeds

    result = {"measurement": "B: one poll of each upstream feed", "measured_on": "2026-09-29",
              "method": "same URL shapes as backend/src, Accept-Encoding gzip, urllib; wire = bytes "
                        "received, decoded = after gunzip; no body, URL or key is stored",
              "feeds": feeds}
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2)


if __name__ == "__main__":
    main()
