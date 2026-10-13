"""Show how much of each pipeline is shared code and how much is domain configuration.

Counts non-blank, non-comment lines. This describes this repository's two
synthetic examples; it is not a measurement of effort on a real project.

Run: python scripts/reuse_report.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def count_lines(path: Path, comment: str) -> int:
    n = 0
    in_docstring = False
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if path.suffix == ".py" and s.startswith('"""'):
            if not (s.count('"""') == 2 and len(s) > 3):
                in_docstring = not in_docstring
            continue
        if in_docstring or not s or s.startswith(comment):
            continue
        n += 1
    return n


def main() -> None:
    core = sorted((ROOT / "src" / "d2ai").glob("*.py"))
    core_lines = sum(count_lines(p, "#") for p in core)
    print(f"Shared pipeline code (src/d2ai, {len(core)} files): {core_lines} lines")
    for cfg in sorted((ROOT / "configs").glob("*.toml")):
        lines = count_lines(cfg, "#")
        print(f"  {cfg.stem:<20} domain configuration: {lines:>4} lines "
              f"(new code written for this domain: 0 lines)")


if __name__ == "__main__":
    main()
