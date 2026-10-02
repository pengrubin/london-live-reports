#!/usr/bin/env python3
"""Measurement D: attribute the local run's CPU profile to pipeline stages.

    python3 analyze_cpuprofile.py --run ~/london-live-worktrees/measure/tmp/profile-run \
        --out ../data/cpu-profile-summary.json

Inputs, all produced by run-local-profile.sh:
    cpuprofile/*.cpuprofile   V8 sampling profile of the MAIN thread (node --cpu-prof)
    proc-metrics.jsonl        process.cpuUsage()/memoryUsage() every 30 s + upstream request counters
    health.jsonl              the backend's own /health every 30 s
    viewer-requests.jsonl     what the synthetic viewer received
    phases.json               warm-up / quiet / viewer boundaries (wall clock)
    server.log                only the "BODS poll: N vehicles, parse M ms" lines are read

ATTRIBUTION RULE. Every sample is a call stack. Walking from the leaf towards
the root, the first frame that belongs to a stage-owning project file names the
stage ("deepest owner wins"); shared helpers (geometry, cache, fetch wrappers)
are skipped so their time goes to whoever called them. Stacks with no project
frame are classified by library (undici, fastify, node internals). V8 does not
record async callers, so work that resumes after an `await` inside a library
(JSON parsing of a response body, for instance) cannot be tied to the stage
that asked for it: it is reported under the library bucket, not guessed.

The profile covers the main thread only. Brotli/gzip, file writes, DNS and
TLS session work run on libuv's thread pool; their cost is the difference
between process.cpuUsage() and the profile's busy time, reported as
`off_main_thread`.
"""

import argparse
import glob
import json
import os
import re
import statistics
from collections import defaultdict

BUS_POLL_S = 15

# file (suffix match on the URL) -> stage. Order matters only for readability.
OWNERS = [
    ("backend/src/trace-writer.ts", "trace writer"),
    ("backend/src/diversion-detector.ts", "diversion detector"),
    ("backend/src/diversion-events.ts", "diversion detector"),
    ("backend/src/route-projection.ts", "diversion detector"),
    ("backend/src/bods-client.ts", "BODS parse + vehicle table"),
    ("backend/src/leaderboard.ts", "leaderboard sampling"),
    ("backend/src/shared/position-inference.ts", "leaderboard sampling"),
    ("backend/src/shared/nr-inference.ts", "leaderboard sampling"),
    ("backend/src/nr-sampler.ts", "leaderboard sampling"),
    ("backend/src/status-recorder.ts", "status + disruption shaping"),
    ("backend/src/disruptions/", "status + disruption shaping"),
    ("backend/src/routes/disruptions.ts", "status + disruption shaping"),
    ("backend/src/routes/bus-stop-closures.ts", "status + disruption shaping"),
    ("backend/src/ais-client.ts", "AIS stream"),
    ("backend/src/ea-tides.ts", "tide gauges"),
    ("backend/src/coverage-writer.ts", "daily batch (coverage, rollups)"),
    ("backend/src/rollup-writer.ts", "daily batch (coverage, rollups)"),
    ("backend/src/routes/", "serve: routes, serialise, compress (main thread)"),
    ("scripts/preload-metrics.mjs", "measurement overhead (preload)"),
]
# Helpers whose time belongs to their caller.
PASS_THROUGH = ("backend/src/shared/geometry.ts", "backend/src/cache.ts", "backend/src/rate-budget.ts",
                "backend/src/tfl-client.ts", "backend/src/darwin-client.ts", "backend/src/crash-guard.ts",
                "backend/src/shared/london-date.ts", "backend/src/region.ts", "backend/src/config.ts",
                "backend/src/shared/types.ts")
SERVE = "serve: routes, serialise, compress (main thread)"
UPSTREAM_JSON = "upstream body: JSON.parse (TfL, Darwin, EA)"
UPSTREAM_TEXT = "upstream body: UTF-8 decode to string (BODS XML)"
UPSTREAM_OTHER = "upstream fetch: undici client"
NODE_IO = "node I/O glue: TLS, sockets, streams, zlib bindings"


def owner_of(url):
    for suffix, stage in OWNERS:
        if suffix in url:
            return stage
    return None


