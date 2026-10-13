"""Delivering results: one table per readiness profile, the quarantine, and the run report."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .pipeline import RunResult


def _fmt(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 4)
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k)) for k in columns})


def write_outputs(result: RunResult, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for p in result.profiles:
        paths[p.name] = out / f"{p.name}.csv"
        _write_csv(paths[p.name], p.rows, p.columns)

    held = list(result.source_quarantine)
    for p in result.profiles:
        held += p.quarantine
    q_cols: list[str] = ["_stage", "_source", "_reason"]
    for row in held:
        for k in row:
            if k not in q_cols:
                q_cols.append(k)
    paths["quarantine"] = out / "quarantine.csv"
    _write_csv(paths["quarantine"], held, q_cols)

    paths["report"] = out / "run_report.json"
    paths["report"].write_text(json.dumps(result.report, indent=2) + "\n", encoding="utf-8")
    return paths
