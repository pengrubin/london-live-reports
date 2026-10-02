#!/usr/bin/env python3
"""Measurement C: memory coefficients from the production /health samples.

    python3 fit_memory.py --samples ~/bus-archive/health-samples.jsonl --out ../data

Ordinary least squares of heapUsedMB and rssMB on the component counters that
/health reports. Restarts are where `up` decreases; the first 30 minutes after
each restart are excluded. The PRIMARY window is the longest single uptime
segment (one process, one build), because the code changed between restarts
and a coefficient fitted across builds would describe neither.

Outputs: memory-fit.json, memory-fit.png
"""

import argparse
import json
import os
from datetime import datetime, timezone

import numpy as np

WARMUP_EXCLUDED_S = 30 * 60
SAMPLE_INTERVAL_S = 300
MODELS = {
    "M0 intercept only": [],
    "M1 vehicleStates": ["vehicleStates"],
    "M2 lbLastFixes": ["lbLastFixes"],
    "M3 lbVehicleTotals": ["lbVehicleTotals"],
    "M4 vehicleStates + lbVehicleTotals": ["vehicleStates", "lbVehicleTotals"],
    "M5 vehicleStates + lbVehicleTotals + uptimeDays": ["vehicleStates", "lbVehicleTotals", "uptimeDays"],
    "M6 M5 + events + eventMembers + eventPassages":
        ["vehicleStates", "lbVehicleTotals", "uptimeDays", "events", "eventMembers", "eventPassages"],
    "M7 M5 + eventMembers + per-id caches":
        ["vehicleStates", "lbVehicleTotals", "uptimeDays", "eventMembers", "cacheVehicleArrivals",
         "cacheStopArrivals", "cacheStopDetail"],
    "M8 everything that varies":
        ["vehicleStates", "lbLastFixes", "lbVehicleTotals", "uptimeDays", "routeIndexes", "shapeGates",
         "events", "eventMembers", "eventPassages", "cacheVehicleArrivals", "cacheStopArrivals",
         "cacheStopDetail", "cacheCrowding", "cacheBikePoints"],
}
CORRELATION_VARS = ["vehicleStates", "lbLastFixes", "lbVehicleTotals", "uptimeDays", "events",
                    "eventMembers", "eventPassages", "cacheVehicleArrivals", "cacheStopArrivals"]


