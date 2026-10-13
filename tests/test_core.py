"""Unit tests for the shared components. Run: python -m unittest discover -s tests"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from d2ai.align import FieldSpec, align, floor_time, join_static  # noqa: E402
from d2ai.checks import (apply_row_checks, build_row_check, drop_duplicates,  # noqa: E402
                         parse_duration, run_table_check)
from d2ai.expressions import ExpressionError, compile_expression, evaluate  # noqa: E402

T0 = datetime(2026, 6, 1, 0, 0)


class ExpressionTests(unittest.TestCase):
    def test_unit_conversion(self):
        tree = compile_expression("(f - 32) * 5 / 9")
        self.assertAlmostEqual(evaluate(tree, {"f": 212}), 100.0)

    def test_missing_input_gives_none(self):
        self.assertIsNone(evaluate(compile_expression("a * b"), {"a": 2, "b": None}))

    def test_division_by_zero_gives_none(self):
        self.assertIsNone(evaluate(compile_expression("a / b"), {"a": 1, "b": 0}))

    def test_rejects_unsafe_code(self):
        for text in ("__import__('os')", "a.b", "open('x')", "[1, 2]"):
            with self.assertRaises(ExpressionError):
                compile_expression(text)


class CheckTests(unittest.TestCase):
    def test_range_quarantines_with_reason(self):
        check = build_row_check({"type": "range", "column": "x", "min": 0, "max": 20, "name": "x_ok"})
        passed, held = apply_row_checks([{"x": 5}, {"x": 45}, {"x": None}], [check])
        self.assertEqual([r["x"] for r in passed], [5, None])
        self.assertEqual(held[0]["_reason"], "x_ok")

    def test_duplicates_keep_first(self):
        kept, dupes = drop_duplicates([{"k": 1, "v": "a"}, {"k": 1, "v": "b"}, {"k": 2, "v": "c"}], ["k"])
        self.assertEqual([r["v"] for r in kept], ["a", "c"])
        self.assertEqual(len(dupes), 1)

    def test_freshness(self):
        rows = [{"ts": T0}, {"ts": T0 + timedelta(minutes=45)}]
        ok = run_table_check({"type": "freshness", "max_age": "30min"}, rows, T0 + timedelta(hours=1))
        late = run_table_check({"type": "freshness", "max_age": "10min"}, rows, T0 + timedelta(hours=1))
        self.assertTrue(ok.passed)
        self.assertFalse(late.passed)

    def test_parse_duration(self):
        self.assertEqual(parse_duration("15min"), timedelta(minutes=15))
        self.assertEqual(parse_duration("2h"), timedelta(hours=2))
        self.assertEqual(parse_duration("1d"), timedelta(days=1))


class AlignTests(unittest.TestCase):
    def test_floor_time(self):
        self.assertEqual(floor_time(T0 + timedelta(minutes=22), timedelta(minutes=15)),
                         T0 + timedelta(minutes=15))

    def test_aggregates_onto_grid_and_fills_within_limit(self):
        fast = [{"ts": T0 + timedelta(minutes=m), "v": float(m)} for m in range(0, 30)]
        slow = [{"ts": T0, "s": 1.0}]
        fields = [FieldSpec("fast", "v", "mean"),
                  FieldSpec("slow", "s", "last", fill="ffill", fill_limit=1)]
        rows = align({"fast": fast, "slow": slow}, "10min", [], fields)
        self.assertEqual([r["v"] for r in rows], [4.5, 14.5, 24.5])
        self.assertEqual([r["s"] for r in rows], [1.0, 1.0, None])  # carried one step only

    def test_source_without_keys_applies_to_every_entity(self):
        a = [{"ts": T0, "pond_id": "P1", "v": 1.0}, {"ts": T0, "pond_id": "P2", "v": 2.0}]
        weather = [{"ts": T0, "air": 30.0}]
        rows = align({"a": a, "w": weather}, "15min", ["pond_id"],
                     [FieldSpec("a", "v"), FieldSpec("w", "air", "last")])
        self.assertEqual({(r["pond_id"], r["air"]) for r in rows}, {("P1", 30.0), ("P2", 30.0)})

    def test_join_static(self):
        rows = join_static([{"p": "A"}, {"p": "Z"}], [{"p": "A", "h": 3.5}], ["p"], ["h"])
        self.assertEqual([r["h"] for r in rows], [3.5, None])


if __name__ == "__main__":
    unittest.main()
