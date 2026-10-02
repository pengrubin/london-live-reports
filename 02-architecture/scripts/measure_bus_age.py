#!/usr/bin/env python3
"""Measurement G: source-to-server-response age of bus positions.

    python3 measure_bus_age.py --base https://london.pengrubin.com --samples 5 --gap 15 \
        --out ../data/bus-age.json

For each sample, GET /api/buses and compute (now - t) for every bus, where t is
the vehicle's RecordedAtTime in epoch ms (wire key `t`) and `now` is the local
wall clock at the moment the first response byte arrived. The response's Date
header is recorded as a check on the local clock, and the Cloudflare `age`
header as the part of the delay that the edge cache added.

Five requests in total, 15 s apart.
"""

import argparse
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import brotli

PERCENTILES = [5, 25, 50, 75, 90, 95, 99]


def percentile(sorted_values, pct):
    if not sorted_values:
        return None
    rank = (len(sorted_values) - 1) * pct / 100
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (rank - low)


def sample(base):
    with tempfile.TemporaryDirectory() as tmp:
        body_path, head_path = os.path.join(tmp, "b"), os.path.join(tmp, "h")
        started = time.time()
        proc = subprocess.run(
            ["curl", "-s", "-m", "30", "-H", "Accept-Encoding: br", "-D", head_path, "-o", body_path,
             "-w", "%{http_code} %{time_starttransfer} %{time_total}", f"{base}/api/buses"],
            capture_output=True, text=True, check=True,
        )
        code, ttfb, total = proc.stdout.split()
        headers = {}
        for line in open(head_path, errors="replace"):
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        wire = open(body_path, "rb").read()
    if code != "200":
        return {"status": int(code)}
    raw = brotli.decompress(wire) if headers.get("content-encoding") == "br" else wire
    buses = json.loads(raw)
    now_ms = (started + float(ttfb)) * 1000
    ages = sorted((now_ms - bus["t"]) / 1000 for bus in buses if isinstance(bus.get("t"), (int, float)))
    if not ages:
        # A deployment with no bus feed answers []: a result, not an error.
        return {"status": 200, "vehicles": 0, "_ages": [],
                "at_utc": datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    date_header = headers.get("date")
    clock_offset = None
    if date_header:
        clock_offset = round(now_ms / 1000 - parsedate_to_datetime(date_header).timestamp(), 1)
    return {
        "status": 200,
        "at_utc": datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vehicles": len(buses),
        "cf_cache_status": headers.get("cf-cache-status", ""),
        "edge_age_s": int(headers["age"]) if headers.get("age", "").isdigit() else None,
        "local_minus_date_header_s": clock_offset,
        "age_s": {
            "min": round(ages[0], 1),
            **{f"p{p}": round(percentile(ages, p), 1) for p in PERCENTILES},
            "max": round(ages[-1], 1),
            "mean": round(sum(ages) / len(ages), 1),
        },
        "share_under_30s": round(sum(a < 30 for a in ages) / len(ages), 4),
        "share_under_60s": round(sum(a < 60 for a in ages) / len(ages), 4),
        "share_over_120s": round(sum(a > 120 for a in ages) / len(ages), 4),
        "_ages": ages,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--gap", type=float, default=15.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    results = []
    for i in range(args.samples):
        tick = time.time()
        results.append(sample(args.base))
        if i < args.samples - 1:
            time.sleep(max(0.0, args.gap - (time.time() - tick)))

    pooled = sorted(a for r in results for a in r.get("_ages", []))
    summary = {
        "measurement": "G: bus position age at server response (now - RecordedAtTime)",
        "base": args.base,
        "measured_utc": [r.get("at_utc") for r in results],
        "method": "GET /api/buses x%d, %gs apart; now = local clock at first byte; t = wire key t (ms)"
                  % (args.samples, args.gap),
        "samples": [{k: v for k, v in r.items() if k != "_ages"} for r in results],
        "pooled": {
            "fixes": len(pooled),
            "min": round(pooled[0], 1),
            **{f"p{p}": round(percentile(pooled, p), 1) for p in PERCENTILES},
            "max": round(pooled[-1], 1),
            "mean": round(sum(pooled) / len(pooled), 1),
        } if pooled else {"fixes": 0, "note": "/api/buses returned no vehicles"},
        "histogram_10s_bins": {},
    }
    for age in pooled:
        key = f"{int(age // 10) * 10:03d}-{int(age // 10) * 10 + 10:03d}s" if age < 300 else "300s+"
        summary["histogram_10s_bins"][key] = summary["histogram_10s_bins"].get(key, 0) + 1
    summary["histogram_10s_bins"] = dict(sorted(summary["histogram_10s_bins"].items()))
    with open(args.out, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps({"pooled": summary["pooled"], "vehicles": [r.get("vehicles") for r in results]}))


if __name__ == "__main__":
    main()