def iso(epoch_s):
    return datetime.fromtimestamp(epoch_s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") == 200 and "mem" in row and "comp" in row:
                rows.append(row)
    return rows


def segments(rows):
    """Split at restarts (uptime decreases). Returns list of lists."""
    out, current = [], [rows[0]]
    for prev, row in zip(rows, rows[1:]):
        if row["up"] < prev["up"]:
            out.append(current)
            current = []
        current.append(row)
    out.append(current)
    return out


def column(rows, name):
    if name == "uptimeDays":
        return np.array([r["up"] / 86400 for r in rows], dtype=float)
    return np.array([r["comp"].get(name, 0) for r in rows], dtype=float)


def ols(rows, target, regressors):
    y = np.array([r["mem"][target] for r in rows], dtype=float)
    kept = [name for name in regressors if np.ptp(column(rows, name)) > 0]
    dropped = [name for name in regressors if name not in kept]
    X = np.column_stack([np.ones(len(rows))] + [column(rows, name) for name in kept])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    resid = y - fitted
    n, p = X.shape
    dof = max(n - p, 1)
    sigma2 = float(resid @ resid) / dof
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0
    cov = sigma2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    # Conditioning of the standardised design (intercept removed): how far the
    # regressors are from being separately identifiable.
    condition = None
    vif = {}
    if kept:
        Z = X[:, 1:]
        Z = (Z - Z.mean(axis=0)) / Z.std(axis=0)
        condition = float(np.linalg.cond(Z))
        if len(kept) > 1:
            corr = np.corrcoef(Z, rowvar=False)
            inv = np.linalg.pinv(corr)
            vif = {name: round(float(inv[i, i]), 1) for i, name in enumerate(kept)}
    lag1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if n > 2 else None
    # Serial correlation shrinks the information in n samples; AR(1) approximation.
    n_eff = int(n * (1 - lag1) / (1 + lag1)) if lag1 is not None and lag1 < 1 else None
    names = ["intercept"] + kept
    return {
        "target": target,
        "regressors": kept,
        "dropped_constant_regressors": dropped,
        "n": n,
        "coefficients": {
            name: {
                "value": float(b),
                "std_error_iid": float(s),
                "unit": "MB" if name == "intercept" else ("MB per day" if name == "uptimeDays" else "MB per item"),
                **({"kb_per_item": round(float(b) * 1024, 4)} if name not in ("intercept", "uptimeDays") else {}),
            }
            for name, b, s in zip(names, beta, se)
        },
        "r2": round(r2, 4),
        "adjusted_r2": round(1 - (1 - r2) * (n - 1) / dof, 4),
        "residual_sd_mb": round(float(np.sqrt(sigma2)), 2),
        "residual_lag1_autocorrelation": round(lag1, 3) if lag1 is not None else None,
        "effective_n_ar1": n_eff,
        "design_condition_number": round(condition, 1) if condition else None,
        "vif": vif,
        "_fitted": fitted,
    }


def describe(rows, name, getter):
    values = np.array([getter(r) for r in rows], dtype=float)
    return {"min": float(values.min()), "p05": float(np.percentile(values, 5)),
            "median": float(np.median(values)), "p95": float(np.percentile(values, 95)),
            "max": float(values.max()), "mean": round(float(values.mean()), 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    rows = load(os.path.expanduser(args.samples))
    segs = segments(rows)
    trimmed = [[r for r in seg if r["up"] >= WARMUP_EXCLUDED_S] for seg in segs]
    primary = max(trimmed, key=len)
    pooled = [r for seg in trimmed for r in seg]

    result = {
        "measurement": "C: memory vs component counters (OLS)",
        "computed_on": "2026-09-29",
        "source": args.samples,
        "method": "OLS (numpy lstsq) of heapUsedMB and rssMB on /health component counters; restarts = "
                  "uptime decreases; first 30 min after each restart excluded; primary window = longest "
                  "single-process uptime segment. Standard errors assume independent samples and are "
                  "therefore too small: see residual_lag1_autocorrelation and effective_n_ar1.",
        "all_samples": {"ok_samples": len(rows), "from": iso(rows[0]["at"]), "to": iso(rows[-1]["at"]),
                        "restarts": len(segs) - 1,
                        "restart_times_utc": [iso(seg[0]["at"]) for seg in segs[1:]]},
        "primary_window": {
            "from": iso(primary[0]["at"]), "to": iso(primary[-1]["at"]), "n": len(primary),
            "uptime_at_end_days": round(primary[-1]["up"] / 86400, 2),
            "sample_interval_s": SAMPLE_INTERVAL_S,
            "gaps_over_10min": int(sum(1 for a, b in zip(primary, primary[1:]) if b["at"] - a["at"] > 600)),
        },
        "ranges_primary_window": {
            **{f"mem.{k}": describe(primary, k, lambda r, k=k: r["mem"][k])
               for k in ("rssMB", "heapUsedMB", "heapTotalMB", "externalMB")},
            **{f"comp.{k}": describe(primary, k, lambda r, k=k: r["comp"].get(k, 0))
               for k in ("vehicleStates", "lbLastFixes", "lbVehicleTotals", "routeIndexes", "shapeGates",
                         "events", "eventMembers", "eventPassages", "cacheArrivals", "cacheStopArrivals",
                         "cacheVehicleArrivals", "cacheStopDetail", "cacheCrowding")},
        },
        "fits_primary_window": {},
        "fits_pooled_all_segments": {},
    }

    corr_matrix = np.corrcoef(np.column_stack([column(primary, v) for v in CORRELATION_VARS]), rowvar=False)
    result["correlation_primary_window"] = {
        a: {b: round(float(corr_matrix[i, j]), 3) for j, b in enumerate(CORRELATION_VARS)}
        for i, a in enumerate(CORRELATION_VARS)
    }

    fitted_for_plot = {}
    for target in ("heapUsedMB", "rssMB"):
        result["fits_primary_window"][target] = {}
        result["fits_pooled_all_segments"][target] = {}
        for label, regressors in MODELS.items():
            fit = ols(primary, target, regressors)
            if label.startswith("M5"):
                fitted_for_plot[target] = fit["_fitted"]
            fit.pop("_fitted")
            result["fits_primary_window"][target][label] = fit
            if label.startswith(("M1", "M4", "M5")):
                pooled_fit = ols(pooled, target, regressors)
                pooled_fit.pop("_fitted")
                result["fits_pooled_all_segments"][target][label] = pooled_fit
    result["pooled_window"] = {"n": len(pooled), "segments_used": sum(1 for s in trimmed if s),
                               "note": "spans several builds; coefficients are not comparable to the primary window"}

    # Day-level view: what the daily cycle alone explains, by hour of day (UTC).
    hours = np.array([datetime.fromtimestamp(r["at"], timezone.utc).hour for r in primary])
    result["by_hour_utc_primary_window"] = {
        f"{h:02d}": {
            "vehicleStates_median": float(np.median(column(primary, "vehicleStates")[hours == h])),
            "heapUsedMB_median": float(np.median(np.array([r["mem"]["heapUsedMB"] for r in primary])[hours == h])),
            "rssMB_median": float(np.median(np.array([r["mem"]["rssMB"] for r in primary])[hours == h])),
        }
        for h in range(24) if (hours == h).any()
    }

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "memory-fit.json"), "w") as fh:
        json.dump(result, fh, indent=2)

    plot(primary, fitted_for_plot, os.path.join(args.out, "memory-fit.png"), result)
    summary = {t: {m: (f["r2"], f["residual_sd_mb"]) for m, f in result["fits_primary_window"][t].items()}
               for t in result["fits_primary_window"]}
    print(json.dumps({"primary_window": result["primary_window"], "r2_and_resid_sd": summary}, indent=1))


def plot(primary, fitted, path, result):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    surface, ink, secondary, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e6e5e0"
    measured_colour, fitted_colour = "#2a78d6", "#d9622b"  # validated pair (validate_palette.js)
    times = [datetime.fromtimestamp(r["at"], timezone.utc) for r in primary]
    vehicles = column(primary, "vehicleStates")

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), facecolor=surface,
                             gridspec_kw={"width_ratios": [2.1, 1]})
    for row, target, label in ((0, "heapUsedMB", "Heap used"), (1, "rssMB", "Resident set size")):
        y = np.array([r["mem"][target] for r in primary], dtype=float)
        fit = result["fits_primary_window"][target]["M5 vehicleStates + lbVehicleTotals + uptimeDays"]
        ax = axes[row][0]
        # Break both lines where the sampler was down, so a gap is not drawn as a trend.
        gap = np.array([False] + [b["at"] - a["at"] > 900 for a, b in zip(primary, primary[1:])])
        measured = np.where(gap, np.nan, y)
        modelled = np.where(gap, np.nan, fitted[target])
        ax.plot(times, measured, color=measured_colour, linewidth=0.8, label="measured (5 min samples)")
        ax.plot(times, modelled, color=fitted_colour, linewidth=1.4, label="fitted, model M5")
        ax.set_title(f"{label}, MB: measured against fitted\nR² {fit['r2']:.2f}, residual sd "
                     f"{fit['residual_sd_mb']:.0f} MB; gaps are sampler outages", loc="left", color=ink,
                     fontsize=11)
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.legend(frameon=False, fontsize=9, loc="upper left", labelcolor=secondary)

        scatter = axes[row][1]
        scatter.scatter(vehicles, y, s=5, color=measured_colour, alpha=0.35, linewidths=0)
        single = result["fits_primary_window"][target]["M1 vehicleStates"]
        xs = np.array([vehicles.min(), vehicles.max()])
        slope = single["coefficients"]["vehicleStates"]["value"]
        scatter.plot(xs, single["coefficients"]["intercept"]["value"] + slope * xs,
                     color=fitted_colour, linewidth=1.6)
        scatter.set_title(f"{label} by tracked vehicles\n{slope * 1024:+.1f} KB per vehicle, "
                          f"R² {single['r2']:.2f}", loc="left", color=ink, fontsize=11)
        scatter.set_xlabel("vehicleStates (diversion detector)", color=secondary, fontsize=9)
    for ax in axes.flat:
        ax.set_facecolor(surface)
        ax.grid(True, color=grid, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(colors=muted, labelsize=9)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(grid)
    window = result["primary_window"]
    fig.suptitle(f"london.pengrubin.com memory, one process: {window['from'][:10]} to {window['to'][:10]} "
                 f"(n = {window['n']}, first 30 min after restart excluded)",
                 x=0.01, ha="left", color=ink, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=150, facecolor=surface)


if __name__ == "__main__":
    main()
