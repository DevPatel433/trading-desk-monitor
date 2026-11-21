import os
import random
import tempfile
import unittest

from desk_monitor import generator, monitor, readiness, recon
from desk_monitor.monitor import AdaptiveDetector


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_clean_day_passes_and_reconciles_cleanly(self):
        p = self.path("clean.csv")
        generator.write_events(p, n_orders=2000, seed=1)
        self.assertEqual(readiness.check(p)["status"], "PASS")
        self.assertEqual(recon.reconcile(p)["breaks"], [])

    def test_every_injected_reconciliation_fault_is_detected(self):
        p = self.path("faulty.csv")
        truth = generator.write_events(
            p, n_orders=2000, seed=2,
            faults={"drop_fill": 2, "duplicate_fill": 2,
                    "price_breach": 2, "fill_before_new": 2})
        self.assertEqual(readiness.check(p)["status"], "PASS")
        res = recon.reconcile(p)
        found = {(b["kind"], b["order_id"]) for b in res["breaks"]}
        for t in truth:
            self.assertIn((t["kind"], t["order_id"]), found, f"missed {t}")
        # Duplicates must not inflate fills into false UNCLOSED or OVERFILL breaks.
        expected_unclosed = {(t["kind"], t["order_id"]) for t in truth if t["kind"] == "UNCLOSED"}
        actual_unclosed = {(b["kind"], b["order_id"]) for b in res["breaks"]
                           if b["kind"] in ("UNCLOSED", "OVERFILL")}
        self.assertEqual(actual_unclosed, expected_unclosed)

    def test_readiness_gate_halts_on_sequence_gap(self):
        p = self.path("gap.csv")
        generator.write_events(p, n_orders=500, seed=3, faults={"seq_gap": 1})
        res = readiness.check(p)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(i["check"] == "sequence" for i in res["issues"]))

    def test_readiness_gate_catches_missing_columns(self):
        p = self.path("bad.csv")
        with open(p, "w") as f:
            f.write("seq,ts_ns,event\n1,100,NEW\n")
        self.assertEqual(readiness.check(p)["status"], "FAIL")

    def test_detector_flags_spike_without_absorbing_it(self):
        rng = random.Random(1)
        det = AdaptiveDetector()
        for _ in range(200):
            det.update(rng.gauss(100, 5))
        out = det.update(300)
        self.assertEqual(out[0], "ANOMALY")
        self.assertLess(abs(det.mean - 100), 3, "spike leaked into the baseline")

    def test_detector_adapts_to_level_shift(self):
        rng = random.Random(2)
        det = AdaptiveDetector()
        kinds = []
        stream = [rng.gauss(100, 5) for _ in range(200)] + [rng.gauss(130, 5) for _ in range(400)]
        for x in stream:
            out = det.update(x)
            kinds.append(out[0] if out else None)
        self.assertIn("DRIFT", kinds[200:])
        self.assertNotIn("ANOMALY", kinds[-200:], "detector kept alarming after adapting")

    def test_monitor_flags_order_flow_burst(self):
        p = self.path("burst.csv")
        generator.write_events(p, n_orders=20000, seed=4, burst=(15.0, 3.0, 3000))
        res = monitor.monitor(p)
        hits = [a for a in res["alerts"] if 14.5 <= a["t_offset_s"] <= 19.0]
        self.assertTrue(hits, "burst not detected")


if __name__ == "__main__":
    unittest.main()
