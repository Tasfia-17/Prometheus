#!/usr/bin/env bash
# run-prometheus-test.sh — Start app, run k6, generate report, clean up.
# Usage: ./scripts/run-prometheus-test.sh <k6-script> <app-type> [base-url]
#
# app-type: midas | calliope | hestia

set -euo pipefail

SCRIPT_PATH="${1:?Usage: run-prometheus-test.sh <k6-script> <app-type> [base-url]}"
APP_TYPE="${2:?Usage: run-prometheus-test.sh <k6-script> <app-type> [base-url]}"
BASE_URL="${3:-}"

RUN_LOG="/tmp/prometheus-run.log"
exec 3>&1
exec 1>"$RUN_LOG" 2>&1

REPORT_NAME=$(basename "$SCRIPT_PATH" .js)
APP_PID=""
PYTHON=$(command -v python3.12 || command -v python3)

cleanup() {
  [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null && wait "$APP_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: Start app ──
case "$APP_TYPE" in
  midas)
    BASE_URL="${BASE_URL:-http://localhost:8000}"
    HEALTH_URL="$BASE_URL/api/health"
    cd demos/midas-bank
    $PYTHON -m pip install --break-system-packages -r requirements.txt -q 2>/dev/null || true
    $PYTHON -m uvicorn app:app --host 0.0.0.0 --port 8000 > /tmp/midas.log 2>&1 &
    APP_PID=$!
    cd ../..
    ;;
  calliope)
    BASE_URL="${BASE_URL:-http://localhost:3000}"
    HEALTH_URL="$BASE_URL/api/health"
    cd demos/calliope-books
    npm install --silent 2>/dev/null || true
    node app.js > /tmp/calliope.log 2>&1 &
    APP_PID=$!
    cd ../..
    ;;
  hestia)
    BASE_URL="${BASE_URL:-http://localhost:8080}"
    HEALTH_URL="$BASE_URL/api/health"
    cd demos/hestia-eats
    npm install --silent 2>/dev/null || true
    node app.js > /tmp/hestia.log 2>&1 &
    APP_PID=$!
    cd ../..
    ;;
  *)
    echo "ERROR: Unknown app type '$APP_TYPE'. Use midas, calliope, or hestia."
    exit 1
    ;;
esac

# ── Step 2: Health check ──
echo "Waiting for $APP_TYPE to start..."
for i in $(seq 1 15); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "App healthy (attempt $i)."
    break
  fi
  [ "$i" -eq 15 ] && { echo "ERROR: App failed to start."; cat /tmp/${APP_TYPE}.log 2>/dev/null; exit 1; }
  sleep 1
done

# ── Step 3: Risk analysis ──
mkdir -p k6/prometheus/results
DIFF_TEXT=$(git diff HEAD~1 -- "demos/${APP_TYPE}-bank/" "demos/${APP_TYPE}-books/" "demos/${APP_TYPE}-eats/" 2>/dev/null || \
            git diff HEAD~1 -- "demos/" 2>/dev/null || echo "")
RISK_FILE="k6/prometheus/results/${REPORT_NAME}-risk.md"
GRAPHRAG_FILE="k6/prometheus/results/${REPORT_NAME}-graphrag.md"

if [ -n "$DIFF_TEXT" ]; then
  echo "$DIFF_TEXT" | $PYTHON scripts/analyze-risk.py --diff-stdin > "$RISK_FILE" 2>/dev/null || true

  # Resolve spec path
  case "$APP_TYPE" in
    midas)    SPEC="demos/midas-bank/openapi.json" ;;
    calliope) SPEC="demos/calliope-books/openapi.json" ;;
    hestia)   SPEC="demos/hestia-eats/openapi.json" ;;
  esac
  echo "$DIFF_TEXT" | $PYTHON -m graphrag --spec "$SPEC" --diff-stdin > "$GRAPHRAG_FILE" 2>/dev/null || true
fi

# ── Step 4: Validate k6 script ──
k6 inspect "$SCRIPT_PATH" > /dev/null 2>&1 || { echo "ERROR: k6 script invalid"; k6 inspect "$SCRIPT_PATH" 2>&1; exit 1; }

# ── Step 5: Run k6 ──
echo "Running k6: $SCRIPT_PATH"
k6 run --env BASE_URL="$BASE_URL" "$SCRIPT_PATH" > /tmp/k6-run.log 2>&1
K6_EXIT=$?
tail -20 /tmp/k6-run.log

# ── Step 6: Generate report ──
JSON_RESULT="k6/prometheus/results/${REPORT_NAME}.json"
[ ! -f "$JSON_RESULT" ] && JSON_RESULT=$(find k6/prometheus/results/ -name "*.json" 2>/dev/null | head -1)

MD_RESULT=""
if [ -f "$JSON_RESULT" ]; then
  BASELINE_FILE=".prometheus/baselines/${APP_TYPE}.json"
  ARGS="$JSON_RESULT --save-baseline $BASELINE_FILE"
  [ -f "$BASELINE_FILE" ] && ARGS="$ARGS --baseline $BASELINE_FILE"
  [ -f "$RISK_FILE" ] && ARGS="$ARGS --risk-report $RISK_FILE"
  [ -f "$GRAPHRAG_FILE" ] && ARGS="$ARGS --graphrag-report $GRAPHRAG_FILE"

  $PYTHON scripts/generate-report.py $ARGS 2>/dev/null
  MD_RESULT="k6/prometheus/results/${REPORT_NAME}-report.md"
  [ -f "$MD_RESULT" ] && cat "$MD_RESULT" >&3
fi

[ -z "$MD_RESULT" ] || [ ! -f "$MD_RESULT" ] && {
  echo "ERROR: Report generation failed. Last 20 lines of run log:" >&3
  tail -20 "$RUN_LOG" >&3
}

exit $K6_EXIT
