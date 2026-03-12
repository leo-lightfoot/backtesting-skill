# Backtesting Skill

Run reproducible `ziplime` backtests from a constrained JSON schema.

This package is designed to work in Claude Code and other CLI agent environments.

## What is included

- `SKILL.md`: Skill-level workflow and reporting rules
- `references/schema.md`: Schema reference and output contract
- `references/example_oversold_schema.json`: Oversold bounce example
- `references/example_sma_schema.json`: SMA crossover example
- `references/example_trend_dip_single_schema.json`: Trend-dip single-run example
- `references/example_trend_dip_grid_schema.json`: Trend-dip grid-search example
- `scripts/run_backtest_from_schema.py`: Main runner
- `scripts/ingest_yahoo_bundle.py`: Optional Yahoo bundle ingestion helper

## Supported templates

- `oversold_bounce_long_only`
- `sma_crossover_long_only`
- `trend_dip_buy_long_only`

Multi-symbol equal-weight portfolio mode is available for:

- `sma_crossover_long_only`
- `trend_dip_buy_long_only`

`oversold_bounce_long_only` remains single-symbol logic.

Portfolio controls for the two multi-symbol templates:

- `params.max_positions`
- `params.rank_metric`
- `params.rebalance_rule` (`daily|weekly|monthly`)

## Quick start

1. Validate a schema:

```bash
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_single_schema.json --validate-only
```

2. Run a single backtest:

```bash
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_single_schema.json
```

3. Run a grid search:

```bash
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_grid_schema.json
```

The grid example includes `validation_split`, so each trial returns train and test blocks and ranking uses test metrics.

4. Ingest Yahoo data when a bundle is missing:

```bash
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_grid_schema.json --ingest-if-missing
```

## Output

The runner prints JSON.

Core fields:

- `mode`
- `backtest_window`
- `metrics`
- `performance_metrics`
- `trade_summary`
- `capacity_diagnostics`
- `risk_attribution`
- `practical_assessment`
- `data_interface`
- `live_interface` (when `live_data.enabled` is true)
- `validation` (when split is enabled)

Run-specific fields:

- single run: `params`
- grid run: `rank_by`, `total_trials`, `top_results`

Grid-level diagnostics:

- `stability_diagnostics`
- `capacity_diagnostics` (from the best-ranked run)

Grid rows include `rank_value` for the active ranking metric.

When split is enabled:

- single run: `train` and `test` blocks
- grid run: each row includes `train` and `test` blocks

`practical_assessment` always includes:

- `future_leakage`
- `slippage_commission`
- `overfitting_risk`
- `capacity_liquidity`

## Grid policy

Default policy is small and fast grid search.

Use larger exhaustive grids only when explicitly requested.

## Notes

- Keep strategy frequency and bundle frequency aligned.
- For daily strategies, use daily bundles and `frequency_minutes: 1440`.
- Keep `max_leverage=1.0` for long-only templates.
- Use `execution` fields in schema to tune slippage, commission, leverage, and fill semantics.
