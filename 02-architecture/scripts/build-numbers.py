#!/usr/bin/env python3
"""Assemble numbers.json for document 2 from the calibration outputs.

Day run (data/, 2026-09-30 12:40-13:13 UTC) is the primary calibration point;
the night run (data-night-2026-09-29/) is the second. Every key is a measured
value with its date; the document body quotes only these keys.
"""
import json, csv, os, sys
sys.path.insert(0, os.path.dirname(__file__)); from figstyle import put, DATA
ROOT = os.path.dirname(DATA); NIGHT = os.path.join(ROOT, 'data-night-2026-09-29')
rows = lambda p: list(csv.DictReader(open(p)))
f = lambda x: float(x) if x not in ('', None) else None

ep = {r['path']: r for r in rows(f'{DATA}/endpoints.csv')}
epn = {r['path']: r for r in rows(f'{NIGHT}/endpoints.csv')}
st = {r['stream']: r for r in rows(f'{DATA}/streams.csv')}
sto = {r['dataset']: r for r in rows(f'{DATA}/storage.csv')}
cpu = json.load(open(f'{DATA}/cpu-profile-summary.json')); cpun = json.load(open(f'{NIGHT}/cpu-profile-summary.json'))
mem = json.load(open(f'{DATA}/memory-fit.json'))
age = json.load(open(f'{DATA}/bus-age.json')); agen = json.load(open(f'{NIGHT}/bus-age.json'))
dub = {r['path']: r for r in rows(f'{DATA}/endpoints-dubai.csv')}

N = {}
# --- input streams (day)
bus = st['bus positions']; arr = st['train arrival predictions (no viewer)']; arrv = st['train arrival predictions (one viewer polling at 10 s)']
N.update(bus_poll_s=15, bus_wire_mb=round(f(bus['wire_bytes_per_poll'])/1e6, 2), bus_decoded_mb=round(f(bus['decoded_bytes_per_poll'])/1e6, 2),
         bus_records_per_poll=int(f(bus['records_per_poll'])), bus_records_per_s=round(f(bus['records_per_s'])), bus_decoded_gb_per_day=round(f(bus['decoded_bytes_per_day'])/1e9, 1), bus_wire_gb_per_day=round(f(bus['wire_bytes_per_day'])/1e9, 1),
         bus_live_day=cpu['bus_polls_logged']['vehicles_median'], bus_live_night=cpun['bus_polls_logged']['vehicles_median'], bus_records_night=8273,
         arrivals_wire_kb=round(f(arr['wire_bytes_per_poll'])/1e3), arrivals_decoded_mb=round(f(arr['decoded_bytes_per_poll'])/1e6, 1), arrivals_records=int(f(arr['records_per_poll'])),
         arrivals_fetch_interval_no_viewer_s=15, arrivals_fetch_interval_viewer_s=f(arrv['poll_interval_s']), arrivals_decoded_gb_per_day=round(f(arr['decoded_bytes_per_day'])/1e9, 1),
         nr_board_wire_kb=round(f(st['National Rail departure boards']['wire_bytes_per_poll'])/1e3), nr_boards_per_15s=1, nr_hubs=17,
         status_wire_kb=round(f(st['rail line status, 7-day window with detail']['wire_bytes_per_poll'])/1e3), status_decoded_kb=round(f(st['rail line status, 7-day window with detail']['decoded_bytes_per_poll'])/1e3), status_poll_s=120,
         road_wire_kb=round(f(st['road disruptions']['wire_bytes_per_poll'])/1e3), road_decoded_kb=round(f(st['road disruptions']['decoded_bytes_per_poll'])/1e3), road_records=int(f(st['road disruptions']['records_per_poll'])),
         closures_records=int(f(st['bus stop closures']['records_per_poll'])), vessels_live=int(f(st['vessel positions']['records_per_poll'])), aircraft_live=int(f(st['aircraft positions']['records_per_poll'])))
