"""Command line: python -m d2ai run <config.toml> [--out DIR]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .deliver import write_outputs
from .pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="d2ai", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a pipeline configuration")
    run.add_argument("config", type=Path)
    run.add_argument("--out", type=Path, default=None, help="output folder (default: out/<name>)")
    args = parser.parse_args(argv)

    result = run_pipeline(args.config)
    out_dir = args.out or Path("out") / result.name
    paths = write_outputs(result, out_dir)

    r = result.report
    print(f"{r['pipeline']}: {r['status']}")
    for name, s in r["sources"].items():
        print(f"  source {name:<22} read {s['rows_read']:>6}  quarantined {s['rows_quarantined']:>4}")
    o = r["output"]
    print(f"  output rows delivered {o['rows_delivered']}, quarantined {o['rows_quarantined']}")
    for c in r["table_checks"]:
        mark = "ok " if c["passed"] else "FAIL"
        print(f"  [{mark}] {c['check']}: {c['detail']}")
    print(f"  wrote {paths['table']}, {paths['quarantine'].name}, {paths['report'].name}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
