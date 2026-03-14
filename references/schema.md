# Backtest Schema

Use this two-tier human-friendly format. The runner auto-translates it to its internal representation.

```json
{
  "template": "oversold_bounce_long_only",
  "symbols": ["QQQ"],
  "frequency": "5min",
  "start": "2025-06-10",
  "end": "2025-07-31",
  "initial_cash": 100000,

  "strategy": {
    "ema_extension": -0.30,
    "sma_extension": -0.40,
    "min_down_days": 3,
    "max_hold_days": 3,
    "entry_after_hour": 10,
    "entry_after_minute": 0
  },

  "advanced": {
    "benchmark": "QQQ",
    "allow_yahoo_ingest": false,
    "min_price": 5.0,
    "min_daily_volume": 2000000,
    "range_mult": 1.5,
    "stop_buffer": 0.01,

    "execution": {
      "slippage_bps": 5.0,
      "commission_per_share": 0.001
    },

    "grid_search": {
      "enabled": true,
      "rank_by": "sharpe",
      "top_n": 5,
      "params": {
        "ema_extension": [-0.2, -0.3, -0.4],
        "min_down_days": [3, 4, 5],
        "max_hold_days": [2, 3, 5]
      }
    },

    "validation_split": {
      "enabled": false,
      "method": "date",
      "split_date": "2025-07-01",
      "gap_bars": 0,
      "rank_on": "test_sharpe"
    }
  }
}
```

## Required fields
- `template`
- `symbols` (list, e.g. `["QQQ"]`)
- `frequency`: `"daily"` | `"hourly"` | `"5min"` | `"1min"`
- `start`, `end`

## Symbols and portfolio mode
- `data.symbols` can include one or more symbols.
- Multi-symbol portfolio behavior is supported by:
  - `sma_crossover_long_only`
  - `trend_dip_buy_long_only`
- Current implementation uses equal weights across active long signals.
- `oversold_bounce_long_only` remains single-symbol strategy logic.

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
- `benchmark`: benchmark symbol (default: first symbol)
- `timezone`: market timezone (default `America/New_York`)
- `max_positions`: max simultaneous positions
- `rank_by`: asset ranking metric
- `rebalance`: `daily|weekly|monthly`
- `min_price`, `min_daily_volume`: entry filters
- `slope_lookback`, `bounce_range_ratio`: trend-dip specific
- `range_mult`, `stop_buffer`: oversold-bounce specific
- `allow_yahoo_ingest`: auto-download data if bundle is missing

## Supported templates
- `oversold_bounce_long_only`
- `sma_crossover_long_only`
- `trend_dip_buy_long_only`

## Reference examples
- `references/example_oversold_schema.json`
- `references/example_sma_schema.json`
- `references/example_trend_dip_single_schema.json`
- `references/example_trend_dip_grid_schema.json`

## Strategy block parameters

`oversold_bounce_long_only`:
- `ema_extension`, `sma_extension` — extension thresholds (e.g. `-0.30`, `-0.40`)
- `min_down_days`, `max_hold_days`
- `entry_after_hour`, `entry_after_minute` — time gate for entries (24h clock)
- advanced filters: `min_price`, `min_daily_volume`, `range_mult`, `stop_buffer`

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