fw = cpu['files_written_by_the_run']['bus-traces']
N.update(new_fixes_per_poll_day=round(fw['new_fixes_per_poll']), new_fixes_per_vehicle_per_poll=fw['new_fixes_per_vehicle_per_poll'], new_fixes_per_s_day=round(fw['lines_per_second']))
# --- storage
tr = sto['bus-traces']; trr = sto['bus-traces (RAW jsonl, as on the server)']
N.update(trace_fixes_per_day=int(f(tr['records_per_day_median'])), trace_gz_mb_per_day=round(f(tr['bytes_per_day_median'])/1e6), trace_gz_bytes_per_fix=round(f(tr['bytes_per_record_median']), 1),
         trace_raw_mb_per_day=round(f(trr['bytes_per_day_median'])/1e6), trace_raw_bytes_per_fix=round(f(trr['bytes_per_record_median']), 1), trace_gzip_ratio=5.27,
         rollup_kb_per_day=round(f(sto['bus-rollups']['bytes_per_day_median'])/1e3), rollup_routes_per_day=int(f(sto['bus-rollups']['records_per_day_median'])),
         diversions_mb_per_day=round(f(sto['diversions']['bytes_per_day_median'])/1e6, 2), diversions_lines_per_day=int(f(sto['diversions']['records_per_day_median'])),
         status_mb_per_day=round(f(sto['tube-status']['bytes_per_day_median'])/1e6, 1), leaderboard_mb_per_day=round(f(sto['leaderboard']['bytes_per_day_median'])/1e6, 1), leaderboard_totals_per_day=int(f(sto['leaderboard']['records_per_day_median'])),
         learned_snapshot_mb=round(f(sto['route-snapshots']['bytes_per_day_median'])/1e6, 1), archive_days=int(tr['days_in_archive']))
# --- CPU (day run, profiler attached; control without)
q = cpu['windows']['quiet (pipeline only, no viewer)']; v = cpu['windows']['viewer (pipeline + one synthetic viewer)']
stage = lambda w, name: next((s['cpu_ms_per_15s_bus_poll'] for s in w['stages'] if s['stage'].startswith(name)), 0.0)
N.update(cpu_main_busy_ms_quiet=round(q['main_thread_busy_ms_per_15s'], 1), cpu_main_busy_ms_viewer=round(v['main_thread_busy_ms_per_15s'], 1),
         cpu_main_util_quiet_pct=round(100*q['main_thread_utilisation'], 2), cpu_process_ms_control=round(cpu['control_run_without_profiler']['process_cpu_ms_per_15s'], 1),
         cpu_process_util_control_pct=round(100*cpu['control_run_without_profiler']['process_cpu_utilisation_of_one_core'], 1),
         cpu_process_ms_control_night=round(cpun['control_run_without_profiler']['process_cpu_ms_per_15s'], 1), cpu_main_busy_ms_quiet_night=round(cpun['windows']['quiet (pipeline only, no viewer)']['main_thread_busy_ms_per_15s'], 1),
         cpu_ms_io_glue=round(stage(q, 'node I/O glue'), 1), cpu_ms_bods_parse=round(stage(q, 'BODS parse'), 1), cpu_ms_gc=round(stage(q, 'GC'), 1), cpu_ms_leaderboard=round(stage(q, 'leaderboard'), 1),
         cpu_ms_undici=round(stage(q, 'upstream fetch'), 1), cpu_ms_json_parse=round(stage(q, 'upstream body: JSON'), 1), cpu_ms_detector=round(stage(q, 'diversion'), 1), cpu_ms_trace=round(stage(q, 'trace'), 1),
         cpu_ms_serve_viewer=round(stage(v, 'serve'), 1), cpu_ms_gc_viewer=round(stage(v, 'GC'), 1), cpu_ms_io_glue_viewer=round(stage(v, 'node I/O glue'), 1), cpu_ms_json_parse_viewer=round(stage(v, 'upstream body: JSON'), 1),
         cpu_process_ms_viewer=round(v['process_cpu_ms_per_15s (user+system, all threads)'], 1), cpu_process_ms_quiet=round(q['process_cpu_ms_per_15s (user+system, all threads)'], 1),
         parse_ms_per_poll_day=cpu['bus_polls_logged']['logged_parse_ms_median'], parse_ms_per_poll_night=cpun['bus_polls_logged']['logged_parse_ms_median'],
         parse_us_per_element=round(1000*stage(q, 'BODS parse')/N['bus_records_per_poll'], 1), detector_us_per_bus=round(1000*stage(q, 'diversion')/N['bus_live_day'], 1))
