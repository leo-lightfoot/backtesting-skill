# Backtest Schema

Use this constrained JSON format.

```json
{
  "template": "oversold_bounce_long_only",
  "symbol": "QQQ",
  "bundle": "yahoo_5m_qqq",
  "frequency_minutes": 5,
  "start": "2025-06-10",
  "end": "2025-07-31",
  "timezone": "America/New_York",
  "initial_cash": 100000,
  "benchmark_symbol": "QQQ",
  "data": {
    "source": "bundle",
    "allow_yahoo_ingest": false,
    "symbols": ["QQQ"]
  },
  "params": {
    "ext_10": -0.30,
    "ext_20": -0.40,
    "min_down_days": 3,
    "range_mult": 1.5,
    "stop_buffer": 0.01,
    "max_hold_days": 3,
    "min_price": 5.0,
    "min_avg_daily_volume": 2000000,
    "entry_after_hour": 10,
    "entry_after_minute": 0
  },
  "grid_search": {
    "enabled": false,
    "rank_by": "sharpe",
    "top_n": 5,
    "params": {
      "ext_10": [-0.2, -0.3, -0.4],
      "min_down_days": [3, 4, 5],
      "max_hold_days": [2, 3, 5]
    }
  },
  "validation_split": {
    "enabled": true,
    "method": "date",
    "split_date": "2025-07-01",
    "gap_bars": 0,
    "rank_on": "test_sharpe"
  },
  "live_data": {
    "enabled": false,
    "provider": "ibkr",
    "host": "127.0.0.1",
    "port": 7497,
    "client_id": 1,
    "account": "DUXXXXXX"
  }
}
```

## Required fields
- `template`
- `symbol`
- `bundle`
- `frequency_minutes`
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

## Optional execution and cost config
- `execution.max_leverage` (default `1.0`)
- `execution.same_bar_execution` (default `false`)
- `execution.price_used_in_order_execution` (`open|close|high|low`, default `close`)
- `execution.costs.slippage_bps` (default `5.0`)
- `execution.costs.volume_limit_fraction` (default `0.1`)
- `execution.costs.commission_per_share_usd` (default `0.001`)
- `execution.costs.commission_min_trade_usd` (default `0.0`)

## Optional live interface reservation
- `live_data.enabled`: include live-interface validation output
- `live_data.provider`: currently supports reserved config for `ibkr`
- `live_data.host`, `live_data.port`, `live_data.client_id`, `live_data.account`
- This is a reserved interface only (no live trading runtime in this runner)

## Optional validation split
- `validation_split.enabled`: enable train/test split output
- `validation_split.method`: `date` or `ratio`
- Date method fields:
  - `split_date`: first day in test window
  - `gap_bars` (default `0`): skip bars after split before test starts
- Ratio method fields:
  - `train_ratio` in `(0, 1)`
  - `gap_bars` (default `0`)
- `validation_split.rank_on`:
  - no split: use `grid_search.rank_by`
  - with split: defaults to `test_sharpe`
  - supports `test_<metric>` or `train_<metric>` (for example: `test_sharpe`, `test_total_return`)

## Supported templates
- `oversold_bounce_long_only`
- `sma_crossover_long_only`
- `trend_dip_buy_long_only`

## Reference examples
- `references/example_oversold_schema.json`
- `references/example_sma_schema.json`
- `references/example_trend_dip_single_schema.json`
- `references/example_trend_dip_grid_schema.json`

## Parameter notes
- `oversold_bounce_long_only` uses `params` keys:
  - `ext_10`, `ext_20`, `min_down_days`, `range_mult`, `stop_buffer`, `max_hold_days`
  - optional filters: `min_price`, `min_avg_daily_volume`
- `sma_crossover_long_only` uses:
  - `short_window`, `long_window`
  - portfolio controls: `max_positions`, `rank_metric` (`ma_ratio|one_bar_return`), `rebalance_rule` (`daily|weekly|monthly`)
- `trend_dip_buy_long_only` uses:
  - `sma_fast_period`, `sma_med_period`, `sma_slow_period`, `slope_lookback`
  - `touch_ma` (`sma_fast|sma_med|sma_slow`), `bounce_range_ratio`
  - `exit_below_ma` (`sma_fast|sma_med|sma_slow`)
  - optional filters: `min_price`, `min_avg_daily_volume`
  - portfolio controls: `max_positions`, `rank_metric` (`trend_strength|close_vs_sma_slow|volume_ratio`), `rebalance_rule` (`daily|weekly|monthly`)

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
