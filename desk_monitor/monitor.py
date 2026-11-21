"""Intraday monitoring: 100 ms rate metrics through an adaptive anomaly detector.

Design notes:
- The baseline (EWMA mean and variance) updates only on normal points, so a spike
  cannot pull the baseline toward itself and hide later problems.
- A run of anomalous points longer than `run_limit` is treated as a regime change
  rather than a transient. The detector re-learns its baseline, so it adapts to the
  new level instead of alarming forever. The cost is a short re-learning gap.
- A two-sided CUSUM on normal z-scores catches slow drift that never crosses the
  per-point threshold.
"""
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from .schema import parse, read_csv

BUCKET_NS = 100_000_000  # 100 ms
METRICS = ("msgs", "fills")


class AdaptiveDetector:
    def __init__(self, alpha=0.02, z_thresh=5.0, warmup=50,
                 cusum_k=0.5, cusum_h=12.0, run_limit=50):
        self.alpha = alpha
        self.z_thresh = z_thresh
        self.warmup = warmup
        self.k = cusum_k
        self.h = cusum_h
        self.run_limit = run_limit
        self.mean = None
        self.var = None
        self.buffer = []
        self.s_up = self.s_dn = 0.0
        self.run = 0

    def _restart(self, x):
        self.mean = self.var = None
        self.buffer = [x]
        self.s_up = self.s_dn = 0.0
        self.run = 0

    def update(self, x):
        """Feed one observation. Returns None, ("ANOMALY", z) or ("DRIFT", z)."""
        if self.mean is None:
            self.buffer.append(x)
            if len(self.buffer) >= self.warmup:
                self.mean = statistics.fmean(self.buffer)
                self.var = max(statistics.pvariance(self.buffer), 1e-6)
                self.buffer = []
            return None

        z = (x - self.mean) / math.sqrt(self.var)
        if abs(z) > self.z_thresh:
            self.run += 1
            if self.run >= self.run_limit:
                self._restart(x)
                return ("DRIFT", z)
            return ("ANOMALY", z)

        self.run = 0
        self.s_up = max(0.0, self.s_up + z - self.k)
        self.s_dn = max(0.0, self.s_dn - z - self.k)
        if self.s_up > self.h or self.s_dn > self.h:
            self._restart(x)
            return ("DRIFT", z)

        d = x - self.mean
        self.mean += self.alpha * d
        self.var = (1 - self.alpha) * (self.var + self.alpha * d * d)
        return None


def bucket_series(events):
    """Return (bucket indices, {metric: values}) on a contiguous 100 ms grid."""
    counts = defaultdict(lambda: {"msgs": 0, "fills": 0})
    for e in events:
        b = e.ts_ns // BUCKET_NS
        counts[b]["msgs"] += 1
        if e.event == "FILL":
            counts[b]["fills"] += 1
    if not counts:
        return [], {m: [] for m in METRICS}
    buckets = list(range(min(counts), max(counts) + 1))
    series = {m: [counts[b][m] for b in buckets] for m in METRICS}
    return buckets, series


def monitor(path, **detector_kwargs):
    _, rows = read_csv(path)
    buckets, series = bucket_series([parse(r) for r in rows])
    alerts = []
    for metric in METRICS:
        det = AdaptiveDetector(**detector_kwargs)
        for b, x in zip(buckets, series[metric]):
            out = det.update(x)
            if out:
                kind, z = out
                alerts.append({
                    "metric": metric,
                    "kind": kind,
                    "t_offset_s": round((b - buckets[0]) * BUCKET_NS / 1e9, 1),
                    "time_utc": datetime.fromtimestamp(b * BUCKET_NS / 1e9, timezone.utc)
                                .isoformat(timespec="milliseconds"),
                    "value": x,
                    "z": round(z, 2),
                })
    alerts.sort(key=lambda a: (a["t_offset_s"], a["metric"]))
    return {"buckets": len(buckets), "alerts": alerts}
