"""Quality checks.

Row checks decide, row by row, whether data may continue toward the AI
application; failing rows are quarantined with a reason instead of being
silently passed on or silently dropped. Table checks look at the whole result
(is it fresh enough, is there enough of it) and can fail the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

Row = dict[str, Any]


def parse_duration(text: str) -> timedelta:
    """Parse durations such as '15min', '2h', '1d'."""
    text = text.strip().lower()
    units = {"min": "minutes", "m": "minutes", "h": "hours", "d": "days", "s": "seconds"}
    for suffix in sorted(units, key=len, reverse=True):
        if text.endswith(suffix):
            return timedelta(**{units[suffix]: float(text[: -len(suffix)])})
    raise ValueError(f"unknown duration {text!r}")


@dataclass
class RowCheck:
    name: str
    test: Callable[[Row], bool]


def build_row_check(cfg: dict[str, Any]) -> RowCheck:
    kind = cfg["type"]
    col = cfg.get("column")
    label = cfg.get("name") or f"{kind}:{col}"

    if kind == "not_null":
        return RowCheck(label, lambda r: r.get(col) is not None)
    if kind == "range":
        lo, hi = cfg.get("min"), cfg.get("max")

        def in_range(r: Row) -> bool:
            v = r.get(col)
            if v is None:
                return True  # nulls are handled by not_null
            return (lo is None or v >= lo) and (hi is None or v <= hi)

        return RowCheck(label, in_range)
    if kind == "allowed_values":
        allowed = set(cfg["values"])
        return RowCheck(label, lambda r: r.get(col) in allowed)
    raise ValueError(f"unknown row check type {kind!r}")


def apply_row_checks(rows: list[Row], checks: list[RowCheck]) -> tuple[list[Row], list[Row]]:
    passed: list[Row] = []
    quarantined: list[Row] = []
    for row in rows:
        failures = [c.name for c in checks if not c.test(row)]
        if failures:
            quarantined.append({**row, "_reason": ";".join(failures)})
        else:
            passed.append(row)
    return passed, quarantined


def drop_duplicates(rows: list[Row], keys: list[str]) -> tuple[list[Row], list[Row]]:
    """Keep the first row for each key combination; quarantine the rest."""
    seen: set[tuple] = set()
    kept: list[Row] = []
    dupes: list[Row] = []
    for row in rows:
        k = tuple(row.get(c) for c in keys)
        if k in seen:
            dupes.append({**row, "_reason": "duplicate:" + ",".join(keys)})
        else:
            seen.add(k)
            kept.append(row)
    return kept, dupes


@dataclass
class TableCheckResult:
    check: str
    passed: bool
    detail: str
    severity: str  # "fail" stops the run; "warn" is reported only

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.check, "passed": self.passed,
                "severity": self.severity, "detail": self.detail}


def run_table_check(cfg: dict[str, Any], rows: list[Row], as_of: datetime | None) -> TableCheckResult:
    kind = cfg["type"]
    severity = cfg.get("on_fail", "fail")
    if kind == "row_count":
        minimum = int(cfg["min"])
        return TableCheckResult(kind, len(rows) >= minimum,
                                f"{len(rows)} rows (minimum {minimum})", severity)
    if kind == "freshness":
        max_age = parse_duration(cfg["max_age"])
        if not rows or as_of is None:
            return TableCheckResult(kind, False, "no rows or no reference time", severity)
        latest = max(r["ts"] for r in rows)
        age = as_of - latest
        return TableCheckResult(kind, age <= max_age,
                                f"latest {latest.isoformat()}, age {age} (maximum {max_age})", severity)
    if kind == "max_quarantine_share":
        raise ValueError("max_quarantine_share is evaluated by the pipeline")
    raise ValueError(f"unknown table check type {kind!r}")
