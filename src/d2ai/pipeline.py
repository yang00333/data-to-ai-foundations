"""Running a pipeline from a configuration file.

The same sequence runs for every domain:

    read sources -> drop duplicates -> source checks -> align in time
    -> join lookup tables -> derive columns -> output checks -> table checks
    -> deliver the table, the quarantine, and a run report

Only the configuration differs between domains.
"""

from __future__ import annotations

import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .align import FieldSpec, align, join_static
from .checks import (TableCheckResult, apply_row_checks, build_row_check, drop_duplicates,
                     run_table_check)
from .expressions import compile_expression, evaluate
from .sources import SourceSpec, read_source

Row = dict[str, Any]


@dataclass
class RunResult:
    name: str
    rows: list[Row]
    quarantine: list[Row]
    report: dict[str, Any]
    columns: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.report["status"] == "success"


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def run_pipeline(config_path: str | Path, as_of: datetime | None = None) -> RunResult:
    config_path = Path(config_path)
    cfg = load_config(config_path)
    base = config_path.parent
    meta = cfg["pipeline"]
    if as_of is None and meta.get("as_of"):
        as_of = datetime.fromisoformat(meta["as_of"])

    timings: dict[str, float] = {}
    started = time.perf_counter()
    quarantine: list[Row] = []
    source_stats: dict[str, dict[str, Any]] = {}
    time_sources: dict[str, list[Row]] = {}
    static_sources: dict[str, list[Row]] = {}

    # 1-3. Read, de-duplicate, and check each source.
    t0 = time.perf_counter()
    for scfg in cfg["sources"]:
        spec = SourceSpec.from_config(scfg)
        rows, rejected = read_source(spec, base)
        read_count = len(rows) + len(rejected)
        bad = [{**r, "_stage": "parse"} for r in rejected]
        if scfg.get("dedupe_on"):
            rows, dupes = drop_duplicates(rows, scfg["dedupe_on"])
            bad += [{**r, "_stage": "source"} for r in dupes]
        checks = [build_row_check(c) for c in scfg.get("checks", [])]
        rows, failed = apply_row_checks(rows, checks)
        bad += [{**r, "_stage": "source"} for r in failed]
        for r in bad:
            r.setdefault("_source", spec.name)
        quarantine += bad
        source_stats[spec.name] = {
            "rows_read": read_count,
            "rows_passed": len(rows),
            "rows_quarantined": len(bad),
            "by_reason": _count_reasons(bad),
        }
        (static_sources if spec.static else time_sources)[spec.name] = rows
    timings["read_and_check_sources"] = time.perf_counter() - t0

    # 4. Align time-based sources onto one grid.
    t0 = time.perf_counter()
    acfg = cfg["align"]
    keys = list(acfg.get("keys", []))
    fields = [FieldSpec.from_config(f) for f in acfg["fields"]]
    rows = align(time_sources, acfg["freq"], keys, fields)
    timings["align"] = time.perf_counter() - t0

    # 5. Join lookup tables such as a product master.
    joined_cols: list[str] = []
    for jcfg in cfg.get("join", []):
        rows = join_static(rows, static_sources[jcfg["source"]], jcfg["on"], jcfg["columns"])
        joined_cols += jcfg["columns"]

    # 6. Derive output columns from domain rules.
    derived = {name: compile_expression(expr) for name, expr in cfg.get("derive", {}).items()}
    for row in rows:
        for name, tree in derived.items():
            row[name] = evaluate(tree, row)

    # 7. Output row checks: what may reach the AI application.
    t0 = time.perf_counter()
    out_checks = [build_row_check(c) for c in cfg.get("output_checks", [])]
    aligned_count = len(rows)
    rows, failed = apply_row_checks(rows, out_checks)
    quarantine += [{**r, "_stage": "output", "_source": "aligned"} for r in failed]
    timings["output_checks"] = time.perf_counter() - t0

    # 8. Table checks: freshness, volume, and the share of rows held back.
    table_results: list[TableCheckResult] = [run_table_check(c, rows, as_of)
                                             for c in cfg.get("table_checks", [])]
    max_share = cfg.get("output", {}).get("max_quarantine_share")
    if max_share is not None and aligned_count:
        share = len(failed) / aligned_count
        table_results.append(TableCheckResult(
            "max_quarantine_share", share <= max_share,
            f"{share:.1%} of aligned rows quarantined (maximum {max_share:.0%})", "fail"))

    status = "success"
    if any(not r.passed and r.severity == "fail" for r in table_results):
        status = "failed"

    columns = ["ts", *keys, *[f.name for f in fields], *joined_cols, *derived]
    timings["total"] = time.perf_counter() - started
    report = {
        "pipeline": meta["name"],
        "domain": meta.get("domain"),
        "status": status,
        "as_of": as_of.isoformat() if as_of else None,
        "sources": source_stats,
        "output": {
            "rows_aligned": aligned_count,
            "rows_delivered": len(rows),
            "rows_quarantined": len(failed),
            "by_reason": _count_reasons(failed),
            "time_range": [rows[0]["ts"].isoformat(), rows[-1]["ts"].isoformat()] if rows else None,
            "columns": columns,
        },
        "table_checks": [r.as_dict() for r in table_results],
        "timings_seconds": {k: round(v, 4) for k, v in timings.items()},
    }
    return RunResult(meta["name"], rows, quarantine, report, columns)


def _count_reasons(rows: list[Row]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        for reason in str(r.get("_reason", "unknown")).split(";"):
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))