# --- memory
fits = mem['fits_primary_window']['heapUsedMB']
# the two-regressor model (vehicle states + leaderboard totals): the kitchen-sink fit has a higher R² but collinear, sign-flipped coefficients
best = next(m for m in fits.values() if set(m['regressors']) == {'vehicleStates', 'lbVehicleTotals'})
rng = mem['ranges_primary_window']
N.update(heap_fit_model=[k for k, m in fits.items() if m is best][0], heap_fit_r2=round(best['r2'], 2), heap_fit_intercept_mb=round(best['coefficients']['intercept']['value']),
         heap_fit_kb_per_vehicle_state=round(best['coefficients'].get('vehicleStates', {}).get('kb_per_item', 0), 2), heap_fit_kb_per_lb_total=round(best['coefficients'].get('lbVehicleTotals', {}).get('kb_per_item', 0), 3),
         heap_fit_residual_sd_mb=best['residual_sd_mb'], heap_fit_n=best['n'], heap_fit_window_from=mem['primary_window']['from'][:10], heap_fit_window_to=mem['primary_window']['to'][:10],
         prod_heap_median_mb=rng['mem.heapUsedMB']['median'], prod_heap_p95_mb=rng['mem.heapUsedMB']['p95'], prod_rss_median_mb=rng['mem.rssMB']['median'], prod_rss_p95_mb=rng['mem.rssMB']['p95'],
         prod_external_median_mb=rng['mem.externalMB']['median'], vehicle_states_median=rng['comp.vehicleStates']['median'], vehicle_states_p95=rng['comp.vehicleStates']['p95'],
         local_heap_median_day_mb=cpu['memory_during_run']['heap_used_mb_median_health'], local_heap_median_night_mb=cpun['memory_during_run']['heap_used_mb_median_health'],
         local_rss_median_day_mb=cpu['memory_during_run']['rss_mb_median_health'], local_rss_peak_day_mb=cpu['memory_during_run']['rss_mb_peak_health'],
         local_vehicle_states_day=cpu['memory_during_run']['components_at_end']['vehicleStates'], local_vehicle_states_night=cpun['memory_during_run']['components_at_end']['vehicleStates'])
# --- endpoints (day) and night
def e(path, key, src=ep): return f(src[path][key]) if path in src else None
for name, path in [('buses', '/api/buses'), ('arrivals', '/api/arrivals'), ('vessels', '/api/vessels'), ('aircraft', '/api/aircraft'), ('diversions', '/api/diversions'), ('coverage', '/api/coverage'), ('leaderboard', '/api/leaderboard'), ('disruptions', '/api/disruptions'), ('road', '/api/road-disruptions'), ('closures', '/api/bus-stop-closures'), ('bikes', '/api/bikes'), ('tide', '/api/tide-gauges')]:
    if path in ep:
        N[f'ep_{name}_raw_kb'] = round(e(path, 'raw_bytes_median')/1e3, 1); N[f'ep_{name}_br_kb'] = round((e(path, 'br_wire_bytes_median') or 0)/1e3, 1)
        N[f'ep_{name}_records'] = int(e(path, 'records_median') or 0); N[f'ep_{name}_raw_over_br'] = e(path, 'raw_over_br'); N[f'ep_{name}_ttfb_ms'] = e(path, 'ttfb_ms_median')
    if path in epn:
        N[f'ep_{name}_raw_kb_night'] = round(e(path, 'raw_bytes_median', epn)/1e3, 1); N[f'ep_{name}_br_kb_night'] = round((e(path, 'br_wire_bytes_median', epn) or 0)/1e3, 1); N[f'ep_{name}_records_night'] = int(e(path, 'records_median', epn) or 0)
N.update(ep_buses_raw_bytes_per_bus=round(N['ep_buses_raw_kb']*1000/N['ep_buses_records'], 1), ep_buses_br_bytes_per_bus=round(N['ep_buses_br_kb']*1000/N['ep_buses_records'], 1),
         ep_arrivals_raw_bytes_per_pred=round(N['ep_arrivals_raw_kb']*1000/N['ep_arrivals_records']), ep_arrivals_br_bytes_per_pred=round(N['ep_arrivals_br_kb']*1000/N['ep_arrivals_records'], 1))
# --- one viewer per minute (from the client inventory) and bytes per tab-minute (day, brotli)
per_min = {'nr-board': 15, 'aircraft': 12, 'arrivals': 6, 'vessels': 6, 'buses': 4, 'leaderboard': 2, 'bikes': 1, 'disruptions': 60/90, 'road': 0.5, 'tide': 0.2}
br = {'nr-board': f(next(r for r in rows(f'{DATA}/endpoints-nr-board.csv'))['br_wire_bytes_median']), 'aircraft': N['ep_aircraft_br_kb']*1e3, 'arrivals': N['ep_arrivals_br_kb']*1e3, 'vessels': N['ep_vessels_br_kb']*1e3,
      'buses': N['ep_buses_br_kb']*1e3, 'leaderboard': N['ep_leaderboard_br_kb']*1e3, 'bikes': N['ep_bikes_br_kb']*1e3, 'disruptions': N['ep_disruptions_br_kb']*1e3, 'road': N['ep_road_br_kb']*1e3, 'tide': N['ep_tide_br_kb']*1e3}
