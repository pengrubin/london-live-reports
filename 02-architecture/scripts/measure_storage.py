#!/usr/bin/env python3
"""Measurement E: storage rates from the local archive.

    python3 measure_storage.py --out ../data/storage.csv

Sizes are file sizes as `ls -l` reports them (os.stat st_size). The archive is
the external volume when mounted, else ~/bus-archive. Bus traces are stored
gzipped in the archive but RAW on the server, so one day is decompressed to a
pipe (nothing is written) to count raw bytes and lines; per-day fix counts for
the other days come from that day's rollup (`totals.fixes`).

Only complete days are used: today's partial files are skipped.
"""

import argparse
import csv
import gzip
import json
import os
import statistics
from datetime import datetime, timezone

EXTERNAL = "/Volumes/大龟壳/bus-archive"
LOCAL = os.path.expanduser("~/bus-archive")
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
SECONDS_PER_DAY = 86_400

DATASETS = [
    # (directory, suffix, what one record is, how to count records)
    ("bus-traces", ".jsonl.gz", "GPS fix", "rollup"),
    ("bus-rollups", ".json", "route-direction", "rollup-routes"),
    ("diversions", ".jsonl", "transition line", "lines"),
    ("tube-status", ".jsonl", "snapshot line", "lines"),
    ("road-disruptions", ".jsonl", "snapshot line", "lines"),
    ("leaderboard", ".json", "vehicle total", "leaderboard"),
    ("route-snapshots", ".tar.gz", "learned route file", "none"),
    ("arrivals", ".jsonl.gz", "sampler line (local sampler, not server state)", "none"),
]


def day_files(root, directory, suffix):
    folder = os.path.join(root, directory)
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(suffix) and name[:10] < TODAY and name[4] == "-":
            out.append((name[:10], os.path.join(folder, name)))
    return out


def count_lines(path):
    with open(path, "rb") as fh:
        return sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1 << 20), b""))


def gunzip_count(path):
    raw_bytes = lines = 0
    with gzip.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            raw_bytes += len(chunk)
            lines += chunk.count(b"\n")
    return raw_bytes, lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--recent-days", type=int, default=7)
    args = parser.parse_args()
    root = EXTERNAL if os.path.isdir(EXTERNAL) else LOCAL
    source_note = "external volume" if root == EXTERNAL else "local ~/bus-archive (external volume not mounted)"

    rollup_totals = {}
    for day, path in day_files(root, "bus-rollups", ".json"):
        with open(path) as fh:
            doc = json.load(fh)
        rollup_totals[day] = {**doc.get("totals", {}), "route_entries": len(doc.get("routes", {}))}

    rows = []
    for directory, suffix, record_name, counter in DATASETS:
        files = day_files(root, directory, suffix)
        if not files:
            rows.append({"dataset": directory, "note": "no complete day files found"})
            continue
        sizes = {day: os.path.getsize(path) for day, path in files}
        recent = files[-args.recent_days:]
        recent_sizes = [sizes[day] for day, _ in recent]

        records_by_day = {}
        for day, path in recent:
            if counter == "rollup" and day in rollup_totals:
                records_by_day[day] = rollup_totals[day].get("fixes")
            elif counter == "rollup-routes" and day in rollup_totals:
                records_by_day[day] = rollup_totals[day]["route_entries"]
            elif counter == "lines":
                records_by_day[day] = count_lines(path)
            elif counter == "leaderboard":
                with open(path) as fh:
                    records_by_day[day] = len(json.load(fh).get("totals", []))
        per_record = [sizes[day] / n for day, n in records_by_day.items() if n]
        median_bytes = statistics.median(recent_sizes)
        median_records = statistics.median(records_by_day.values()) if records_by_day else None

        row = {
            "dataset": directory,
            "format_in_archive": suffix,
            "record": record_name,
            "measured_on": "2026-09-29",
            "source": source_note,
            "days_in_archive": len(files),
            "first_day": files[0][0],
            "last_day": files[-1][0],
            "window_days": len(recent),
            "window": f"{recent[0][0]}..{recent[-1][0]}",
            "bytes_per_day_median": int(median_bytes),
            "bytes_per_day_min": min(recent_sizes),
            "bytes_per_day_max": max(recent_sizes),
            "bytes_per_second_mean": round(statistics.mean(recent_sizes) / SECONDS_PER_DAY, 1),
            "records_per_day_median": int(median_records) if median_records else "",
            "bytes_per_record_median": round(statistics.median(per_record), 2) if per_record else "",
            "bytes_per_year_at_median": int(median_bytes * 365),
            "all_days_total_bytes": sum(sizes.values()),
            "note": "",
        }
        rows.append(row)

        if directory == "bus-traces":
            day, path = files[-1]
            raw_bytes, lines = gunzip_count(path)
            gz_bytes = sizes[day]
            rollup_fixes = rollup_totals.get(day, {}).get("fixes")
            rows.append({
                "dataset": "bus-traces (RAW jsonl, as on the server)",
                "format_in_archive": "decompressed to a pipe",
                "record": "GPS fix",
                "measured_on": "2026-09-29",
                "source": source_note,
                "days_in_archive": 1, "first_day": day, "last_day": day, "window_days": 1, "window": day,
                "bytes_per_day_median": raw_bytes,
                "bytes_per_day_min": raw_bytes, "bytes_per_day_max": raw_bytes,
                "bytes_per_second_mean": round(raw_bytes / SECONDS_PER_DAY, 1),
                "records_per_day_median": lines,
                "bytes_per_record_median": round(raw_bytes / lines, 2),
                "bytes_per_year_at_median": raw_bytes * 365,
                "all_days_total_bytes": raw_bytes,
                "note": f"gzip ratio {raw_bytes / gz_bytes:.2f}x; {gz_bytes / lines:.2f} gz bytes per fix; "
                        f"lines in file {lines} vs rollup totals.fixes {rollup_fixes}; "
                        f"vehicles {rollup_totals.get(day, {}).get('vehicles')}, "
                        f"journeys {rollup_totals.get(day, {}).get('journeys')}",
            })

    fields = ["dataset", "format_in_archive", "record", "measured_on", "source", "days_in_archive",
              "first_day", "last_day", "window_days", "window", "bytes_per_day_median", "bytes_per_day_min",
              "bytes_per_day_max", "bytes_per_second_mean", "records_per_day_median",
              "bytes_per_record_median", "bytes_per_year_at_median", "all_days_total_bytes", "note"]
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row.get("dataset"), row.get("bytes_per_day_median"), row.get("records_per_day_median"),
              row.get("bytes_per_record_median"), row.get("note"))


if __name__ == "__main__":
    main()
