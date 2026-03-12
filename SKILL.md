---
name: backtesting-skill
description: Use when a user wants reproducible ziplime backtests from a constrained JSON schema, with optional Yahoo ingestion and optional grid search, in any CLI agent environment.
---

# Backtesting Skill

## Overview
Run ziplime backtests from deterministic templates and a constrained JSON schema.
Map the user strategy into schema fields, run the script, and report results in one standard format.

## Workflow
1. Identify whether the user request maps to a supported template:
   - `oversold_bounce_long_only`
   - `sma_crossover_long_only`
   - `trend_dip_buy_long_only`
2. Build a schema JSON using `references/schema.md`.
3. Run the backtest script:
    - `python scripts/run_backtest_from_schema.py --schema <path-to-schema.json>`
4. If bundle is missing and user allows Yahoo ingestion, run with:
   - `python scripts/run_backtest_from_schema.py --schema <path> --ingest-if-missing`
5. If the user asks for OOS checks, enable `validation_split` in schema and report train/test results explicitly.
6. Return concise results using the global output standard (all templates):
      - Core metrics (`total_return`, `sharpe`, `max_drawdown`, `alpha`, `beta`, `algo_volatility`)
      - Extended performance metrics (`Performance`, `Win Days`, `Sharpe`, `Avg. Drawdown`, `Beta`, `Avg. Drawdown Days`, `Alpha`, `Volatility`, `Recovery Factor`, `Profit Factor`, `Calmar`)
      - Trade summary (`trade_count`, `win_rate`, `avg_hold_days`, `avg_trade_return`, `expectancy_return`, `best_trade_return`, `worst_trade_return`)
      - Capacity diagnostics (`avg_daily_turnover`, `annualized_turnover`, `participation_vs_adv_floor`, `participation_risk`)
      - Risk attribution (`corr_with_benchmark`, up/down beta, up/down capture, rolling risk endpoints)
      - Stability diagnostics for grid runs (`stability_diagnostics`)
      - Final equity
     - Chosen params or top grid-search params
    - Practical tradability assessment (required, brief):
      - Future-leakage check (signal timestamp vs execution semantics)
      - Slippage and commission assumptions, and likely live impact direction
      - Overfitting risk comment (grid size, parameter concentration, need for OOS/walk-forward)
      - Capacity/liquidity note (turnover sensitivity and instrument suitability)

## Global Output Standard (All Runs)
- Apply this output contract to every backtest result, regardless of template or symbol.
- Always include: core metrics, extended metrics, final equity, chosen params/top grid params.
- Always include a brief practical tradability assessment with all 4 checks:
  - future leakage / execution semantics
  - slippage + commission realism
  - overfitting risk
  - capacity/liquidity constraints
- Keep grid search defaults small and fast; only run exhaustive grids when explicitly requested.

## Template Mapping Rules
- If user asks for waterfall/panic-reversal mean reversion and long-only, use `oversold_bounce_long_only`.
- If user asks for moving-average cross long-only, use `sma_crossover_long_only`.
- If user asks for trend-dip long-only with MA regime filter, use `trend_dip_buy_long_only`.
- If request cannot map safely to supported templates, ask for a template-constrained restatement.

## Execution Notes
- Keep `max_leverage=1.0` and no short orders.
- Prefer existing bundles. Only ingest when explicitly requested or enabled.
- Use the same frequency for bundle load and `emission_rate`.
- Use out-of-sample checks by date split when user requests robustness.
- Default to quick, reasonable grid sizes; run exhaustive grids only when explicitly requested.
- Use `execution` schema fields when the user asks to tune slippage, commission, or fill behavior.
- Use `data.symbols` for multi-symbol runs on `sma_crossover_long_only` and `trend_dip_buy_long_only`.
- Use `max_positions`, `rank_metric`, and `rebalance_rule` for lightweight portfolio construction controls.
- Keep runtime `data.source` on `bundle`; treat other data sources as reserved interface checks unless adapter support is added.
- Use `live_data` fields only as reserved interface validation (for example `ibkr`), not for live order execution in this runner.

## Commands
- Single run:
  - `python scripts/run_backtest_from_schema.py --schema schema.json`
- Grid search:
  - set `"grid_search": {"enabled": true, ...}` in schema, then run the same command.
- Optional ingestion path:
  - `python scripts/run_backtest_from_schema.py --schema schema.json --ingest-if-missing`
- Validation-only (no ziplime runtime required):
  - `python scripts/run_backtest_from_schema.py --schema schema.json --validate-only`

## Common Mistakes
- Bundle frequency mismatch (`5m` bundle but daily emission or inverse).
- Running intraday templates against daily-only bundles.
- Expecting Yahoo minute data to cover very long history windows.
- Adding unconstrained custom logic instead of using schema parameters.