kb_min = sum(per_min[k]*br[k] for k in per_min)/1e3
N.update(tab_requests_per_min=round(sum(per_min.values()), 1), tab_kb_per_min=round(kb_min), tab_mb_per_hour=round(kb_min*60/1e3, 1), tab_share_arrivals_pct=round(100*per_min['arrivals']*br['arrivals']/1e3/kb_min), tab_share_buses_pct=round(100*per_min['buses']*br['buses']/1e3/kb_min))
# --- latency
p = age['pooled']; pn = agen['pooled']
N.update(bus_age_p50_s=p['p50'], bus_age_p95_s=p['p95'], bus_age_p5_s=p['p5'], bus_age_p50_s_night=pn['p50'], bus_age_p95_s_night=pn['p95'])
# --- Dubai
N.update(dubai_health_heap_mb=30, dubai_health_rss_mb=117, dubai_bikes=213)
# --- reference dates
N.update(cal_day_date='2026-09-30', cal_day_window='12:40 to 13:13 UTC', cal_night_date='2026-09-29', cal_night_window='22:14 to 22:40 UTC', cal_commit='6875e27', cal_machine='Apple M4, Node 24.13', prod_uptime_days=round(mem['primary_window']['uptime_at_end_days'], 1))
put(**N)
print(len(N), 'numbers written')

# --- derived: batch job and scaling scenarios (formulas from the body applied to the parameters above)
n = json.load(open(os.path.join(ROOT, 'numbers.json')))
learner_min = 29  # local run 2026-09-28 on three days of traces (document 1, table 5.1)
S = {}
S['learner_duration_min'] = learner_min; S['learner_window_fixes_m'] = round(3 * n['trace_fixes_per_day'] / 1e6, 1); S['learner_keys_seen'] = 2210; S['learner_keys_learned'] = 1647
S['trace_gb_per_year_gz'] = round(n['trace_gz_mb_per_day'] * 365 / 1e3, 1); S['trace_gb_per_year_raw'] = round(n['trace_raw_mb_per_day'] * 365 / 1e3)
# viewers x10
U = 10
S['sc_viewers'] = U; S['sc_viewers_egress_gb_per_day'] = round(U * n['tab_mb_per_hour'] * 24 / 1e3, 1)
S['sc_viewers_serve_ms'] = round(U * n['cpu_ms_serve_viewer']); S['sc_viewers_main_ms'] = round(n['cpu_main_busy_ms_quiet'] + U * n['cpu_ms_serve_viewer'])
S['sc_viewers_main_util_pct'] = round(100 * S['sc_viewers_main_ms'] / 15000, 1)
# UK-wide bus feed
uk_records = 40000; k = uk_records / n['bus_records_per_poll']; uk_live = round(n['bus_live_day'] * k)
S['sc_uk_records'] = uk_records; S['sc_uk_factor'] = round(k, 1); S['sc_uk_live'] = uk_live
S['sc_uk_xml_mb_per_poll'] = round(n['bus_decoded_mb'] * k); S['sc_uk_xml_gb_per_day'] = round(n['bus_decoded_gb_per_day'] * k)
S['sc_uk_parse_ms'] = round(n['cpu_ms_bods_parse'] * k); S['sc_uk_ingest_ms'] = round((n['cpu_ms_bods_parse'] + n['cpu_ms_io_glue'] + n['cpu_ms_undici']) * k)
S['sc_uk_detector_ms'] = round(n['cpu_ms_detector'] * k); S['sc_uk_main_ms'] = round(n['cpu_main_busy_ms_quiet'] - (n['cpu_ms_bods_parse'] + n['cpu_ms_io_glue'] + n['cpu_ms_undici'] + n['cpu_ms_detector'] + n['cpu_ms_trace']) + (n['cpu_ms_bods_parse'] + n['cpu_ms_io_glue'] + n['cpu_ms_undici'] + n['cpu_ms_detector'] + n['cpu_ms_trace']) * k)
S['sc_uk_main_util_pct'] = round(100 * S['sc_uk_main_ms'] / 15000, 1)
S['sc_uk_heap_extra_mb'] = round(n['heap_fit_kb_per_vehicle_state'] * (uk_live * 1.6 - n['vehicle_states_median']) / 1000)  # states ≈ 1.6 × live (30-min window)
S['sc_uk_trace_gz_mb_per_day'] = round(n['trace_gz_mb_per_day'] * k); S['sc_uk_bus_body_kb_br'] = round(n['ep_buses_br_kb'] * k)
S['sc_uk_learner_min'] = round(learner_min * k)
# one-year retention
S['sc_year_trace_gb_gz'] = S['trace_gb_per_year_gz']; S['sc_year_rollup_mb'] = round(n['rollup_kb_per_day'] * 365 / 1e3); S['sc_year_diversions_mb'] = round(n['diversions_mb_per_day'] * 365)
put(**S); print(len(S), 'derived numbers added')

