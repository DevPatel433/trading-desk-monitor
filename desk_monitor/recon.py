"""Post-trade reconciliation: match NEW, FILL and CANCEL events per order, classify breaks.

An order is closed when filled quantity plus cancelled quantity equals its order quantity.
"""
from collections import Counter, defaultdict

from .schema import parse, read_csv

PRICE_TOL = 1e-9


def reconcile(path):
    _, rows = read_csv(path)
    by_order = defaultdict(list)
    for row in rows:
        e = parse(row)
        by_order[e.order_id].append(e)

    breaks = []
    seen_fill_ids = set()

    def brk(kind, oid, detail):
        breaks.append({"kind": kind, "order_id": oid, "detail": detail})

    for oid, evs in by_order.items():
        evs.sort(key=lambda e: e.seq)
        news = [e for e in evs if e.event == "NEW"]
        if not news:
            brk("UNKNOWN_ORDER", oid, "executions or cancels with no NEW event")
            continue
        new = news[0]
        if len(news) > 1:
            brk("DUPLICATE_NEW", oid, f"{len(news)} NEW events")

        filled = cancelled = 0
        for e in evs:
            if e.event == "NEW":
                continue
            if e.event == "CANCEL":
                if e.ts_ns < new.ts_ns:
                    brk("CANCEL_BEFORE_NEW", oid, "cancel timestamped before order")
                cancelled += e.qty
                continue
            # FILL
            if e.fill_id in seen_fill_ids:
                brk("DUPLICATE_FILL", oid, f"fill {e.fill_id} booked twice")
                continue  # a repeated execution must not count twice
            seen_fill_ids.add(e.fill_id)
            if e.ts_ns < new.ts_ns:
                brk("FILL_BEFORE_NEW", oid, f"fill {e.fill_id} precedes its order")
            if e.side != new.side:
                brk("SIDE_MISMATCH", oid, f"fill side {e.side} vs order side {new.side}")
            if new.side == "BUY":
                breached = e.price > new.price + PRICE_TOL
            else:
                breached = e.price < new.price - PRICE_TOL
            if breached:
                brk("PRICE_BREACH", oid, f"fill {e.price} through limit {new.price}")
            filled += e.qty

        if filled + cancelled > new.qty:
            brk("OVERFILL", oid, f"filled {filled} + cancelled {cancelled} > ordered {new.qty}")
        elif filled + cancelled < new.qty:
            open_qty = new.qty - filled - cancelled
            brk("UNCLOSED", oid, f"{open_qty} shares neither filled nor cancelled")

    return {
        "orders": len(by_order),
        "breaks": breaks,
        "by_kind": dict(Counter(b["kind"] for b in breaks)),
    }
