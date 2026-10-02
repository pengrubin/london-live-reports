#!/usr/bin/env python3
"""Measurements A and F: payload size of every public GET endpoint.

    python3 measure_endpoints.py --base https://london.pengrubin.com --rounds 5 \
        --label london --out ../data
    python3 measure_endpoints.py --base https://dubai.pengrubin.com --rounds 3 \
        --label dubai --out ../data

For each endpoint and round, two requests are made with curl, one asking for
brotli and one for gzip. The body is saved exactly as it came off the wire
(curl is NOT given --compressed), so %{size_download} is the wire size; the
script then decodes it to obtain the raw size and the record count. The raw
size and the record count in the CSV come from the brotli response.

Politeness: requests are strictly sequential (concurrency 1) with at least
REQUEST_GAP_S between them, which keeps the rate under one request per second.

Outputs (in --out):
    endpoints-samples-<label>.csv   one row per endpoint x round
    endpoints[-<label>].csv         medians per endpoint
"""

import argparse
import csv
import gzip
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import brotli

REQUEST_GAP_S = 1.1
CURL_TIMEOUT_S = 40
USER_AGENT = "architecture-calibration/1.0 (payload measurement; 1 req/s)"
HEADER_KEYS = ["x-cache", "cf-cache-status", "age", "cache-control", "content-encoding", "content-type"]

_last_request_at = 0.0