# --- a few more derived values used in the body
n = json.load(open(os.path.join(ROOT, 'numbers.json')))
put(arrivals_wire_gb_per_day=round(1796457600 / 1e9, 1),  # streams.csv, no viewer, 15 s cadence
    cpu_off_main_ms_control=round(n['cpu_process_ms_control'] - n['cpu_main_busy_ms_quiet']),
    cpu_process_ms_per_viewer_profiled=round(n['cpu_process_ms_viewer'] - n['cpu_process_ms_quiet']),
    arrivals_raw_over_used_fields=2,  # client reads 11 of ~21 fields per prediction (client inventory)
    trace_retention_days=7, trace_disk_cap_gb=2, tab_mb_per_day=round(n['tab_mb_per_hour'] * 24 / 1e3, 1))
put(cpu_ms_serve_quiet=0.3)  # profile, quiet phase: serve row 0.31 ms per 15 s (health checks only)

# --- corrections after peer review (2026-09-30)
n = json.load(open(os.path.join(ROOT, 'numbers.json')))
F = n['trace_fixes_per_day']
put(fixes_per_s_mean=round(F / 86400), fixes_per_poll_mean=round(F / 86400 * n['bus_poll_s']),  # daily mean from the archive; the 146/s figure is a midday replica run
    trace_cap_gb=2, trace_cap_days=round(2 * 1024**3 / (n['trace_raw_mb_per_day'] * 1e6), 1),  # MAX_TOTAL_BYTES = 2 GiB in trace-writer.ts binds before RETENTION_DAYS = 7
    c_json_ms_per_mb=round(n['cpu_ms_json_parse'] / n['arrivals_decoded_mb'], 1),  # day run; all upstream JSON bodies, predictions dominate
    trace_us_per_fix=round(n['cpu_ms_trace'] / n['new_fixes_per_poll_day'] * 1000, 1),  # day run
    state_over_live=round(n['local_vehicle_states_day'] / n['bus_live_day'], 2),  # measured S/V by day (30-min window)
    arrivals_records_night=4487, status_gb_per_day=0.46, darwin_gb_per_day=0.59,  # streams.csv / calibration note B
    tab_gb_per_day=round(n['tab_mb_per_hour'] * 24 / 1e3, 1),
    cpu_main_ms_per_viewer=round(n['cpu_main_busy_ms_viewer'] - n['cpu_main_busy_ms_quiet']),
    cpu_off_main_ms_per_viewer=round((n['cpu_process_ms_viewer'] - n['cpu_process_ms_quiet']) - (n['cpu_main_busy_ms_viewer'] - n['cpu_main_busy_ms_quiet'])),
    main_share_profiled_pct=round(100 * n['cpu_main_busy_ms_quiet'] / n['cpu_process_ms_quiet']))
n = json.load(open(os.path.join(ROOT, 'numbers.json')))
U = n['sc_viewers']; main = n['cpu_main_busy_ms_quiet'] + U * n['cpu_main_ms_per_viewer']; proc = n['cpu_process_ms_quiet'] + U * (n['cpu_main_ms_per_viewer'] + n['cpu_off_main_ms_per_viewer'])
put(sc_viewers_main_ms=round(main), sc_viewers_main_util_pct=round(100 * main / 15000, 1), sc_viewers_process_pct_profiled=round(100 * proc / 15000),
    sc_uk_heap_extra_mb=round(n['heap_fit_kb_per_vehicle_state'] * (n['sc_uk_live'] * n['state_over_live'] - n['vehicle_states_median']) / 1000),
    sc_uk_trace_raw_gb_per_day=round(n['trace_raw_mb_per_day'] * n['sc_uk_factor'] / 1000, 1),
    sc_uk_cap_days=round(2 * 1024**3 / (n['trace_raw_mb_per_day'] * n['sc_uk_factor'] * 1e6), 1),
    viewers_per_core_profiled=round(15000 / (n['cpu_main_ms_per_viewer'] + n['cpu_off_main_ms_per_viewer'])))
