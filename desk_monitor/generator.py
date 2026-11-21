"""Synthetic order-flow generator with fault injection.

Produces the CSV schema the rest of the pipeline consumes. Every injected fault
is returned as ground truth so tests can verify that the checks catch it.
"""
import random

from .schema import write_csv

START_NS = 1_700_000_000_000_000_000
FAULT_KINDS = ("drop_fill", "duplicate_fill", "price_breach", "fill_before_new", "seq_gap")


def _row(ts, event, oid, fill_id, side, qty, price):
    return {"ts_ns": ts, "event": event, "order_id": oid, "fill_id": fill_id,
            "side": side, "qty": qty, "price": round(price, 2)}


def _fill_price(side, limit, rng):
    """Clean fills execute at or inside the limit."""
    off = rng.uniform(0, 0.03)
    return limit - off if side == "BUY" else limit + off


def generate(n_orders=20000, seed=7, mean_gap_ns=2_000_000, faults=None, burst=None):
    """Build a day of events.

    faults: {kind: count}, kinds listed in FAULT_KINDS.
    burst:  (start_s, seconds, n_orders) adds a short order-flow spike of
            NEW+CANCEL pairs, to exercise the intraday monitor.
    Returns (rows, truth) where truth is a list of {"kind", "order_id"} dicts.
    """
    rng = random.Random(seed)
    rows = []
    t = START_NS
    for i in range(n_orders):
        t += int(rng.expovariate(1.0) * mean_gap_ns)
        oid = f"O{i:06d}"
        side = rng.choice(["BUY", "SELL"])
        qty = rng.choice([100, 200, 300, 500])
        mid = 100 + rng.uniform(-1, 1)
        limit = round(mid + 0.05, 2) if side == "BUY" else round(mid - 0.05, 2)
        rows.append(_row(t, "NEW", oid, "", side, qty, limit))

        r = rng.random()
        if r < 0.7:  # fully filled, in one or two executions
            pieces = [qty] if rng.random() < 0.5 else [qty // 2, qty - qty // 2]
            tf = t
            for k, q in enumerate(pieces, 1):
                tf += int(rng.uniform(1e6, 50e6))
                rows.append(_row(tf, "FILL", oid, f"{oid}-F{k}", side, q,
                                 _fill_price(side, limit, rng)))
        elif r < 0.9:  # partially filled, remainder cancelled
            q = qty // 2
            tf = t + int(rng.uniform(1e6, 50e6))
            rows.append(_row(tf, "FILL", oid, f"{oid}-F1", side, q,
                             _fill_price(side, limit, rng)))
            rows.append(_row(tf + int(rng.uniform(1e6, 50e6)), "CANCEL", oid, "",
                             side, qty - q, limit))
        else:  # cancelled without any fill
            rows.append(_row(t + int(rng.uniform(1e6, 50e6)), "CANCEL", oid, "",
                             side, qty, limit))

    if burst:
        start_s, seconds, n = burst
        for k in range(n):
            oid = f"B{k:06d}"
            ts = START_NS + int(start_s * 1e9) + int(rng.uniform(0, seconds * 1e9))
            rows.append(_row(ts, "NEW", oid, "", "BUY", 100, 99.0))
            rows.append(_row(ts + 1_000_000, "CANCEL", oid, "", "BUY", 100, 99.0))

    rows.sort(key=lambda r: r["ts_ns"])
    faults = faults or {}
    truth = []
    frng = random.Random(seed + 1)
    used = set()

    def pick(pred):
        cands = [r for r in rows if pred(r) and r["order_id"] not in used]
        if not cands:
            raise ValueError("not enough eligible orders for requested faults")
        choice = frng.choice(cands)
        used.add(choice["order_id"])
        return choice

    is_fill = lambda r: r["event"] == "FILL"

    for _ in range(faults.get("drop_fill", 0)):
        c = pick(is_fill)
        rows = [r for r in rows if r is not c]
        truth.append({"kind": "UNCLOSED", "order_id": c["order_id"]})

    for _ in range(faults.get("duplicate_fill", 0)):
        c = pick(is_fill)
        idx = next(i for i, r in enumerate(rows) if r is c)
        rows.insert(idx + 1, dict(c))
        truth.append({"kind": "DUPLICATE_FILL", "order_id": c["order_id"]})

    for _ in range(faults.get("price_breach", 0)):
        c = pick(is_fill)
        bump = 0.50 if c["side"] == "BUY" else -0.50
        c["price"] = round(c["price"] + bump, 2)
        truth.append({"kind": "PRICE_BREACH", "order_id": c["order_id"]})

    for _ in range(faults.get("fill_before_new", 0)):
        c = pick(is_fill)
        new = next(r for r in rows if r["order_id"] == c["order_id"] and r["event"] == "NEW")
        new["ts_ns"] = c["ts_ns"] + 5_000_000  # order booked late, after its fill
        truth.append({"kind": "FILL_BEFORE_NEW", "order_id": c["order_id"]})

    rows.sort(key=lambda r: r["ts_ns"])
    for seq, r in enumerate(rows, 1):
        r["seq"] = seq

    # Dropped rows after numbering leave holes in the sequence (a transport loss).
    for _ in range(faults.get("seq_gap", 0)):
        del rows[frng.randrange(1, len(rows) - 1)]
        truth.append({"kind": "SEQ_GAP", "order_id": None})

    return rows, truth


def write_events(path, **kwargs):
    rows, truth = generate(**kwargs)
    write_csv(path, rows)
    return truth
