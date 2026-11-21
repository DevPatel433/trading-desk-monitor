# Desk Monitor

A trading-desk toolkit with three parts: a pre-open readiness gate, post-trade
reconciliation, and intraday anomaly monitoring. It runs on a synthetic order-flow
feed in the schema a live feed would be normalised into. Pure Python 3, standard
library only.

## Quick start

    python3 -m unittest discover -s tests -t .          # 7 tests
    python3 -m desk_monitor generate --out data/events_2026-11-20.csv \
        --faults drop_fill:2,duplicate_fill:1,price_breach:1,fill_before_new:1 \
        --burst-orders 3000 --truth data/truth_2026-11-20.json
    bash scripts/run_daily.sh 2026-11-20                # reads data/events_<date>.csv

Exit codes: 0 clean, 1 breaks or alerts found, 2 readiness gate failed.
Reports land in `reports/<date>/` as `report.md`, `readiness.json`, `recon.json`,
`alerts.json` and `run.log`.

## Components

- **Readiness (`readiness.py`)**: schema, value validity, sequence continuity, duplicate
  sequence numbers and timestamp ordering. Any error halts the run before reconciliation.
- **Reconciliation (`recon.py`)**: matches NEW, FILL and CANCEL events per order.
  Breaks: UNCLOSED, OVERFILL, DUPLICATE_FILL, PRICE_BREACH, FILL_BEFORE_NEW,
  CANCEL_BEFORE_NEW, SIDE_MISMATCH, UNKNOWN_ORDER, DUPLICATE_NEW. A repeated fill is
  counted once.
- **Monitoring (`monitor.py`)**: 100 ms message and fill rates through an adaptive
  z-score detector. Spikes raise ANOMALY and do not update the baseline. A sustained
  run of anomalies, or a CUSUM shift in the normal points, is treated as drift, and the
  baseline is re-learned.
- **Report (`report.py`)**: a daily markdown summary.

## Validation

The generator returns ground truth for every fault it injects. The test suite checks
that each one is caught. In the demo day, 5 of 5 injected reconciliation faults were
found with no false UNCLOSED or OVERFILL breaks. A 3-second order-flow burst of 3,000
orders produced 30 anomaly alerts, and the detector did not drift on it. On a clean
day with no burst, the monitor raised 1 alert in 399 buckets.

## Trade-offs to tune

- `run_limit` (default 50 buckets, 5 s): how long an anomaly can last before it is
  treated as a regime change. A longer value tolerates longer bursts but delays adaptation.
- `warmup` (default 50 buckets): the re-learning window after a drift reset. The
  detector is blind during it. In production, page on drift events.
- `z_thresh` (default 5.0): trades false alarms against missed events. Tune it against
  labelled history.

## Limitations

- Synthetic data only. Timestamps are generated from a fixed epoch, not the real date.
- No live feed adapter, persistence, or dashboard.
- The price check compares fills to the order's limit only. Production would also check
  reference prices and position limits.
- The script is run with `bash scripts/run_daily.sh`. Mark it executable with
  `chmod +x` before scheduling it under cron or systemd.
