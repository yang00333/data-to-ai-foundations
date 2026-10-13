"""End-to-end tests: both domain configurations run on the same shared code."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d2ai.deliver import write_outputs  # noqa: E402
from d2ai.pipeline import run_pipeline  # noqa: E402


class AquacultureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_pipeline(ROOT / "configs" / "aquaculture.toml")

    def test_succeeds(self):
        self.assertTrue(self.result.ok, self.result.report["table_checks"])

    def test_sensor_faults_never_reach_the_table(self):
        self.assertTrue(all(r["do_mg_l"] <= 20 for r in self.result.rows))
        reasons = self.result.report["sources"]["dissolved_oxygen"]["by_reason"]
        self.assertEqual(reasons.get("do_physically_possible"), 6)

    def test_fahrenheit_converted(self):
        temps = [r["water_temp_c"] for r in self.result.rows]
        self.assertTrue(20 < min(temps) and max(temps) < 32)

    def test_outage_rows_are_quarantined_not_invented(self):
        held = self.result.report["output"]["by_reason"]
        self.assertEqual(held.get("not_null:do_mg_l"), 6)  # 90-minute outage, 15-minute grid

    def test_one_row_per_15_minutes(self):
        ts = [r["ts"] for r in self.result.rows]
        self.assertEqual(len(ts), len(set(ts)))


class SemiconductorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_pipeline(ROOT / "configs" / "semiconductor_test.toml")

    def test_succeeds(self):
        self.assertTrue(self.result.ok, self.result.report["table_checks"])

    def test_unknown_product_is_held_back(self):
        self.assertNotIn("PX-999", {r["product_id"] for r in self.result.rows})

    def test_negative_inventory_rejected_at_source(self):
        self.assertTrue(all(r["units_on_hand"] >= 0 for r in self.result.rows))

    def test_derived_capacity_gap(self):
        r = self.result.rows[0]
        self.assertAlmostEqual(r["capacity_gap_hours"],
                               r["tester_hours"] - r["planned_lots"] * r["test_hours_per_lot"])


class DeliveryTests(unittest.TestCase):
    def test_writes_three_outputs(self):
        result = run_pipeline(ROOT / "configs" / "semiconductor_test.toml")
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_outputs(result, tmp)
            for p in paths.values():
                self.assertTrue(p.exists() and p.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
