"""End-to-end tests: both domains, and every readiness profile, run on the same shared code."""

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
        cls.model = cls.result.profile("forecasting_model")
        cls.dashboard = cls.result.profile("analytics_dashboard")
        cls.assistant = cls.result.profile("ai_assistant_context")

    def test_all_profiles_succeed(self):
        self.assertTrue(self.result.ok, self.result.report["profiles"])

    def test_foundation_built_once_and_shared(self):
        self.assertEqual(self.result.foundation_rows, len(self.dashboard.rows))
        self.assertEqual(len(self.result.profiles), 3)

    def test_sensor_faults_never_reach_any_profile(self):
        for p in self.result.profiles:
            self.assertTrue(all(r["do_mg_l"] is None or r["do_mg_l"] <= 20 for r in p.rows), p.name)
        reasons = self.result.report["sources"]["dissolved_oxygen"]["by_reason"]
        self.assertEqual(reasons.get("do_physically_possible"), 6)

    def test_fahrenheit_converted(self):
        temps = [r["water_temp_c"] for r in self.model.rows]
        self.assertTrue(20 < min(temps) and max(temps) < 32)

    def test_model_holds_back_outage_rows(self):
        self.assertEqual(self.model.report["by_reason"].get("not_null:do_mg_l"), 6)
        self.assertTrue(all(r["do_mg_l"] is not None for r in self.model.rows))

    def test_dashboard_keeps_outage_visible(self):
        blanks = [r for r in self.dashboard.rows if r["do_mg_l"] is None]
        self.assertEqual(len(blanks), 6)  # shown as a gap, not hidden and not invented

    def test_dashboard_fills_ph_longer_than_model(self):
        dash_ph = sum(r["ph"] is not None for r in self.dashboard.rows)
        self.assertEqual(dash_ph, len(self.dashboard.rows))  # 2-hour pH gap bridged
        self.assertEqual(self.model.report["by_reason"].get("not_null:ph"), 6)

    def test_assistant_gets_current_state_only(self):
        self.assertEqual(len(self.assistant.rows), 1)
        latest = max(r["ts"] for r in self.model.rows)
        self.assertEqual(self.assistant.rows[0]["ts"], latest)
        self.assertIn("low_oxygen", self.assistant.columns)
        self.assertNotIn("feed_kg", self.assistant.columns)


class SemiconductorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_pipeline(ROOT / "configs" / "semiconductor_test.toml")
        cls.model = cls.result.profile("capacity_forecast_model")
        cls.dashboard = cls.result.profile("planning_dashboard")

    def test_all_profiles_succeed(self):
        self.assertTrue(self.result.ok, self.result.report["profiles"])

    def test_unknown_product_is_held_back(self):
        for p in self.result.profiles:
            self.assertNotIn("PX-999", {r["product_id"] for r in p.rows})

    def test_negative_inventory_rejected_at_source(self):
        self.assertTrue(all(r["units_on_hand"] >= 0 for r in self.model.rows))

    def test_profiles_differ_on_tolerated_gap(self):
        # Two missing inventory days: the model accepts a one-day stand-in, the dashboard three.
        self.assertEqual(len(self.dashboard.rows) - len(self.model.rows), 1)

    def test_derived_capacity_gap(self):
        r = self.model.rows[0]
        self.assertAlmostEqual(r["capacity_gap_hours"],
                               r["tester_hours"] - r["planned_lots"] * r["test_hours_per_lot"])


class DeliveryTests(unittest.TestCase):
    def test_writes_one_table_per_profile(self):
        result = run_pipeline(ROOT / "configs" / "aquaculture.toml")
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_outputs(result, tmp)
            for name in ("analytics_dashboard", "forecasting_model", "ai_assistant_context",
                         "quarantine", "report"):
                self.assertTrue(paths[name].exists() and paths[name].stat().st_size > 0, name)


if __name__ == "__main__":
    unittest.main()
