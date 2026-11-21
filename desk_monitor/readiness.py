"""Pre-open readiness gate: is today's event file safe to process?

Any ERROR fails the gate, and the pipeline halts before reconciliation or monitoring.
"""
from .schema import COLUMNS, EVENT_TYPES, SIDES, read_csv


def check(path):
    header, rows = read_csv(path)
    issues = []

    def add(severity, check, detail):
        issues.append({"severity": severity, "check": check, "detail": detail})

    def result():
        errors = sum(1 for i in issues if i["severity"] == "ERROR")
        return {"status": "FAIL" if errors else "PASS", "rows": len(rows),
                "errors": errors, "issues": issues}

    missing = [c for c in COLUMNS if c not in header]
    if missing:
        add("ERROR", "schema", f"missing columns: {missing}")
        return result()
    if not rows:
        add("ERROR", "completeness", "file has no events")
        return result()

    prev_seq = prev_ts = None
    seen = set()
    for n, row in enumerate(rows, start=2):  # file line numbers, header is line 1
        try:
            seq, ts = int(row["seq"]), int(row["ts_ns"])
            qty, price = int(row["qty"]), float(row["price"])
        except (TypeError, ValueError):
            add("ERROR", "schema", f"line {n}: non-numeric seq, ts, qty or price")
            continue
        if row["event"] not in EVENT_TYPES:
            add("ERROR", "values", f"line {n}: unknown event '{row['event']}'")
        if row["side"] not in SIDES:
            add("ERROR", "values", f"line {n}: unknown side '{row['side']}'")
        if qty <= 0 or price <= 0:
            add("ERROR", "values", f"line {n}: non-positive qty or price")
        if row["event"] == "FILL" and not row["fill_id"]:
            add("ERROR", "values", f"line {n}: FILL without fill_id")
        if seq in seen:
            add("ERROR", "sequence", f"line {n}: duplicate seq {seq}")
        seen.add(seq)
        if prev_seq is not None and seq != prev_seq + 1:
            add("ERROR", "sequence", f"line {n}: seq jumps {prev_seq} -> {seq}")
        prev_seq = seq
        if prev_ts is not None and ts < prev_ts:
            add("ERROR", "timestamps", f"line {n}: timestamp goes backwards")
        prev_ts = ts

    return result()
