"""Event schema shared by every stage of the pipeline.

Each row is one order-lifecycle event:
  NEW     - an order is sent (qty = order size, price = limit)
  FILL    - an execution (fill_id unique, qty = executed size, price = execution price)
  CANCEL  - remaining quantity is cancelled (qty = cancelled size)
"""
import csv
from dataclasses import dataclass

COLUMNS = ["seq", "ts_ns", "event", "order_id", "fill_id", "side", "qty", "price"]
EVENT_TYPES = ("NEW", "FILL", "CANCEL")
SIDES = ("BUY", "SELL")


@dataclass(frozen=True)
class Event:
    seq: int
    ts_ns: int
    event: str
    order_id: str
    fill_id: str
    side: str
    qty: int
    price: float


def read_csv(path):
    """Return (header, rows) as raw strings so validation can report problems."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)
    return header, rows


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse(row):
    return Event(
        seq=int(row["seq"]),
        ts_ns=int(row["ts_ns"]),
        event=row["event"],
        order_id=row["order_id"],
        fill_id=row["fill_id"],
        side=row["side"],
        qty=int(row["qty"]),
        price=float(row["price"]),
    )
