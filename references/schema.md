# Backtest Schema

Use this two-tier human-friendly format. The runner auto-translates it to its internal representation.

```json
{
  "template": "rsi_mean_reversion_long_only",
  "symbols": ["AAPL"],
  "frequency": "daily",
  "start": "2018-01-02",
  "end": "2024-12-31",
  "initial_cash": 100000,

  "strategy": {
    "rsi_period": 14,
    "oversold_threshold": 30,
    "exit_rsi": 60,
    "trend_filter_period": 200,
    "max_hold_days": 20
  },

  "advanced": {
    "benchmark": "AAPL",
    "allow_yahoo_ingest": true,
    "min_price": 5.0,
    "min_daily_volume": 2000000,

    "execution": {
      "slippage_bps": 5.0,
      "commission_per_share": 0.001
    },

    "grid_search": {
      "enabled": false,
      "rank_by": "sharpe",
      "top_n": 5,
      "params": {
        "rsi_period": [10, 14, 20],
        "oversold_threshold": [25, 30, 35]
      }
    },

    "validation_split": {
      "enabled": false,
      "method": "date",
      "split_date": "2022-01-03",
      "gap_bars": 0,
      "rank_on": "test_sharpe"
    }
  }
}
```

## Required fields
- `template`
- `symbols` (list, e.g. `["QQQ"]`)
- `frequency`: `"daily"` | `"hourly"`
- `start`, `end`

## Symbols and portfolio mode
- `data.symbols` can include one or more symbols.
- Multi-symbol portfolio behavior is supported by:
  - `sma_crossover_long_only`
  - `trend_dip_buy_long_only`
- Current implementation uses equal weights across active long signals.
- `rsi_mean_reversion_long_only` is single-symbol only; only the first symbol is used.

## Benchmark warning
The `benchmark` symbol must be present in the ingested data bundle. Always set it to one of the symbols in your `symbols` list. Setting a benchmark not in the bundle will cause a runtime error.

## Data source interface
- `data.source = "bundle"` is active at runtime.
- Reserved interfaces (schema-level placeholders):
  - `data.source = "csv"`
  - `data.source = "parquet"`
  - `data.source = "custom"`
- Reserved interfaces are validated and reported in output, but not executed by this runner.

## Optional advanced config

**Execution costs** (`advanced.execution`):
- `slippage_bps` (default `5.0`)
- `commission_per_share` (default `0.001`)

**Grid search** (`advanced.grid_search`):
- `enabled`: run a parameter sweep
- `rank_by`: metric to rank results (`sharpe`, `total_return`, etc.)
- `top_n`: number of top results to return
- `params`: dict of human-friendly param name → list of values to sweep

**Validation split** (`advanced.validation_split`):
- `enabled`: enable train/test split output
- `method`: `date` or `ratio`
- Date method: `split_date` (first day of test window), `gap_bars` (default `0`)
- Ratio method: `train_ratio` in `(0, 1)`, `gap_bars` (default `0`)
- `rank_on`: defaults to `test_sharpe`; supports `test_<metric>` or `train_<metric>`

**Filters and portfolio** (`advanced`):
- `benchmark`: benchmark symbol (default: first symbol) — **must be one of the ingested symbols**
- `timezone`: market timezone (default `America/New_York`)
- `max_positions`: max simultaneous positions
- `rank_by`: asset ranking metric
- `rebalance`: `daily|weekly|monthly`
- `min_price`, `min_daily_volume`: entry filters
- `slope_lookback`, `bounce_range_ratio`: trend-dip specific
- `allow_yahoo_ingest`: auto-download data if bundle is missing

## Supported templates
- `rsi_mean_reversion_long_only`
- `sma_crossover_long_only`
- `trend_dip_buy_long_only`

## Reference examples
- `references/example_rsi_schema.json`
- `references/example_rsi_aapl_schema.json`
- `references/example_sma_schema.json`
- `references/example_trend_dip_single_schema.json`
- `references/example_trend_dip_grid_schema.json`

## Strategy block parameters

`rsi_mean_reversion_long_only`:
- `rsi_period`, `oversold_threshold`, `exit_rsi`
- `trend_filter_period` — SMA period for trend filter (price must be above to enter)
- `max_hold_days` — maximum bars to hold before forced exit
- advanced filters: `min_price`, `min_daily_volume`

`sma_crossover_long_only`:
- `short_ma`, `long_ma`
- advanced portfolio controls: `max_positions`, `rank_by` (`ma_ratio|one_bar_return`), `rebalance` (`daily|weekly|monthly`)

`trend_dip_buy_long_only`:
- `fast_ma`, `medium_ma`, `slow_ma`
- `entry_on` (`fast|medium|slow`), `exit_below` (`fast|medium|slow`)
- advanced: `slope_lookback`, `bounce_range_ratio`
- advanced filters: `min_price`, `min_daily_volume`
- advanced portfolio controls: `max_positions`, `rank_by` (`trend_strength|close_vs_sma_slow|volume_ratio`), `rebalance` (`daily|weekly|monthly`)

## Output
The runner prints JSON with:
- `mode`: single or grid
- `metrics`: total_return, sharpe, max_drawdown, alpha, beta, algo_volatility, ending_portfolio_value
- `performance_metrics`: Performance, Win Days, Sharpe, Avg. Drawdown, Beta, Avg. Drawdown Days, Alpha, Volatility, Recovery Factor, Profit Factor, Calmar
- `trade_summary`: trade_count, win_rate, avg_hold_days, avg_trade_return, avg_win_return, avg_loss_return, expectancy_return, best_trade_return, worst_trade_return, total_realized_pnl
- `capacity_diagnostics`: avg_daily_trade_notional, avg_portfolio_value, avg_daily_turnover, annualized_turnover, adv_floor_dollar, participation_vs_adv_floor, participation_risk
- `risk_attribution`: corr_with_benchmark, beta_up/down, capture_up/down, regime averages, rolling risk endpoints
- `practical_assessment`: future_leakage, slippage_commission, overfitting_risk, capacity_liquidity
- `equity_curve`: list of `{date, value}` portfolio value points for charting
- `data_interface`: data source status and missing required fields for reserved interfaces
- `live_interface`: reserved interface status and missing required fields when `live_data.enabled=true`
- `validation`: split config and train/test windows when enabled
- `params` for single run
- `top_results` for grid mode

Grid-level additions:
- `stability_diagnostics`: top-k stability summary and parameter concentration
- `capacity_diagnostics`: diagnostics for the best-ranked run

Grid rows include `rank_value` for the active ranking metric.

When split is enabled:
- single mode includes `train` and `test` result blocks
- grid mode includes `train` and `test` blocks inside each row and ranks by `validation_split.rank_on`

## Global Reporting Standard (Assistant Output, All Templates)
- For every run (single/grid, any template), the assistant report must include:
  - core metrics + extended metrics + final equity
  - chosen params (single) or top params (grid)
  - practical tradability assessment (brief, required):
    - future-leakage and execution-semantics check
    - slippage/commission realism and likely live impact direction
    - overfitting risk (grid size, parameter concentration, need for OOS/walk-forward)
    - capacity/liquidity note (turnover sensitivity, instrument suitability)
- Default grid sizing policy: quick/reasonable first, exhaustive only on explicit user request.
