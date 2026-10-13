"""Delivering results: the AI-ready table, the quarantine, and the run report."""

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


def write_outputs(result: RunResult, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "table": out / "ai_ready.csv",
        "quarantine": out / "quarantine.csv",
        "report": out / "run_report.json",
    }

    with paths["table"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=result.columns, extrasaction="ignore")
        writer.writeheader()
        for row in result.rows:
            writer.writerow({k: _fmt(row.get(k)) for k in result.columns})

    q_cols: list[str] = ["_stage", "_source", "_reason"]
    for row in result.quarantine:
        for k in row:
            if k not in q_cols:
                q_cols.append(k)
    with paths["quarantine"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=q_cols)
        writer.writeheader()
        for row in result.quarantine:
            writer.writerow({k: _fmt(row.get(k)) for k in q_cols})

    paths["report"].write_text(json.dumps(result.report, indent=2) + "\n", encoding="utf-8")
    return paths
