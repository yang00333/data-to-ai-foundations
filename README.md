# Data-to-AI Foundations

A small, dependency-free reference implementation of a reusable data foundation for AI applications.

Most AI projects do not stall on the model. They stall on the data underneath it: sources that report at different rates, in different units, with gaps, faults, and duplicates. Teams usually rebuild that layer from scratch for every new application. This repository shows the alternative in working code: **the parts that repeat are written once, and the parts that differ are configuration.**

- **Shared core** (`src/d2ai/`): read sources, drop duplicates, check quality, align onto one time grid, join lookup tables, derive columns, check the result, deliver it, and report on the run.
- **Domain rules** (`configs/*.toml`): which sources, which units, which ranges are physically possible, how long a reading may be carried forward, what must never reach the model.

Two examples run on the same core with no domain-specific code:

| Example | Data (synthetic) | Output for the AI application |
|---|---|---|
| Aquaculture | Dissolved-oxygen, pH, and temperature sensors on different schedules; farm weather; a hand-kept feeding log | One row per pond per 15 minutes for dissolved-oxygen forecasting and risk alerts |
| Semiconductor testing | Material inventory, test plan, tester capacity, product master | One row per product per day for capacity and material-shortage forecasting |

Project site: https://yang00333.github.io/data-to-ai-foundations/

## Quick start

Requires Python 3.11 or later. No packages to install.

```bash
git clone https://github.com/yang00333/data-to-ai-foundations.git
cd data-to-ai-foundations
PYTHONPATH=src python -m d2ai run configs/aquaculture.toml
PYTHONPATH=src python -m d2ai run configs/semiconductor_test.toml
python -m unittest discover -s tests
```

Each run writes three files to `out/<pipeline name>/`:

- `ai_ready.csv`: the table the AI application reads
- `quarantine.csv`: every row that was held back, with the stage and the reason
- `run_report.json`: what was read, what was held back and why, freshness, volume, and timings

Sample outputs are committed in `examples/*/sample_output/`.

## What the examples deliberately get wrong

The synthetic data imitate problems real operational data have, so the checks have something to catch.

**Aquaculture** (`examples/aquaculture/generate.py`)

| Problem in the data | Rule in `configs/aquaculture.toml` | Result |
|---|---|---|
| Dissolved-oxygen sensor reports 45 mg/L (impossible) six times | Range check 0–20 mg/L at the source | Faulty readings quarantined before they can distort averages |
| Temperature probe reports Fahrenheit | Derived column `(water_temp_f - 32) * 5 / 9` | Model receives Celsius |
| 90-minute oxygen sensor outage | No fill allowed for oxygen | Six 15-minute rows held back instead of invented |
| 2-hour pH gap | pH may be carried forward 30 minutes | Short gaps filled; the rest held back |
| Weather has no pond column | Sources without entity keys apply to every pond | Weather joined to each pond's rows |
| Duplicate records, unreadable timestamp | De-duplication and parse rejection | Quarantined with reasons |

**Semiconductor testing** (`examples/semiconductor_test/generate.py`)

| Problem in the data | Rule in `configs/semiconductor_test.toml` | Result |
|---|---|---|
| Negative inventory entry | Inventory must be ≥ 0 | Rejected at the source |
| Missing inventory day | A snapshot may stand in for one day, not more | Gap covered by the previous day's snapshot |
| Plan line exported twice | De-duplicate on date and product | Duplicate quarantined |
| Product not in the product master | Only known products may reach the model | Held back, with every missing field listed |

## How the code maps to the reference architecture

| Layer | Where it lives |
|---|---|
| Source and ingestion | `sources.py`: CSV connectors, time parsing, column mapping, numeric casting |
| Integration and transformation | `align.py` (time grid, aggregation, bounded gap filling, lookup joins); `expressions.py` (safe derived columns) |
| Validation and quality | `checks.py`: row checks with quarantine; table checks for freshness, volume, and share held back |
| Orchestration | `pipeline.py`: the fixed sequence every domain runs; in production the run itself would be scheduled by an orchestrator such as Airflow |
| Delivery and AI consumption | `deliver.py`: the AI-ready table and the quarantine |
| Observability | `run_report.json`: counts and reasons per source, freshness, timings, pass/fail status |

## Reuse in this repository

```
$ python scripts/reuse_report.py
Shared pipeline code (src/d2ai, 8 files): 505 lines
  aquaculture          domain configuration:  117 lines (new code written for this domain: 0 lines)
  semiconductor_test   domain configuration:   89 lines (new code written for this domain: 0 lines)
```

This describes the two synthetic examples here. It is not a claim about effort on any real project.

## Adding a domain

1. Put the source files somewhere the configuration can reach.
2. Copy a configuration from `configs/` and describe the sources, the grid (`freq`, `keys`), the fields and how each is aggregated and filled, the derived columns, and the checks.
3. Run it. If a rule cannot be expressed, that is a signal the shared core needs a new capability, which is how the core grows.

## Scope

- All data in this repository are synthetic. Nothing here comes from any employer, client, or customer.
- This is a reference implementation for reading, running, and adapting. It favors clarity over throughput and uses only the Python standard library.
- Part of the Data-to-AI Foundations project by Yang Chen.

## License

MIT. See [LICENSE](LICENSE).
