"""Reading operational sources into plain rows.

Each source is a CSV file described in the configuration: which column holds
the time, which columns to keep and rename, which are numeric, and which
derived columns to compute (for example, a unit conversion).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .expressions import compile_expression, evaluate

Row = dict[str, Any]


@dataclass
class SourceSpec:
    name: str
    path: str
    time_column: str | None = None
    time_format: str | None = None  # None means ISO 8601
    columns: dict[str, str] = field(default_factory=dict)  # source name -> output name
    numeric: list[str] = field(default_factory=list)
    derive: dict[str, str] = field(default_factory=dict)  # output name -> expression
    static: bool = False  # a lookup table joined on keys, with no time column

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "SourceSpec":
        return cls(
            name=cfg["name"],
            path=cfg["path"],
            time_column=cfg.get("time_column"),
            time_format=cfg.get("time_format"),
            columns=dict(cfg.get("columns", {})),
            numeric=list(cfg.get("numeric", [])),
            derive=dict(cfg.get("derive", {})),
            static=bool(cfg.get("static", False)),
        )


def parse_time(value: str, fmt: str | None) -> datetime:
    value = value.strip()
    if fmt:
        return datetime.strptime(value, fmt)
    return datetime.fromisoformat(value)


def to_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"na", "nan", "null", "none"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_source(spec: SourceSpec, base_dir: Path) -> tuple[list[Row], list[Row]]:
    """Read one source. Returns (rows, rejected) where rejected rows could not be parsed."""
    path = (base_dir / spec.path).resolve()
    derived = {name: compile_expression(expr) for name, expr in spec.derive.items()}
    rows: list[Row] = []
    rejected: list[Row] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for line_no, raw in enumerate(csv.DictReader(handle), start=2):
            row: Row = {}
            if spec.columns:
                for src, dst in spec.columns.items():
                    row[dst] = raw.get(src)
            else:
                row.update(raw)
            if spec.time_column:
                try:
                    row["ts"] = parse_time(raw[spec.time_column], spec.time_format)
                except (KeyError, ValueError):
                    rejected.append({**raw, "_source": spec.name, "_line": line_no,
                                     "_reason": "unparseable time"})
                    continue
            for col in spec.numeric:
                row[col] = to_number(row.get(col))
            for name, tree in derived.items():
                row[name] = evaluate(tree, row)
            rows.append(row)
    return rows, rejected
