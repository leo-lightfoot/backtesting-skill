# Backtesting Skill

Template-driven backtesting for fast strategy idea evaluation.

This project runs reproducible `ziplime` backtests from a constrained JSON schema.
It is designed for Claude Code and other CLI agent environments.

## Scope

- Fast idea-to-backtest workflow
- Long-only strategy templates
- Small, practical grid search by default
- Standardized reporting for performance, stability, risk, and capacity

Not in scope:

- Full portfolio optimization framework
- Live trading execution engine
- Full production data platform

## Install

Python 3.11+ is recommended.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Quick Start

Validate a schema:

```bash
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_single_schema.json --validate-only
```

Run a single backtest:

```bash
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_single_schema.json
```

Run a grid search:

```bash
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_grid_schema.json
```

Ingest Yahoo data when bundle data is missing:

```bash
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_grid_schema.json --ingest-if-missing
```

## Supported Templates

- `oversold_bounce_long_only`
- `sma_crossover_long_only`
- `trend_dip_buy_long_only`

Multi-symbol equal-weight mode is available for:

- `sma_crossover_long_only`
- `trend_dip_buy_long_only`

`oversold_bounce_long_only` remains single-symbol strategy logic.

## Schema Reference

See `references/schema.md` for complete schema fields and output contract.

## Output Contract

Primary output fields:

- `metrics`
- `performance_metrics`
- `trade_summary`
- `capacity_diagnostics`
- `risk_attribution`
- `practical_assessment`

Grid-mode additions:

- `top_results`
- `stability_diagnostics`

When split mode is enabled:

- `validation`
- `train` and `test` blocks

## Data and Live Interface Notes

- Active runtime data source: `data.source = "bundle"`
- Reserved data interfaces: `csv`, `parquet`, `custom` (schema-level placeholders)
- Reserved live interface: `live_data` (for example `ibkr`) is config validation only

## Project Layout

- `SKILL.md`: skill behavior and workflow
- `references/schema.md`: schema and output reference
- `references/example_*.json`: runnable examples
- `scripts/run_backtest_from_schema.py`: runner
- `scripts/ingest_yahoo_bundle.py`: optional ingestion helper

## License

MIT. See `LICENSE`.
