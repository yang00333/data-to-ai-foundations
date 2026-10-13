"""Aligning sources that arrive at different rates onto one time grid.

Sensors report every minute, lab records every few hours, planning systems
once a day. AI applications usually need one row per time step (and per
entity, such as a pond or a product). This module builds that grid,
aggregates each source into it, and fills short gaps only where the
configuration allows it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import fmean
from typing import Any

from .checks import parse_duration

Row = dict[str, Any]
_ORIGIN = datetime(2000, 1, 1)

_AGGREGATIONS = {
    "mean": lambda vs: fmean(vs),
    "min": min,
    "max": max,
    "sum": sum,
    "first": lambda vs: vs[0],
    "last": lambda vs: vs[-1],
    "count": len,
}


@dataclass
class FieldSpec:
    source: str
    column: str
    agg: str = "mean"
    output: str | None = None
    fill: str | None = None  # "ffill" or "zero"
    fill_limit: int | None = None  # max steps to carry a value forward

    @property
    def name(self) -> str:
        return self.output or self.column

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "FieldSpec":
        if cfg.get("agg", "mean") not in _AGGREGATIONS:
            raise ValueError(f"unknown aggregation {cfg['agg']!r}")
        return cls(source=cfg["source"], column=cfg["column"], agg=cfg.get("agg", "mean"),
                   output=cfg.get("as"), fill=cfg.get("fill"), fill_limit=cfg.get("fill_limit"))


def floor_time(ts: datetime, step: timedelta) -> datetime:
    steps = (ts - _ORIGIN) // step
    return _ORIGIN + steps * step


def align(sources: dict[str, list[Row]], freq: str, keys: list[str],
          fields: list[FieldSpec], apply_fill: bool = True) -> list[Row]:
    """Align sources onto one grid. With apply_fill=False, gaps stay empty so that each
    readiness profile can decide later how much filling its downstream use tolerates."""
    step = parse_duration(freq)

    # 1. Bucket every value: (field, key tuple, bucket start) -> values in time order.
    buckets: dict[tuple[str, tuple, datetime], list[Any]] = defaultdict(list)
    broadcast: set[str] = set()  # fields whose source has no entity keys (e.g. weather)
    spans: dict[tuple, list[datetime]] = {}  # entity -> [first bucket, last bucket]

    for f in fields:
        rows = sorted(sources[f.source], key=lambda r: r["ts"])
        has_keys = bool(rows) and all(k in rows[0] for k in keys)
        if keys and not has_keys:
            broadcast.add(f.name)
        for r in rows:
            v = r.get(f.column)
            if v is None:
                continue
            k = tuple(r[c] for c in keys) if has_keys else ()
            b = floor_time(r["ts"], step)
            buckets[(f.name, k, b)].append(v)
            if has_keys or not keys:
                span = spans.setdefault(k, [b, b])
                span[0], span[1] = min(span[0], b), max(span[1], b)

    # 2. For each entity, build its grid (the period it reports), aggregate, fill short gaps.
    out: list[Row] = []
    for k in sorted(spans):
        grid: list[datetime] = []
        t = spans[k][0]
        while t <= spans[k][1]:
            grid.append(t)
            t += step
        series: dict[str, list[Any]] = {}
        for f in fields:
            lookup_key = () if f.name in broadcast else k
            agg = _AGGREGATIONS[f.agg]
            values = [agg(buckets[(f.name, lookup_key, b)]) if (f.name, lookup_key, b) in buckets
                      else None for b in grid]
            series[f.name] = _fill(values, f.fill, f.fill_limit) if apply_fill else values
        for i, b in enumerate(grid):
            row: Row = {"ts": b}
            row.update(dict(zip(keys, k)))
            for f in fields:
                row[f.name] = series[f.name][i]
            out.append(row)
    return out


def _fill(values: list[Any], method: str | None, limit: int | None) -> list[Any]:
    if method is None:
        return values
    if method == "zero":
        return [0.0 if v is None else v for v in values]
    if method == "ffill":
        filled: list[Any] = []
        last, gap = None, 0
        for v in values:
            if v is not None:
                last, gap = v, 0
                filled.append(v)
            else:
                gap += 1
                filled.append(last if last is not None and (limit is None or gap <= limit) else None)
        return filled
    raise ValueError(f"unknown fill method {method!r}")


def fill_rows(rows: list[Row], keys: list[str], column: str,
              method: str | None, limit: int | None) -> list[Row]:
    """Fill one column of aligned rows, entity by entity in time order. Returns new rows."""
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[tuple(r.get(k) for k in keys)].append(i)
    out = [dict(r) for r in rows]
    for idxs in groups.values():
        idxs.sort(key=lambda i: rows[i]["ts"])
        filled = _fill([rows[i].get(column) for i in idxs], method, limit)
        for i, v in zip(idxs, filled):
            out[i][column] = v
    return out


def join_static(rows: list[Row], lookup: list[Row], on: list[str], columns: list[str]) -> list[Row]:
    """Attach columns from a lookup table (such as a product master) by key."""
    index = {tuple(r.get(c) for c in on): r for r in lookup}
    joined = []
    for row in rows:
        match = index.get(tuple(row.get(c) for c in on), {})
        joined.append({**row, **{c: match.get(c) for c in columns}})
    return joined