def classify(stack):
    """stack: list of (functionName, url) from leaf to root."""
    leaf_name, leaf_url = stack[0]
    if leaf_name == "(idle)":
        return "idle"
    if leaf_name == "(garbage collector)":
        return "GC"
    if leaf_name == "(program)":
        return "(program): native code outside JS"
    for name, url in stack:
        if any(helper in url for helper in PASS_THROUGH):
            continue
        stage = owner_of(url)
        if stage:
            return stage
    urls = [url for _, url in stack]
    names = [name for name, _ in stack]
    in_undici = any("undici" in url for url in urls)
    if in_undici:
        if any(n in ("parse", "parseJSONFromBytes") for n in names[:4]):
            return UPSTREAM_JSON
        if any(n in ("utf8DecodeBytes", "decode", "utf8Slice", "latin1Slice") for n in names[:4]):
            return UPSTREAM_TEXT
        return UPSTREAM_OTHER
    if any("/fastify/" in url or "/@fastify/" in url or "fast-json-stringify" in url
           or "/light-my-request/" in url or "/find-my-way/" in url for url in urls):
        return SERVE
    if any("/pino" in url or "sonic-boom" in url or "thread-stream" in url for url in urls):
        return "logging (pino)"
    if any("/tsx/" in url or "esbuild" in url or url.startswith("node:internal/modules") for url in urls):
        return "module loading (tsx, startup)"
    if any(url.startswith("node:") for url in urls):
        return NODE_IO
    return "other / unattributed"


