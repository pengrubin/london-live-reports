# London Live technical notes

How [london.pengrubin.com](https://london.pengrubin.com) is built, written for people who work with transport data. Application source: [pengrubin/london-live-2d](https://github.com/pengrubin/london-live-2d).

| # | Document | Read | Status |
|---|---|---|---|
| 1 | **Bus GPS processing**: route shapes learned from vehicle traces, on-map snapping with an along-route Kalman filter, diversion detection with an evidence-based lifecycle | [HTML](https://docs.london.pengrubin.com/bus-gps/report.html) · [PDF](https://docs.london.pengrubin.com/bus-gps/report.pdf) | v1, 29 Sep 2026 |
| 2 | **Architecture and stream-processing load**: six stages, per-stage rates and CPU/memory/storage as formulas in named parameters, dated calibration, scaling scenarios | [HTML](https://docs.london.pengrubin.com/architecture/report.html) · [PDF](https://docs.london.pengrubin.com/architecture/report.pdf) | v1, 1 Oct 2026 |
| 3 | **Train position inference from arrival predictions**: feed behaviour measured over four weekdays, baked geometry, identity resolution, the ratio model, display smoothing, National Rail, self-consistency validation | [HTML](https://docs.london.pengrubin.com/tube/report.html) · [PDF](https://docs.london.pengrubin.com/tube/report.pdf) | v1, 2 Oct 2026 |

## Layout

```
docs/            what GitHub Pages serves (index + rendered HTML/PDF per document)
01-bus-gps/
  report.template.qmd   the text; every number is a {{placeholder}}
  numbers.json          every measured number, written by the scripts
  render.py             fills the placeholders and runs `quarto render` (HTML + PDF)
  scripts/              one script per figure; scan-traces.py builds data/daily/
  figures/              generated figures (PNG + SVG)
  data/                 per-day statistics, event tables, case-study trace slices
  refs.bib              references
02-architecture/        same layout; data/ holds the calibration measurements (CSV/JSON), notes/ the inventories
02-tube/                same layout; data/arrivals-metrics.json from the recorded Arrivals samples, notes/ the rule catalogue and findings
```

## Reproducing document 1

Requirements: Python 3 with matplotlib, [Quarto](https://quarto.org) 1.10+, [tectonic](https://tectonic-typesetting.github.io) (or any TeX), Node 22 with `tsx` for the Kalman replay.

1. Inputs: daily bus-trace files (`bus-traces/YYYY-MM-DD.jsonl.gz`, lines `{"k","i","x","y","t"}`), daily rollups, the diversion transition log, TfL road-disruption snapshots and a learned-route snapshot, laid out as the London Live backend writes them. The 38 days used in v1 are the author's archive; the same files are produced by running the backend.
2. `python3 scripts/scan-traces.py <archive> data/daily <day>...` once per day of traces.
3. Run each `scripts/fig-*.py` (and `diversion-stats.py`, `tfl-match.py`, the `replay-kalman.ts` replay via `tsx`); each writes its figure and its numbers into `numbers.json`.
4. `python3 render.py` → `report.html` and `report.pdf`.

`data/learned/` (a 30 MB learned-route snapshot) and `data/coverage.geojson` are not committed; both are downloads from the running site (`/bus-routes/learned/<key>.json`, `/api/coverage`).

## Licence

Text and figures CC BY 4.0; scripts MIT. See `LICENSE`.

## Reproducing document 2

Requirements as above, plus `numpy` for the memory regression. The measurements in `02-architecture/data/` were taken with the scripts in `02-architecture/scripts/` (`measure_*.py`, `run-local-profile.sh`, `fit_memory.py`) against the production origin and a local replica of the backend; they need the backend's API keys and are not needed to rebuild the document. To rebuild from the recorded data: `python3 scripts/build-numbers.py`, then each `scripts/fig-*.py`, then `python3 render.py`.

## Reproducing document 3

Inputs: daily Arrivals sample files written by `arrivals-sampler.mjs` (one gzip member per 30 s poll, eleven fields). `python3 scripts/analyze-arrivals.py --branches <london-live-2d>/data/branches --out data <files>` builds `data/arrivals-metrics.json`; `python3 scripts/fig-arrivals.py` draws the figures; `python3 scripts/build-numbers.py` derives every number in the text; `python3 render.py` fills and renders. The four days used in v1 are the author's recording; the sampler is in the application repository's tooling.
