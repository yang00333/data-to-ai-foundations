# Data-to-AI Foundations

A small, dependency-free reference implementation of a reusable data foundation for AI applications.

Most AI projects do not stall on the model. They stall on the data underneath it: sources that report at different rates, in different units, with gaps, faults, and duplicates. That data is usually prepared separately for each industry, and then again for each downstream use: a dashboard, a machine-learning model, and an AI application each need it in a different state. This repository separates those two dimensions in working code: **the parts that repeat are written once, and the parts that differ are configuration.**

- **Shared core** (`src/d2ai/`): read sources, drop duplicates, check quality, align onto one time grid, and join lookup tables. This foundation is built once per run.
- **Domain rules** (`configs/*.toml`): which sources, which units, which ranges are physically possible.
- **Readiness profiles** (also in the configuration): what each downstream use requires from the same foundation, such as how far a gap may be filled, which values must be present, how fresh the data must be, and whether the user needs history or only the current state.

Two examples run on the same core with no domain-specific code:

| Example | Data (synthetic) | Readiness profiles built from one foundation |
|---|---|---|
| Aquaculture | Dissolved-oxygen, pH, and temperature sensors on different schedules; farm weather; a hand-kept feeding log | **Analytics dashboard**: every 15-minute row, gaps left visible. **Forecasting model**: only complete rows, no invented oxygen values. **AI assistant context**: the current state of each pond, with a low-oxygen flag |
| Semiconductor testing | Material inventory, test plan, tester capacity, product master | **Planning dashboard**: an inventory snapshot may stand in for up to three missing days. **Capacity forecast model**: known products only, every input present |

## What "AI-ready" means here

Data counts as AI-ready when it meets six conditions, each checked on every run:

1. **Every value is believable.** Impossible readings are set aside before they can distort an average.
2. **Everything is on one clock.** Sources that report at different rates are lined up on the same time steps.
3. **Units and formats agree.** Conversions are rules in the configuration, not hidden in code.
4. **Missing data stays missing.** Gaps are marked; nothing is invented to fill them.
5. **Each use gets what it needs.** A dashboard, a model, and an AI assistant each receive the data in the state they require, from the same checked foundation.
6. **Every change is on record.** Each run reports what every source sent, what was held back, and why.

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

Each run writes to `out/<pipeline name>/`:

- one CSV per readiness profile, for example `analytics_dashboard.csv`, `forecasting_model.csv`, `ai_assistant_context.csv`
- `quarantine.csv`: every row that was held back, with the stage, the profile, and the reason
- `run_report.json`: what each source sent, what was held back and why, the shared foundation, and the checks and results for each profile

Sample outputs are committed in `examples/*/sample_output/`.

## What the examples deliberately get wrong

The synthetic data imitate problems real operational data have, so the checks have something to catch.

**Aquaculture** (`examples/aquaculture/generate.py`)

| Problem in the data | Rule in `configs/aquaculture.toml` | Result |
|---|---|---|
| Dissolved-oxygen sensor reports 45 mg/L (impossible) six times | Range check 0–20 mg/L at the source | Faulty readings quarantined before they can distort averages |
| Temperature probe reports Fahrenheit | Derived column `(water_temp_f - 32) * 5 / 9` | Model receives Celsius |
| 90-minute oxygen sensor outage | No fill allowed for oxygen | The model holds six rows back; the dashboard shows them as a gap; nothing is invented |
| 2-hour pH gap | The model may carry pH 30 minutes; the dashboard may carry it 2 hours | The dashboard bridges the gap; the model holds those rows back |
| Weather has no pond column | Sources without entity keys apply to every pond | Weather joined to each pond's rows |
| Duplicate records, unreadable timestamp | De-duplication and parse rejection | Quarantined with reasons |

**Semiconductor testing** (`examples/semiconductor_test/generate.py`)

| Problem in the data | Rule in `configs/semiconductor_test.toml` | Result |
|---|---|---|
| Negative inventory entry | Inventory must be ≥ 0 | Rejected at the source |
| Two missing inventory days | The model accepts a one-day stand-in; the dashboard accepts three | The dashboard covers both days; the model holds the second back |
| Plan line exported twice | De-duplicate on date and product | Duplicate quarantined |
| Product not in the product master | Only known products may reach the model | Held back, with every missing field listed |

## How the code maps to the reference architecture

| Layer | Where it lives |
|---|---|
| Source and ingestion | `sources.py`: CSV connectors, time parsing, column mapping, numeric casting |
| Integration and transformation | `align.py` (time grid, aggregation, bounded gap filling, lookup joins); `expressions.py` (safe derived columns) |
| Validation and quality | `checks.py`: row checks with quarantine; table checks for freshness, volume, and share held back |
| Orchestration | `pipeline.py`: builds the shared foundation once, then runs each readiness profile; in production the run itself would be scheduled by an orchestrator such as Airflow |
| Delivery and AI consumption | `deliver.py`: one table per readiness profile, plus the quarantine |
| Observability | `run_report.json`: counts and reasons per source, freshness, timings, pass/fail status |

## Reuse in this repository

```
$ python scripts/reuse_report.py
Shared pipeline code (src/d2ai, 8 files): 507 lines
  aquaculture          domain configuration:  148 lines (new code written for this domain: 0 lines)
  semiconductor_test   domain configuration:  103 lines (new code written for this domain: 0 lines)
```

Two domains and five readiness profiles run on the same shared code. These counts describe the synthetic examples in this repository.

## Adding a domain

1. Put the source files somewhere the configuration can reach.
2. Copy a configuration from `configs/` and describe the sources, the grid (`freq`, `keys`), and the fields and how each is aggregated.
3. Add a readiness profile for each downstream use: how far gaps may be filled, the derived columns it needs, the checks its rows must pass, and whether it needs history or only the latest state.
4. Run it. If a rule cannot be expressed, that is a signal the shared core needs a new capability, which is how the core grows.

## Scope

- All data in this repository are synthetic. Nothing here comes from any employer, client, or customer.
- This is a reference implementation for reading, running, and adapting. It favors clarity over throughput and uses only the Python standard library.
- Part of the Data-to-AI Foundations project by Yang Chen.

## License

MIT. See [LICENSE](LICENSE).
