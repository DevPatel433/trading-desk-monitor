#!/usr/bin/env bash
# Daily desk-monitor run. Intended for cron or a systemd timer before market open.
#   usage: scripts/run_daily.sh [YYYY-MM-DD]
#   env:   EVENTS_DIR (default ./data), REPORT_DIR (default ./reports)
set -euo pipefail

DATE="${1:-$(date +%F)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVENTS="${EVENTS_DIR:-$ROOT/data}/events_${DATE}.csv"
OUTDIR="${REPORT_DIR:-$ROOT/reports}/${DATE}"
LOG="${OUTDIR}/run.log"

if [[ ! -f "$EVENTS" ]]; then
  echo "$DATE: event file missing: $EVENTS" >&2
  exit 2
fi

mkdir -p "$OUTDIR"
cd "$ROOT"

set +e
python3 -m desk_monitor run --events "$EVENTS" --outdir "$OUTDIR" --date "$DATE" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e

case "$rc" in
  0) echo "$DATE: OK" ;;
  1) echo "$DATE: breaks or alerts found, see $OUTDIR/report.md" ;;
  2) echo "$DATE: READINESS FAILED, processing halted" >&2 ;;
  *) echo "$DATE: unexpected error (exit $rc)" >&2 ;;
esac
exit "$rc"