def polite_wait():
    global _last_request_at
    wait = REQUEST_GAP_S - (time.time() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.time()


def fetch(url, encoding):
    """One GET. Returns dict with status, wire bytes, timings, headers, raw body bytes."""
    polite_wait()
    with tempfile.TemporaryDirectory() as tmp:
        body_path = os.path.join(tmp, "body")
        head_path = os.path.join(tmp, "head")
        fmt = "%{http_code} %{size_download} %{time_starttransfer} %{time_total}"
        started = time.time()
        proc = subprocess.run(
            ["curl", "-s", "-m", str(CURL_TIMEOUT_S), "-A", USER_AGENT,
             "-H", f"Accept-Encoding: {encoding}", "-D", head_path, "-o", body_path,
             "-w", fmt, url],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return {"status": 0, "error": f"curl exit {proc.returncode}"}
        code, size, ttfb, total = proc.stdout.split()
        headers = {}
        with open(head_path, "r", errors="replace") as fh:
            for line in fh:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
        with open(body_path, "rb") as fh:
            wire = fh.read()
    applied = headers.get("content-encoding", "identity")
    try:
        if applied == "br":
            raw = brotli.decompress(wire)
        elif applied == "gzip":
            raw = gzip.decompress(wire)
        else:
            raw = wire
    except Exception as err:  # noqa: BLE001 - record and carry on
        return {"status": int(code), "error": f"decode failed: {type(err).__name__}"}
    return {
        "status": int(code),
        "requested_at": started,
        "wire_bytes": int(size),
        "raw_bytes": len(raw),
        "ttfb_s": float(ttfb),
        "total_s": float(total),
        "headers": headers,
        "applied_encoding": applied,
        "raw": raw,
    }


def count_records(raw):
    """(count, basis) for a JSON body. Never raises."""
    try:
        doc = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None, "not-json"
    if isinstance(doc, list):
        return len(doc), "array length"
    if isinstance(doc, dict):
        if isinstance(doc.get("features"), list):
            return len(doc["features"]), "features[]"
        lists = [(k, len(v)) for k, v in doc.items() if isinstance(v, list)]
        if lists:
            key, size = max(lists, key=lambda kv: kv[1])
            return size, f"{key}[]"
        dicts = [(k, len(v)) for k, v in doc.items() if isinstance(v, dict)]
        if dicts:
            key, size = max(dicts, key=lambda kv: kv[1])
            return size, f"keys of {key}"
        return len(doc), "top-level keys"
    return None, "scalar"


def discover(base, nr_hubs=("WAT",)):
    """Endpoint list for this deployment, from its own capabilities and manifest."""
    caps = json.loads(fetch(f"{base}/api/capabilities", "br")["raw"])
    layers = caps.get("layers", {})
    center = caps.get("region", {}).get("center", [-0.1276, 51.5072])
    manifest_res = fetch(f"{base}/manifest.json", "br")
    line_ids = []
    if manifest_res.get("status") == 200:
        line_ids = [line["id"] for line in json.loads(manifest_res["raw"]).get("lines", [])]
    index_res = fetch(f"{base}/api/bus-routes-index", "br")
    route_keys = json.loads(index_res["raw"]) if index_res.get("status") == 200 else []

    endpoints = [("health", "/health"), ("capabilities", "/api/capabilities")]
    if line_ids and layers.get("trainPositions"):
        endpoints.append((f"arrivals ({len(line_ids)} lines)", f"/api/arrivals?lines={','.join(line_ids)}"))
    endpoints += [
        ("buses", "/api/buses"),
        ("diversions", "/api/diversions"),
        ("coverage", "/api/coverage"),
        ("vessels", "/api/vessels"),
        ("aircraft", "/api/aircraft"),
        ("bikes (GBFS)", "/api/bikes"),
    ]
    if layers.get("bikePoints"):
        endpoints.append(("bike-points (TfL, around centre)",
                          f"/api/bike-points?lat={center[1]:.5f}&lon={center[0]:.5f}"))
    if layers.get("roadDisruptions"):
        endpoints.append(("road-disruptions", "/api/road-disruptions"))
    if layers.get("disruptions"):
        endpoints.append(("disruptions", "/api/disruptions"))
    if layers.get("busStopClosures"):
        endpoints.append(("bus-stop-closures", "/api/bus-stop-closures"))
    if layers.get("jamCams"):
        endpoints.append(("jamcams", "/api/jamcams"))
    if layers.get("lineStatus") and line_ids:
        endpoints.append(("lift-disruptions", "/api/lift-disruptions"))
    for mode in ("bus", "train", "ship"):
        endpoints.append((f"leaderboard day/{mode}", f"/api/leaderboard?period=day&mode={mode}"))
    endpoints.append(("tide-gauges", "/api/tide-gauges"))
    if layers.get("nationalRail"):
        for crs in nr_hubs:
            endpoints.append((f"nr-board ({crs})", f"/api/nr-board?crs={crs}"))
        endpoints.append(("static nr/segments.json", "/nr/segments.json"))
        endpoints.append(("static nr/stations.json", "/nr/stations.json"))
    endpoints.append(("bus-routes-index", "/api/bus-routes-index"))
    if route_keys:
        preferred = [k for k in route_keys if k.startswith("TFLO_88_")] or route_keys
        endpoints.append((f"learned route file ({preferred[0]})", f"/bus-routes/learned/{preferred[0]}.json"))
    endpoints.append(("static manifest.json", "/manifest.json"))
    if line_ids:
        sample_line = "central" if "central" in line_ids else line_ids[0]
        endpoints.append((f"static branches/{sample_line}.json", f"/branches/{sample_line}.json"))
        endpoints.append((f"static lines/{sample_line}.json", f"/lines/{sample_line}.json"))
        endpoints.append((f"static stations/{sample_line}.json", f"/stations/{sample_line}.json"))
    return endpoints, {"line_ids": line_ids, "learned_routes": len(route_keys), "layers": layers}


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def mode_of(values):
    values = [v for v in values if v]
    return max(set(values), key=values.count) if values else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--round-gap", type=float, default=20.0,
                        help="pause between rounds, seconds (rounds already take > 1 min each)")
    parser.add_argument("--nr-hubs", default="WAT", help="comma-separated CRS codes for /api/nr-board")
    parser.add_argument("--only", default="", help="measure only endpoints whose name contains this")
    parser.add_argument("--suffix", default="", help="appended to output file names (supplementary runs)")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    endpoints, context = discover(args.base, tuple(args.nr_hubs.split(",")))
    if args.only:
        endpoints = [e for e in endpoints if args.only in e[0]]
    print(f"{args.label}: {len(endpoints)} endpoints, {len(context['line_ids'])} manifest lines, "
          f"{context['learned_routes']} learned routes", flush=True)

    sample_rows = []
    for round_no in range(1, args.rounds + 1):
        for name, path in endpoints:
            url = args.base + path
            br = fetch(url, "br")
            gz = fetch(url, "gzip")
            row = {"deployment": args.label, "endpoint": name, "round": round_no,
                   "path": path.split("?")[0]}
            if br.get("status") == 200 and "error" not in br:
                count, basis = count_records(br["raw"])
                row.update({
                    "sampled_at_utc": datetime.fromtimestamp(br["requested_at"], timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "status": br["status"], "raw_bytes": br["raw_bytes"],
                    "br_wire_bytes": br["wire_bytes"] if br["applied_encoding"] == "br" else None,
                    "records": count, "count_basis": basis,
                    "ttfb_ms": round(br["ttfb_s"] * 1000), "total_ms": round(br["total_s"] * 1000),
                })
                for key in HEADER_KEYS:
                    row[key] = br["headers"].get(key, "")
            else:
                # Never store an error body: upstream errors can echo credentials.
                row.update({"status": br.get("status"), "error": br.get("error", "non-200")})
            if gz.get("status") == 200 and "error" not in gz:
                row["gzip_wire_bytes"] = gz["wire_bytes"] if gz["applied_encoding"] == "gzip" else None
                row["gzip_total_ms"] = round(gz["total_s"] * 1000)
            sample_rows.append(row)
        print(f"  round {round_no}/{args.rounds} done", flush=True)
        if round_no < args.rounds:
            time.sleep(args.round_gap)

    sample_fields = ["deployment", "endpoint", "path", "round", "sampled_at_utc", "status", "raw_bytes",
                     "gzip_wire_bytes", "br_wire_bytes", "records", "count_basis", "ttfb_ms", "total_ms",
                     "gzip_total_ms"] + HEADER_KEYS + ["error"]
    with open(os.path.join(args.out, f"endpoints-samples-{args.label}{args.suffix}.csv"), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=sample_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sample_rows)

    summary_fields = ["deployment", "endpoint", "path", "measured_utc", "samples_ok", "raw_bytes_median",
                      "gzip_wire_bytes_median", "br_wire_bytes_median", "raw_over_br", "records_median",
                      "count_basis", "raw_bytes_per_record", "br_bytes_per_record", "ttfb_ms_median",
                      "total_ms_median", "x_cache", "cf_cache_status", "age_s_median", "cache_control",
                      "method"]
    summary_name = ("endpoints" if args.label == "london" else f"endpoints-{args.label}") + f"{args.suffix}.csv"
    with open(os.path.join(args.out, summary_name), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fields)
        writer.writeheader()
        for name, path in endpoints:
            rows = [r for r in sample_rows if r["endpoint"] == name and r.get("status") == 200]
            if not rows:
                writer.writerow({"deployment": args.label, "endpoint": name, "path": path.split("?")[0],
                                 "samples_ok": 0, "method": "no successful sample"})
                continue
            raw = median([r.get("raw_bytes") for r in rows])
            br = median([r.get("br_wire_bytes") for r in rows])
            records = median([r.get("records") for r in rows])
            ages = [int(r["age"]) for r in rows if str(r.get("age", "")).isdigit()]
            cache_states = sorted({r.get("cf-cache-status", "") for r in rows if r.get("cf-cache-status")})
            x_cache_states = sorted({r.get("x-cache", "") for r in rows if r.get("x-cache")})
            writer.writerow({
                "deployment": args.label, "endpoint": name, "path": path.split("?")[0],
                "measured_utc": f"{rows[0]['sampled_at_utc']}..{rows[-1]['sampled_at_utc']}",
                "samples_ok": len(rows),
                "raw_bytes_median": raw,
                "gzip_wire_bytes_median": median([r.get("gzip_wire_bytes") for r in rows]),
                "br_wire_bytes_median": br,
                "raw_over_br": round(raw / br, 2) if raw and br else None,
                "records_median": records,
                "count_basis": mode_of([r.get("count_basis") for r in rows]),
                "raw_bytes_per_record": round(raw / records, 1) if raw and records else None,
                "br_bytes_per_record": round(br / records, 1) if br and records else None,
                "ttfb_ms_median": median([r.get("ttfb_ms") for r in rows]),
                "total_ms_median": median([r.get("total_ms") for r in rows]),
                "x_cache": "|".join(x_cache_states),
                "cf_cache_status": "|".join(cache_states),
                "age_s_median": median(ages),
                "cache_control": mode_of([r.get("cache-control") for r in rows]),
                "method": "curl, Accept-Encoding br / gzip, wire = size_download, raw = decoded br body",
            })
    print(f"wrote {summary_name}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
