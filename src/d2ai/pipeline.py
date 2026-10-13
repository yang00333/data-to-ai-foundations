"""Running a pipeline from a configuration file.

Every domain runs the same sequence. The shared foundation is built once:

    read sources -> drop duplicates -> source checks -> align in time
    -> join lookup tables

Then each readiness profile prepares the foundation for one downstream use
(an analytics dashboard, a forecasting model, an AI assistant):

    fill gaps as far as that use tolerates -> derive columns -> output checks
    -> select rows -> table checks -> deliver the table and a report

Only the configuration differs between domains and between downstream uses.
"""

from __future__ import annotations

import time
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .align import FieldSpec, align, fill_rows, join_static
from .checks import (TableCheckResult, apply_row_checks, build_row_check, drop_duplicates,
                     run_table_check)
from .expressions import compile_expression, evaluate
from .sources import SourceSpec, read_source

Row = dict[str, Any]


@dataclass
class ProfileResult:
    """The output of one readiness profile: what one downstream use receives."""
    name: str
    description: str
    rows: list[Row]
    quarantine: list[Row]
    columns: list[str]
    report: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.report["status"] == "success"


@dataclass
class RunResult:
    name: str
    profiles: list[ProfileResult]
    source_quarantine: list[Row]
    report: dict[str, Any]
    foundation_rows: int = 0

    @property
    def ok(self) -> bool:
        return self.report["status"] == "success"

    def profile(self, name: str) -> ProfileResult:
        for p in self.profiles:
            if p.name == name:
                return p
        raise KeyError(name)

    # Convenience for single-profile pipelines.
    @property
    def rows(self) -> list[Row]:
        return self.profiles[0].rows


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def _profiles_from_config(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Profiles listed in the config, or one default profile built from top-level settings."""
    if cfg.get("profiles"):
        return cfg["profiles"]
    return [{
        "name": cfg["pipeline"]["name"],
        "description": cfg["pipeline"].get("description", ""),
        "output_checks": cfg.get("output_checks", []),
        "table_checks": cfg.get("table_checks", []),
        "max_quarantine_share": cfg.get("output", {}).get("max_quarantine_share"),
    }]


def run_pipeline(config_path: str | Path, as_of: datetime | None = None) -> RunResult:
    config_path = Path(config_path)
    cfg = load_config(config_path)
    base = config_path.parent
    meta = cfg["pipeline"]
    if as_of is None and meta.get("as_of"):
        as_of = datetime.fromisoformat(meta["as_of"])

    started = time.perf_counter()
    source_quarantine: list[Row] = []
    source_stats: dict[str, dict[str, Any]] = {}
    time_sources: dict[str, list[Row]] = {}
    static_sources: dict[str, list[Row]] = {}

    # Foundation, step 1-3: read, de-duplicate, and check each source once.
    for scfg in cfg["sources"]:
        spec = SourceSpec.from_config(scfg)
        rows, rejected = read_source(spec, base)
        read_count = len(rows) + len(rejected)
        bad = [{**r, "_stage": "parse"} for r in rejected]
        if scfg.get("dedupe_on"):
            rows, dupes = drop_duplicates(rows, scfg["dedupe_on"])
            bad += [{**r, "_stage": "source"} for r in dupes]
        rows, failed = apply_row_checks(rows, [build_row_check(c) for c in scfg.get("checks", [])])
        bad += [{**r, "_stage": "source"} for r in failed]
        for r in bad:
            r.setdefault("_source", spec.name)
        source_quarantine += bad
        source_stats[spec.name] = {
            "rows_read": read_count,
            "rows_passed": len(rows),
            "rows_quarantined": len(bad),
            "by_reason": _count_reasons(bad),
        }
        (static_sources if spec.static else time_sources)[spec.name] = rows

    # Foundation, step 4-5: align once, keeping gaps empty; join lookup tables.
    acfg = cfg["align"]
    keys = list(acfg.get("keys", []))
    fields = [FieldSpec.from_config(f) for f in acfg["fields"]]
    foundation = align(time_sources, acfg["freq"], keys, fields, apply_fill=False)
    joined_cols: list[str] = []
    for jcfg in cfg.get("join", []):
        foundation = join_static(foundation, static_sources[jcfg["source"]], jcfg["on"], jcfg["columns"])
        joined_cols += jcfg["columns"]
    foundation_seconds = time.perf_counter() - started

    base_derive = dict(cfg.get("derive", {}))
    profiles = [
        _run_profile(pcfg, foundation, keys, fields, joined_cols, base_derive, as_of)
        for pcfg in _profiles_from_config(cfg)
    ]

    status = "success" if all(p.ok for p in profiles) else "failed"
    report = {
        "pipeline": meta["name"],
        "domain": meta.get("domain"),
        "status": status,
        "as_of": as_of.isoformat() if as_of else None,
        "sources": source_stats,
        "foundation": {
            "rows": len(foundation),
            "seconds": round(foundation_seconds, 4),
            "built": "once, shared by every profile below",
        },
        "profiles": {p.name: p.report for p in profiles},
        "total_seconds": round(time.perf_counter() - started, 4),
    }
    return RunResult(meta["name"], profiles, source_quarantine, report, len(foundation))


def _run_profile(pcfg: dict[str, Any], foundation: list[Row], keys: list[str],
                 fields: list[FieldSpec], joined_cols: list[str], base_derive: dict[str, str],
                 as_of: datetime | None) -> ProfileResult:
    rows = [dict(r) for r in foundation]

    # Fill: the field's default rule, unless this profile overrides it.
    overrides = pcfg.get("fill", {})
    for f in fields:
        rule = overrides.get(f.name, {"method": f.fill, "limit": f.fill_limit})
        if rule.get("method"):
            rows = fill_rows(rows, keys, f.name, rule["method"], rule.get("limit"))

    derive = {**base_derive, **pcfg.get("derive", {})}
    trees = {name: compile_expression(expr) for name, expr in derive.items()}
    for row in rows:
        for name, tree in trees.items():
            row[name] = evaluate(tree, row)

    checked_count = len(rows)
    rows, failed = apply_row_checks(rows, [build_row_check(c) for c in pcfg.get("output_checks", [])])
    quarantine = [{**r, "_stage": "output", "_source": pcfg["name"]} for r in failed]

    if pcfg.get("select") == "latest":  # the current state of each entity
        latest: dict[tuple, Row] = {}
        for r in rows:
            k = tuple(r.get(c) for c in keys)
            if k not in latest or r["ts"] > latest[k]["ts"]:
                latest[k] = r
        rows = sorted(latest.values(), key=lambda r: tuple(str(r.get(c)) for c in keys))

    results: list[TableCheckResult] = [run_table_check(c, rows, as_of) for c in pcfg.get("table_checks", [])]
    max_share = pcfg.get("max_quarantine_share")
    if max_share is not None and checked_count:
        share = len(failed) / checked_count
        results.append(TableCheckResult(
            "max_quarantine_share", share <= max_share,
            f"{share:.1%} of rows held back (maximum {max_share:.0%})", "fail"))
    status = "failed" if any(not r.passed and r.severity == "fail" for r in results) else "success"

    all_cols = ["ts", *keys, *[f.name for f in fields], *joined_cols, *derive]
    columns = [c for c in all_cols if c in pcfg.get("columns", all_cols)] if pcfg.get("columns") else all_cols
    report = {
        "description": pcfg.get("description", ""),
        "status": status,
        "rows_delivered": len(rows),
        "rows_quarantined": len(failed),
        "by_reason": _count_reasons(failed),
        "time_range": [min(r["ts"] for r in rows).isoformat(),
                       max(r["ts"] for r in rows).isoformat()] if rows else None,
        "columns": columns,
        "table_checks": [r.as_dict() for r in results],
    }
    return ProfileResult(pcfg["name"], pcfg.get("description", ""), rows, quarantine, columns, report)


def _count_reasons(rows: list[Row]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        for reason in str(r.get("_reason", "unknown")).split(";"):
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))