def short(url):
    if "/backend/src/" in url:
        return "backend/src/" + url.split("/backend/src/", 1)[1]
    if "/node_modules/" in url:
        return "node_modules/" + url.rsplit("/node_modules/", 1)[1]
    if "/scripts/" in url and url.startswith("file://"):
        return "scripts/" + url.rsplit("/scripts/", 1)[1]
    return url


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def control_run(run):
    """Process CPU of the identical setup with no profiler attached (quiet phase only)."""
    phases = json.load(open(os.path.join(run, "phases.json")))
    start, end = phases["quiet"]
    proc = [r for r in load_jsonl(os.path.join(run, "proc-metrics.jsonl"))
            if r.get("kind") == "proc" and start - 1000 <= r["at"] <= end + 1000]
    health = [h for h in load_jsonl(os.path.join(run, "health.jsonl")) if h["at"] >= start]
    first, last = proc[0], proc[-1]
    wall_s = (last["at"] - first["at"]) / 1000
    user_ms = (last["cpuUserUs"] - first["cpuUserUs"]) / 1000
    system_ms = (last["cpuSystemUs"] - first["cpuSystemUs"]) / 1000
    vehicles = [h["components"].get("lbLastFixes") for h in health if h["components"].get("lbLastFixes")]
    return {
        "what": "same worktree, seed, port and preload; node WITHOUT --cpu-prof; pollers only, no viewer",
        "environment": open(os.path.join(run, "environment.txt")).read().strip().replace("\n", "; "),
        "window_utc_ms": [first["at"], last["at"]],
        "wall_seconds": round(wall_s, 1),
        "process_cpu_ms_per_15s": round((user_ms + system_ms) / (wall_s / BUS_POLL_S), 1),
        "user_ms_per_15s": round(user_ms / (wall_s / BUS_POLL_S), 1),
        "system_ms_per_15s": round(system_ms / (wall_s / BUS_POLL_S), 1),
        "process_cpu_utilisation_of_one_core": round((user_ms + system_ms) / (wall_s * 1000), 4),
        "rss_mb_peak_health": max((h["memory"]["rssMB"] for h in health), default=None),
        "heap_used_mb_peak_health": max((h["memory"]["heapUsedMB"] for h in health), default=None),
        "heap_used_mb_median_health": statistics.median([h["memory"]["heapUsedMB"] for h in health] or [0]),
        "lbLastFixes_median": statistics.median(vehicles) if vehicles else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--control", default="", help="a PROFILE=0 run directory (no profiler attached)")
    parser.add_argument("--persist", default="", help="the run's PERSIST_DIR, to size what it wrote")
    args = parser.parse_args()
    run = os.path.expanduser(args.run)

    profile_path = sorted(glob.glob(os.path.join(run, "cpuprofile", "*.cpuprofile")))[-1]
    with open(profile_path) as fh:
        profile = json.load(fh)
    control = None
    if args.control:
        control = control_run(os.path.expanduser(args.control))
    nodes = {node["id"]: node for node in profile["nodes"]}
    parent = {}
    for node in profile["nodes"]:
        for child in node.get("children", []):
            parent[child] = node["id"]

    stage_of, leaf_label = {}, {}
    for node_id, node in nodes.items():
        stack, cursor = [], node_id
        while cursor is not None:
            frame = nodes[cursor]["callFrame"]
            stack.append((frame.get("functionName") or "(anonymous)", frame.get("url", "")))
            cursor = parent.get(cursor)
        stage_of[node_id] = classify(stack)
        frame = node["callFrame"]
        leaf_label[node_id] = (f"{frame.get('functionName') or '(anonymous)'}  "
                               f"[{short(frame.get('url', '')) or 'native'}:{frame.get('lineNumber', -1) + 1}]")

    phases = json.load(open(os.path.join(run, "phases.json")))
    proc = [r for r in load_jsonl(os.path.join(run, "proc-metrics.jsonl")) if r.get("kind") == "proc"]
    upstream_rows = [r for r in load_jsonl(os.path.join(run, "proc-metrics.jsonl")) if r.get("kind") == "upstream"]
    health = load_jsonl(os.path.join(run, "health.jsonl"))
    viewer = load_jsonl(os.path.join(run, "viewer-requests.jsonl"))

    # Wall-clock alignment: the profile's clock is monotonic microseconds. The
    # preload's last sample is written in the process 'exit' handler, within
    # milliseconds of the profile's endTime, so the two ends are tied together.
    wall_end_ms = proc[-1]["at"]
    profile_end_us = profile["endTime"]

    def wall_ms(ts_us):
        return wall_end_ms - (profile_end_us - ts_us) / 1000

    windows = {
        "quiet (pipeline only, no viewer)": phases["quiet"],
        "viewer (pipeline + one synthetic viewer)": phases["viewer"],
    }
    per_window = {name: defaultdict(float) for name in windows}
    self_time = {name: defaultdict(float) for name in windows}
    stage_functions = {name: defaultdict(lambda: defaultdict(float)) for name in windows}

    cursor_us = profile["startTime"]
    for node_id, delta in zip(profile["samples"], profile["timeDeltas"]):
        cursor_us += delta
        at = wall_ms(cursor_us)
        for name, (start, end) in windows.items():
            if start <= at < end:
                stage = stage_of[node_id]
                per_window[name][stage] += delta / 1000
                self_time[name][leaf_label[node_id]] += delta / 1000
                stage_functions[name][stage][leaf_label[node_id]] += delta / 1000

    def process_cpu_ms(start, end):
        inside = [r for r in proc if start - 1000 <= r["at"] <= end + 1000]
        if len(inside) < 2:
            return None, None
        first, last = inside[0], inside[-1]
        cpu = (last["cpuUserUs"] + last["cpuSystemUs"] - first["cpuUserUs"] - first["cpuSystemUs"]) / 1000
        return cpu, (last["at"] - first["at"]) / 1000

    summary_windows = {}
    for name, (start, end) in windows.items():
        wall_s = (end - start) / 1000
        polls = wall_s / BUS_POLL_S
        stages = per_window[name]
        sampled_ms = sum(stages.values())
        busy_ms = sampled_ms - stages.get("idle", 0.0)
        cpu_ms, cpu_wall_s = process_cpu_ms(start, end)
        process_per_poll = cpu_ms / (cpu_wall_s / BUS_POLL_S) if cpu_ms else None
        table = []
        for stage, ms in sorted(stages.items(), key=lambda kv: -kv[1]):
            top = sorted(stage_functions[name][stage].items(), key=lambda kv: -kv[1])[:5]
            table.append({
                "stage": stage,
                "cpu_ms_total": round(ms, 1),
                "cpu_ms_per_15s_bus_poll": round(ms / polls, 2),
                "share_of_main_thread_busy": None if stage == "idle" else round(ms / busy_ms, 4),
                "top_functions_ms_per_15s": [{"fn": fn, "ms": round(v / polls, 2)} for fn, v in top],
            })
        summary_windows[name] = {
            "wall_seconds": round(wall_s, 1),
            "bus_polls_in_window": round(polls, 1),
            "profile_samples_ms": round(sampled_ms, 1),
            "profile_coverage_of_wall": round(sampled_ms / (wall_s * 1000), 4),
            "main_thread_busy_ms_per_15s": round(busy_ms / polls, 1),
            "main_thread_utilisation": round(busy_ms / (wall_s * 1000), 4),
            "process_cpu_ms_per_15s (user+system, all threads)":
                round(process_per_poll, 1) if process_per_poll else None,
            "process_cpu_utilisation_of_one_core":
                round(cpu_ms / (cpu_wall_s * 1000), 4) if cpu_ms else None,
            "off_main_thread_ms_per_15s (process minus profile busy)":
                round(process_per_poll - busy_ms / polls, 1) if process_per_poll else None,
            "stages": table,
            "top_self_time_functions": [
                {"fn": fn, "ms_per_15s": round(ms / polls, 2)}
                for fn, ms in sorted(self_time[name].items(), key=lambda kv: -kv[1])[:30]
                if not fn.startswith("(idle)")
            ],
        }

    # What the pipeline itself logged about each bus poll.
    poll_lines = []
    log_path = os.path.join(run, "server.log")
    if os.path.exists(log_path):
        pattern = re.compile(r'"time":(\d+).*?BODS poll: (\d+) vehicles, parse (\d+) ms')
        with open(log_path, errors="replace") as fh:
            for line in fh:
                match = pattern.search(line)
                if match:
                    poll_lines.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    measured = [p for p in poll_lines if p[0] >= phases["quiet"][0]]
    intervals = [(b[0] - a[0]) / 1000 for a, b in zip(measured, measured[1:])]

    def normalise(key):
        key = re.sub(r"GetDepBoardWithDetails/[A-Z]{3}", "GetDepBoardWithDetails/{crs}", key)
        key = re.sub(r"/stations/[^/]+/readings", "/stations/{ref}/readings", key)
        return re.sub(r"/Status/\d{4}-\d{2}-\d{2}/to/\d{4}-\d{2}-\d{2}", "/Status/{from}/to/{to}", key)

    def upstream_table_for(start, end):
        """Counters are flushed every 30 s, so a window is resolved to +/- 30 s."""
        totals = defaultdict(lambda: {"requests": 0, "completed": 0, "wire_bytes": 0,
                                      "status": defaultdict(int)})
        for row in upstream_rows:
            if not start < row["at"] <= end + 1000:
                continue
            for key, agg in row["byKey"].items():
                target = totals[normalise(key)]
                target["requests"] += agg["requests"]
                target["completed"] += agg["completed"]
                target["wire_bytes"] += agg["wireBytes"]
                for status, n in agg["status"].items():
                    target["status"][status] += n
        seconds = (end - start) / 1000
        table = []
        for key, agg in sorted(totals.items(), key=lambda kv: -kv[1]["wire_bytes"]):
            table.append({
                "upstream": key, "requests": agg["requests"], "completed": agg["completed"],
                "status_counts": dict(agg["status"]),
                "mean_interval_s": round(seconds / agg["requests"], 1) if agg["requests"] else None,
                "wire_bytes_total": agg["wire_bytes"],
                "wire_bytes_per_completed_request":
                    round(agg["wire_bytes"] / agg["completed"]) if agg["completed"] else None,
                "wire_bytes_per_second": round(agg["wire_bytes"] / seconds, 1),
            })
        return {"observed_seconds": round(seconds), "by_upstream": table}

    upstream_by_phase = {name: upstream_table_for(start, end) for name, (start, end) in windows.items()}

    viewer_by_path = defaultdict(list)
    for row in viewer:
        viewer_by_path[row["path"]].append(row)
    viewer_table = [{
        "path": path, "requests": len(rows),
        "status_counts": {str(s): sum(1 for r in rows if r.get("status") == s) for s in {r.get("status") for r in rows}},
        "br_wire_bytes_median": statistics.median([r["wireBytes"] for r in rows if r.get("status") == 200] or [0]),
        "ms_median": statistics.median([r["ms"] for r in rows if "ms" in r] or [0]),
        "x_cache": {str(s): sum(1 for r in rows if r.get("xCache") == s) for s in {r.get("xCache") for r in rows}},
    } for path, rows in sorted(viewer_by_path.items())]

    written = {}
    if args.persist:
        persist = os.path.expanduser(args.persist)
        run_seconds = (phases["viewer"][1] - phases["startedAt"]) / 1000
        for folder in ("bus-traces", "diversions", "tube-status", "road-disruptions"):
            for path in glob.glob(os.path.join(persist, folder, "*.jsonl")):
                size = os.path.getsize(path)
                with open(path, "rb") as fh:
                    lines = sum(1 for _ in fh)
                written[folder] = {
                    "bytes": size, "lines": lines, "run_seconds": round(run_seconds),
                    "bytes_per_line": round(size / lines, 1) if lines else None,
                    "lines_per_second": round(lines / run_seconds, 2),
                    "bytes_per_second": round(size / run_seconds, 1),
                }
        for name in ("leaderboard.json", os.path.join("coverage", "latest.json")):
            path = os.path.join(persist, name)
            if os.path.exists(path):
                written[name] = {"bytes": os.path.getsize(path),
                                 "note": "rewritten in place, not appended"}
        if "bus-traces" in written and poll_lines:
            all_polls = len(poll_lines)
            written["bus-traces"]["polls_in_run"] = all_polls
            written["bus-traces"]["new_fixes_per_poll"] = round(written["bus-traces"]["lines"] / all_polls, 1)
            written["bus-traces"]["new_fixes_per_vehicle_per_poll"] = round(
                written["bus-traces"]["lines"] / all_polls / statistics.median([p[1] for p in poll_lines]), 3)

    measured_health = [h for h in health if h["at"] >= phases["quiet"][0]]
    result = {
        "measurement": "D: CPU by stage, local run",
        "measured_on": "2026-09-29",
        "run_window_utc_ms": {"start": phases["startedAt"], "end": phases["viewer"][1]},
        "environment": open(os.path.join(run, "environment.txt")).read().strip(),
        "method": "node --cpu-prof (V8 sampling profiler, main thread) on origin/main in a dedicated "
                  "worktree; 60 s warm-up excluded; then a quiet phase (pollers only) and a viewer "
                  "phase (one synthetic browser at the frontend's poll intervals, Accept-Encoding br). "
                  "process.cpuUsage() sampled every 30 s by a --import preload; no repository file "
                  "was edited.",
        "profiler_attached": True,
        "profile_sampling_interval_us": statistics.median(profile["timeDeltas"]),
        "windows": summary_windows,
        "bus_polls_logged": {
            "count_after_warmup": len(measured),
            "vehicles_median": statistics.median([p[1] for p in measured]) if measured else None,
            "vehicles_min": min((p[1] for p in measured), default=None),
            "vehicles_max": max((p[1] for p in measured), default=None),
            "logged_parse_ms_median": statistics.median([p[2] for p in measured]) if measured else None,
            "logged_parse_ms_p95": sorted(p[2] for p in measured)[int(0.95 * (len(measured) - 1))] if measured else None,
            "logged_parse_ms_max": max((p[2] for p in measured), default=None),
            "poll_interval_s_median": round(statistics.median(intervals), 2) if intervals else None,
            "note": "the logged 'parse' spans parseSiriVm + table build + wire array + trace sink + "
                    "diversion detector record(); it is wall time of one synchronous block",
        },
        "memory_during_run": {
            "samples": len(measured_health),
            "rss_mb_peak_health": max((h["memory"]["rssMB"] for h in measured_health), default=None),
            "rss_mb_median_health": statistics.median([h["memory"]["rssMB"] for h in measured_health] or [0]),
            "heap_used_mb_peak_health": max((h["memory"]["heapUsedMB"] for h in measured_health), default=None),
            "heap_used_mb_median_health": statistics.median([h["memory"]["heapUsedMB"] for h in measured_health] or [0]),
            "external_mb_peak_health": max((h["memory"]["externalMB"] for h in measured_health), default=None),
            "max_rss_mb_os_high_water": round(max(r["maxRssKb"] for r in proc) / 1024 / (1024 if max(r["maxRssKb"] for r in proc) > 50_000_000 else 1), 1),
            "components_at_end": measured_health[-1]["components"] if measured_health else None,
            "series": [{"t_s": round((h["at"] - phases["startedAt"]) / 1000), "phase": h["phase"],
                        "rssMB": h["memory"]["rssMB"], "heapUsedMB": h["memory"]["heapUsedMB"],
                        "externalMB": h["memory"]["externalMB"],
                        "vehicleStates": h["components"].get("vehicleStates")} for h in health],
        },
        "upstream_requests_by_phase": upstream_by_phase,
        "synthetic_viewer": viewer_table,
        "files_written_by_the_run": written,
        "control_run_without_profiler": control,
    }
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2)

    for name, window in summary_windows.items():
        print(f"\n== {name}: main thread {window['main_thread_utilisation']:.2%}, process "
              f"{window['process_cpu_utilisation_of_one_core']}")
        for row in window["stages"]:
            print(f"  {row['cpu_ms_per_15s_bus_poll']:9.2f} ms/15s  {row['stage']}")


if __name__ == "__main__":
    main()
