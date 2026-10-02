#!/bin/bash
# Measurement D: profile the backend locally for ~13 minutes.
#
# Runs origin/main from a dedicated worktree, never the main checkout, with
#   PORT=3999, PERSIST_DIR=<worktree>/tmp/persist  (so no real runtime data is touched)
# and Node's built-in sampling CPU profiler (--cpu-prof). tsx is loaded with
# --import, which is what `npm start` (tsx src/server.ts) does under the hood,
# minus the wrapper process that would otherwise receive the profiler flag.
#
# The persist dir is seeded from the local archive so the run resembles
# production rather than a first boot:
#   - learned routes  (latest route snapshot)  -> the diversion detector starts
#   - last 7 rollups                            -> the detector's shape gates
#   - a fresh learner marker                    -> the daily learner child
#     process does NOT start (it is a 24 h batch that would hit TfL ~700 times)
#
# SECRETS: backend/.env is read by the backend itself. This script never reads,
# prints or copies it. The server log stays in the worktree, not in data/.
set -euo pipefail

WORKTREE="${WORKTREE:-$HOME/london-live-worktrees/measure}"
REPORT="${REPORT:-$HOME/london-live-reports/02-architecture}"
ARCHIVE="${ARCHIVE:-$HOME/bus-archive}"
PORT="${PORT:-3999}"
WARMUP_S="${WARMUP_S:-60}"
QUIET_S="${QUIET_S:-360}"
VIEWER_S="${VIEWER_S:-360}"
# PROFILE=0 runs the identical setup WITHOUT --cpu-prof: the control that shows
# how much of process.cpuUsage() is the profiler's own sampling.
PROFILE="${PROFILE:-1}"
RUN_NAME="${RUN_NAME:-profile-run}"

RUN="$WORKTREE/tmp/$RUN_NAME"
PERSIST="$WORKTREE/tmp/persist-$RUN_NAME"
rm -rf "$RUN" "$PERSIST"
mkdir -p "$RUN/cpuprofile" "$PERSIST/bus-routes/learned" "$PERSIST/bus-rollups"

SNAPSHOT=$(ls "$ARCHIVE"/route-snapshots/*.tar.gz | tail -1)
tar -xzf "$SNAPSHOT" -C "$RUN"
mv "$RUN"/*/routes/*.json "$PERSIST/bus-routes/learned/"
for f in $(ls "$ARCHIVE"/bus-rollups/*.json | tail -7); do cp "$f" "$PERSIST/bus-rollups/"; done
node -e 'process.stdout.write(JSON.stringify({ranAt: Date.now(), seededBy: "run-local-profile.sh"}))' \
  > "$PERSIST/bus-learner.last-run.json"
echo "seeded: $(ls "$PERSIST/bus-routes/learned" | wc -l | tr -d ' ') learned routes from $(basename "$SNAPSHOT")"

cd "$WORKTREE/backend"
echo "node $(node -v), commit $(git -C "$WORKTREE" rev-parse --short HEAD)" | tee "$RUN/environment.txt"

PROFILER_FLAGS=()
if [ "$PROFILE" = "1" ]; then PROFILER_FLAGS=(--cpu-prof --cpu-prof-dir="$RUN/cpuprofile"); fi
sysctl -n machdep.cpu.brand_string >> "$RUN/environment.txt" 2>/dev/null || true
echo "profiler: $PROFILE" >> "$RUN/environment.txt"

PORT="$PORT" PERSIST_DIR="$PERSIST" METRICS_OUT="$RUN/proc-metrics.jsonl" \
  node ${PROFILER_FLAGS[@]+"${PROFILER_FLAGS[@]}"} \
       --import tsx --import "$REPORT/scripts/preload-metrics.mjs" \
       src/server.ts > "$RUN/server.log" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$RUN/server.pid"

until curl -sf -o /dev/null "http://127.0.0.1:$PORT/health"; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then echo "server exited during start"; exit 1; fi
  sleep 1
done
echo "server up (pid $SERVER_PID)"

node "$REPORT/scripts/synthetic-viewer.mjs" --port "$PORT" --out "$RUN" \
  --warmup "$WARMUP_S" --quiet "$QUIET_S" --viewer "$VIEWER_S"

# SIGTERM -> server.ts closes and calls process.exit(0) -> profile is written.
kill -TERM "$SERVER_PID"
until ! kill -0 "$SERVER_PID" 2>/dev/null; do sleep 1; done
echo "server stopped; profile: $(ls "$RUN/cpuprofile")"
# $PERSIST is kept: analyze_cpuprofile.py reads what the run wrote (trace lines, archives).
