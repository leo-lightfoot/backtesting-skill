# Backtesting Skill

<p align="center">
  <img src="https://img.shields.io/badge/AI-Agents-0EA5A4" alt="AI Agents" />
  <img src="https://img.shields.io/badge/Built%20on-Ziplime-0284C7" alt="Built on Ziplime" />
  <img src="https://img.shields.io/badge/Workflow-Schema%20Driven-334155" alt="Schema Driven" />
  <img src="https://img.shields.io/badge/License-MIT-16A34A" alt="MIT License" />
</p>

A schema-driven backtesting skill for AI agents. Write a JSON schema describing your strategy — the runner handles data, execution, and diagnostics.

## Setup

**Python 3.12 or 3.13 required** (`ziplime` does not support 3.11).

**Windows:**
```bash
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running a Backtest

Pick any example schema and run it:

```bash
# Single run
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_single_schema.json

# Grid search with validation split
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_grid_schema.json

# Validate schema without running
python scripts/run_backtest_from_schema.py --schema references/example_rsi_schema.json --validate-only

# Auto-download data if bundle is missing (requires allow_yahoo_ingest: true in schema)
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_single_schema.json --ingest-if-missing
```

## Schema Format

Schemas use a two-tier human-readable format. The runner translates it automatically.

```json
{
  "template": "trend_dip_buy_long_only",
  "symbols": ["QQQ"],
  "frequency": "daily",
  "start": "2018-01-02",
  "end": "2026-03-10",
  "initial_cash": 100000,

  "strategy": {
    "fast_ma": 8,
    "medium_ma": 20,
    "slow_ma": 50,
    "entry_on": "medium",
    "exit_below": "medium"
  },

  "advanced": {
    "benchmark": "QQQ",
    "allow_yahoo_ingest": true,
    "execution": {
      "slippage_bps": 5.0,
      "commission_per_share": 0.001
    },
    "grid_search": {
      "enabled": false,
      "rank_by": "sharpe",
      "top_n": 5,
      "params": {}
    },
    "validation_split": {
      "enabled": false,
      "method": "date",
      "split_date": "2023-01-01",
      "rank_on": "test_sharpe"
    }
  }
}
```

See `references/schema.md` for all fields. See `references/example_*.json` for ready-to-run examples.

## Output

Every run returns a JSON object with:

- `metrics` — total return, Sharpe, max drawdown, alpha, beta, volatility
- `performance_metrics` — extended performance stats
- `trade_summary` — trade count, win rate, avg hold, best/worst trade
- `capacity_diagnostics` — turnover, participation vs ADV
- `risk_attribution` — beta up/down, capture ratios, rolling risk
- `practical_assessment` — future leakage check, slippage realism, overfitting risk

Grid mode adds `top_results` and `stability_diagnostics`.

## Supported Templates

| Template | Frequency | Multi-symbol |
|---|---|---|
| `trend_dip_buy_long_only` | daily | yes |
| `sma_crossover_long_only` | any | yes |
| `rsi_mean_reversion_long_only` | daily | no |
| `oversold_bounce_long_only` | intraday | no |

## Install as an Agent Skill

```bash
npx skills add https://github.com/garroshub/backtesting-skill -a opencode -y
```

## Project Layout

```
scripts/
  run_backtest_from_schema.py   main runner
  schema_adapter.py             translates human-friendly schema to internal format
  ingest_yahoo_bundle.py        optional data ingestion helper
  strategies/
    trend_dip_buy.py
    sma_crossover.py
    rsi_mean_reversion.py
    oversold_bounce.py
references/
  schema.md                     full schema and output reference
  example_*.json                runnable example schemas
tests/
  test_runner.py                unit tests for runner and all templates
```

## License

MIT. See `LICENSE`.
