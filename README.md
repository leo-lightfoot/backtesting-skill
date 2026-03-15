# Backtesting Skill

<p align="center">
  <img src="https://img.shields.io/badge/AI-Agents-0EA5A4" alt="AI Agents" />
  <img src="https://img.shields.io/badge/Built%20on-Ziplime-0284C7" alt="Built on Ziplime" />
  <img src="https://img.shields.io/badge/Workflow-Schema%20Driven-334155" alt="Schema Driven" />
  <img src="https://img.shields.io/badge/License-MIT-16A34A" alt="MIT License" />
</p>

A schema-driven backtesting framework with a web UI and REST API. Describe your strategy as JSON — the runner handles data ingestion, execution, and diagnostics.

---

## Quick Start

```bash
# 1. Create and activate virtual environment (Python 3.12 or 3.13 required)
py -3.13 -m venv .venv          # Windows
python3.13 -m venv .venv        # macOS / Linux

.venv\Scripts\activate           # Windows
source .venv/bin/activate        # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the web server
uvicorn api.main:app --reload --port 8000

# 4. Open in browser
# http://127.0.0.1:8000
```

---

## Web UI

The primary interface. Start the server and open `http://127.0.0.1:8000` in your browser.

### Starting the Server

```bash
uvicorn api.main:app --reload --port 8000
```

- `--reload` enables hot-reload on code changes (development mode)
- Remove `--reload` for production
- Bind to all interfaces with `--host 0.0.0.0` to make it network-accessible

### Layout

The UI is a two-column dark-theme single-page app:

**Left panel — Strategy Form**
- **Strategy** — dropdown to select a template. Changing the template rebuilds the parameter controls below.
- **Symbols** — comma-separated tickers (e.g. `AAPL, MSFT, NVDA`). Multi-symbol strategies trade all listed tickers as a portfolio; single-symbol strategies use only the first.
- **Benchmark** — a single ticker used as the benchmark for alpha/beta calculations (e.g. `SPY`, `QQQ`). See [Benchmark Warning](#benchmark-warning).
- **Start / End dates** — backtest date range.
- **Initial Cash** — starting capital in USD (default $100,000).
- **Strategy Parameters** — sliders and dropdowns generated dynamically for the selected strategy.
- **Run Backtest** button — submits the job and polls until complete.

**Right panel — Results**
- **Run info bar** — symbol, date range, initial cash, job status.
- **Metric cards** — key stats at a glance (Total Return, Sharpe Ratio, Max Drawdown, Win Rate, Trades, Alpha, Beta, Volatility). Color-coded green/red based on sign.
- **Equity Curve** — Chart.js line chart of portfolio value over time. Green if profitable, red if not.
- **Trade Details** — a key-value grid with extended stats: trade counts, avg hold, avg return, best/worst trade, expectancy, PnL.

### Job Lifecycle

Backtests run asynchronously. The UI polls `GET /jobs/{id}` every 2 seconds. Status flow:

```
pending → queued → running → done | error
```

- `pending` — job created, not yet started
- `queued` — waiting for another job to finish (only one backtest runs at a time)
- `running` — actively executing
- `done` — results available
- `error` — failed; error message shown in the UI

> **Note:** Job results are held in memory and reset when the server restarts. There is no persistence layer by design.

---

## REST API

The web UI talks to a FastAPI backend. You can also call the API directly.

**Base URL:** `http://127.0.0.1:8000`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve the web UI |
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `GET` | `/templates` | List all strategy templates with parameter metadata |
| `POST` | `/backtest` | Submit a backtest job — returns `{job_id, status}` immediately (202) |
| `GET` | `/jobs/{job_id}` | Poll job status and retrieve result when done |

### Submit a Backtest

```bash
curl -X POST http://127.0.0.1:8000/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "template": "rsi_mean_reversion_long_only",
    "symbols": ["AAPL"],
    "frequency": "daily",
    "start": "2018-01-02",
    "end": "2024-12-31",
    "initial_cash": 100000,
    "strategy": {
      "rsi_period": 14,
      "oversold_threshold": 30,
      "exit_rsi": 60
    }
  }'
```

Response:
```json
{"job_id": "a3f2c1d9", "status": "pending"}
```

### Poll for Result

```bash
curl http://127.0.0.1:8000/jobs/a3f2c1d9
```

Returns `status: pending|queued|running` until complete, then:
```json
{
  "job_id": "a3f2c1d9",
  "status": "done",
  "result": { ... full backtest output ... },
  "detail": null,
  "created_at": "2026-03-15T10:00:00+00:00"
}
```

On error:
```json
{"job_id": "a3f2c1d9", "status": "error", "detail": "error message", "result": null}
```

---

## CLI

The CLI runner is the lower-level interface. Useful for scripting, CI, or agent workflows.

```bash
# Single run — output to stdout
python scripts/run_backtest_from_schema.py --schema references/example_rsi_schema.json

# Auto-download missing data bundle, then run
python scripts/run_backtest_from_schema.py --schema references/example_rsi_schema.json --ingest-if-missing

# Write output to file instead of stdout
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_single_schema.json --output results/run1.json

# Grid search with train/test validation split
python scripts/run_backtest_from_schema.py --schema references/example_trend_dip_grid_schema.json

# Validate schema without running the backtest
python scripts/run_backtest_from_schema.py --schema references/example_rsi_schema.json --validate-only
```

| Flag | Description |
|------|-------------|
| `--schema <path>` | Path to schema JSON file (required) |
| `--output <path>` | Write JSON result to file instead of stdout |
| `--ingest-if-missing` | Auto-download Yahoo Finance data if bundle is absent |
| `--validate-only` | Check schema validity without running the backtest |

---

## Schema Format

All backtests are described as JSON in a two-tier human-readable format. The runner normalises it automatically before execution.

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
      "split_date": "2022-01-01",
      "rank_on": "test_sharpe"
    }
  }
}
```

### Top-Level Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `template` | string | required | Strategy template ID (see [Strategies](#strategies)) |
| `symbols` | list[string] | required | Ticker list — e.g. `["AAPL", "MSFT"]` |
| `frequency` | string | `"daily"` | `"daily"` or `"hourly"` |
| `start` | string | required | Start date `YYYY-MM-DD` |
| `end` | string | required | End date `YYYY-MM-DD` |
| `initial_cash` | float | `100000` | Starting capital in USD |
| `strategy` | object | `{}` | Template-specific strategy parameters |
| `advanced` | object | `{}` | Benchmark, execution costs, grid search, validation split |

### Advanced Block

| Field | Default | Description |
|-------|---------|-------------|
| `advanced.benchmark` | same as first symbol | Benchmark ticker for alpha/beta. **Must be one of the ingested symbols.** |
| `advanced.allow_yahoo_ingest` | `false` | Allow auto-downloading data from Yahoo Finance |
| `advanced.execution.slippage_bps` | `5.0` | Slippage in basis points per trade |
| `advanced.execution.commission_per_share` | `0.001` | Commission in USD per share |
| `advanced.execution.volume_limit_fraction` | `0.1` | Max fraction of average daily volume per order |
| `advanced.execution.max_leverage` | `1.0` | Maximum portfolio leverage |

See `references/schema.md` for the complete field reference.

---

## Benchmark Warning

> **The benchmark symbol must be present in your ingested data bundle.**
>
> If you set `"benchmark": "SPY"` but only ingested `AAPL`, the backtest will fail with a `KeyError`. Always set `benchmark` to one of the tickers in your `symbols` list — or to a symbol that was explicitly included in the bundle.
>
> **Safe default:** set `benchmark` to the same ticker as your primary symbol.
>
> ```json
> "symbols": ["AAPL"],
> "advanced": { "benchmark": "AAPL" }
> ```

---

## Strategies

### RSI Mean Reversion — `rsi_mean_reversion_long_only`

**Frequency:** daily | **Multi-symbol:** no (single-symbol)

Enters when RSI dips below an oversold threshold while price remains above a long-term trend filter. Exits when RSI recovers to the exit level or the maximum hold period expires.

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `rsi_period` | `14` | 5–30 | RSI lookback period |
| `oversold_threshold` | `30` | 10–45 | RSI level to trigger entry |
| `exit_rsi` | `60` | 50–80 | RSI level to trigger exit |
| `trend_filter_period` | `200` | 50–300 | SMA period for trend filter (must be above to enter) |
| `max_hold_days` | `20` | 5–60 | Maximum bars to hold before forced exit |

---

### SMA Crossover — `sma_crossover_long_only`

**Frequency:** daily or hourly | **Multi-symbol:** yes (portfolio mode)

Classic moving average crossover. Enters when the short SMA crosses above the long SMA; exits on the reverse cross. Runs as a multi-symbol portfolio with equal-weight allocation across the top-ranked positions.

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `short_ma` | `50` | 5–100 | Short SMA period |
| `long_ma` | `200` | 50–500 | Long SMA period (must be > short_ma) |
| `max_positions` | number of symbols | 1–20 | Maximum concurrent positions |
| `rank_metric` | `"ma_ratio"` | `ma_ratio`, `one_bar_return` | Metric to rank symbols when selecting positions |
| `rebalance_rule` | `"daily"` | `daily`, `weekly`, `monthly` | Portfolio rebalance frequency |

---

### Trend Dip Buy — `trend_dip_buy_long_only`

**Frequency:** daily | **Multi-symbol:** yes (portfolio mode)

Three-MA regime filter: price must be in an uptrend (fast > medium, close > slow, all MAs rising). Enters when price dips to touch a chosen MA and bounces. Exits when price closes below the exit MA. Runs as a portfolio with configurable ranking and rebalancing.

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `fast_ma` | `10` | 5–30 | Fast SMA period |
| `medium_ma` | `20` | 10–60 | Medium SMA period |
| `slow_ma` | `50` | 30–200 | Slow SMA period |
| `entry_on` | `"fast"` | `fast`, `medium`, `slow` | MA to watch for a dip-and-touch entry |
| `exit_below` | `"medium"` | `fast`, `medium`, `slow` | Exit when close falls below this MA |
| `bounce_range_ratio` | `0.5` | 0.1–0.9 | Minimum close position in day's range (0 = low, 1 = high) |
| `slope_lookback` | `5` | 2–20 | Bars to measure MA slope |
| `max_positions` | number of symbols | 1–20 | Maximum concurrent positions |
| `rank_metric` | `"trend_strength"` | `trend_strength`, `close_vs_sma_slow`, `volume_ratio` | Metric for ranking symbols |
| `rebalance_rule` | `"daily"` | `daily`, `weekly`, `monthly` | Portfolio rebalance frequency |

---

## Data Ingestion

Backtests require a local data bundle. Bundles are stored at `~/.ziplime/data` and are specific to the symbol set and date range.

### Auto-Ingest (Recommended)

Set `allow_yahoo_ingest: true` in the schema. The runner checks if the bundle already covers the requested date range and ingests only if needed.

**Via the Web UI:** auto-ingest is always enabled.

**Via the CLI:**
```bash
python scripts/run_backtest_from_schema.py --schema my_schema.json --ingest-if-missing
```

### Manual Ingest

```bash
python scripts/ingest_yahoo_bundle.py \
  --bundle yahoo_1d_aapl \
  --symbols AAPL \
  --start 2018-01-02 \
  --end 2024-12-31 \
  --frequency-minutes 1440
```

| Flag | Default | Description |
|------|---------|-------------|
| `--bundle` | required | Bundle name |
| `--symbols` | required | Space-separated tickers |
| `--start` | required | Start date `YYYY-MM-DD` |
| `--end` | required | End date `YYYY-MM-DD` |
| `--frequency-minutes` | `5` | Bar size in minutes (`1440` = daily) |
| `--data-dir` | `~/.ziplime/data` | Override data directory |

### Bundle Naming

Bundles are named automatically from the schema. For example, a daily backtest of `AAPL` and `MSFT` produces a bundle named `yahoo_1d_aapl_msft`. If you change the symbol list, a new bundle is created.

---

## Output

Every backtest returns a JSON object. The web UI renders a formatted view; the CLI prints raw JSON.

### Core Metrics — `metrics`

| Field | Description |
|-------|-------------|
| `total_return` | Total percentage return over the backtest period |
| `sharpe` | Annualised Sharpe ratio |
| `max_drawdown` | Maximum peak-to-trough drawdown (negative value) |
| `alpha` | Annualised alpha vs. benchmark |
| `beta` | Portfolio beta vs. benchmark |
| `algo_volatility` | Annualised portfolio volatility |
| `ending_portfolio_value` | Final portfolio value in USD |

### Extended Performance — `performance_metrics`

Includes Win Days %, Avg Drawdown, Avg Drawdown Days, Recovery Factor, Profit Factor, and Calmar Ratio.

### Trade Summary — `trade_summary`

| Field | Description |
|-------|-------------|
| `trade_count` | Total number of completed trades |
| `win_rate` | Fraction of trades that were profitable |
| `avg_hold_days` | Average holding period per trade |
| `avg_trade_return` | Average return per trade |
| `expectancy_return` | Expected return per trade (win_rate × avg_win − loss_rate × avg_loss) |
| `best_trade_return` | Best single trade return |
| `worst_trade_return` | Worst single trade return |
| `total_realized_pnl` | Sum of all realised profit/loss |

### Capacity Diagnostics — `capacity_diagnostics`

| Field | Description |
|-------|-------------|
| `avg_daily_turnover` | Average daily portfolio turnover |
| `annualized_turnover` | Annualised turnover |
| `participation_vs_adv_floor` | Estimated participation rate vs. average daily volume |
| `participation_risk` | `low`, `moderate`, or `high` — indicates whether the strategy is tradeable at scale |

### Risk Attribution — `risk_attribution`

| Field | Description |
|-------|-------------|
| `corr_with_benchmark` | Correlation of daily returns with benchmark |
| `beta_up` / `beta_down` | Beta in up vs. down market regimes |
| `capture_up` / `capture_down` | Up/down capture ratios vs. benchmark |
| `rolling_sharpe_63_end` | Rolling 63-day Sharpe at end of period |
| `rolling_vol_20_end` | Rolling 20-day volatility at end of period |
| `rolling_dd_63_end` | Rolling 63-day max drawdown at end of period |

### Practical Assessment — `practical_assessment`

Four qualitative flags designed for AI agent interpretation:

| Field | Description |
|-------|-------------|
| `future_leakage_check` | Whether execution semantics are realistic (bar-close fills, no lookahead) |
| `slippage_commission` | Comment on whether cost assumptions are realistic |
| `overfitting_risk_comment` | Risk of overfitting given parameter space and result concentration |
| `capacity_liquidity_note` | Whether the strategy is liquid enough to trade at the tested size |

### Equity Curve — `equity_curve`

Array of `{date, value}` objects representing portfolio value over time. Used to render the chart in the UI.

```json
"equity_curve": [
  {"date": "2018-01-02", "value": 100000.00},
  {"date": "2018-01-03", "value": 100312.50},
  ...
]
```

---

## Grid Search

Enable grid search to sweep parameter combinations and find optimal settings.

```json
"advanced": {
  "grid_search": {
    "enabled": true,
    "rank_by": "sharpe",
    "top_n": 5,
    "params": {
      "rsi_period": [10, 14, 20],
      "oversold_threshold": [25, 30, 35],
      "exit_rsi": [55, 60, 65]
    }
  }
}
```

Grid mode returns:

- `top_results` — ranked list of the best parameter combinations with full metrics for each
- `stability_diagnostics` — analysis of how concentrated the top results are

### Stability Diagnostics

| Label | Meaning |
|-------|---------|
| `stable` | Top results cluster around similar parameters (CV ≤ 0.10). Strategy is robust. |
| `moderate` | Some variation across top results (CV ≤ 0.25). Reasonable, but test out-of-sample. |
| `fragile` | Top results are highly sensitive to parameter choice (CV > 0.25). Likely overfitting. |
| `insufficient` | Too few results to assess stability. |

---

## Validation Split

Pair with grid search for out-of-sample testing. The dataset is split into a training window (for optimisation) and a test window (for evaluation).

```json
"advanced": {
  "grid_search": {
    "enabled": true,
    "params": { "rsi_period": [10, 14, 20] }
  },
  "validation_split": {
    "enabled": true,
    "method": "date",
    "split_date": "2022-01-01",
    "rank_on": "test_sharpe"
  }
}
```

| Method | Description |
|--------|-------------|
| `"date"` | Split at a specific date — requires `split_date` |
| `"ratio"` | Split by fraction of total bars — requires `train_ratio` (e.g. `0.7`) |

Results include both `train` and `test` blocks. Grid ranking uses `rank_on` (e.g. `test_sharpe`, `test_total_return`).

---

## Project Layout

```
api/
  main.py               FastAPI app — endpoints, job queue, async runner
  templates.py          Strategy metadata for UI rendering and validation
  job_store.py          In-memory job store (pending → queued → running → done/error)

frontend/
  index.html            Single-page web UI (dark theme, Chart.js, vanilla JS)

scripts/
  run_backtest_from_schema.py   Main runner — orchestrates ingestion, execution, metrics
  schema_adapter.py             Translates human-friendly schema to internal ziplime format
  ingest_yahoo_bundle.py        Manual data ingestion helper
  strategies/
    trend_dip_buy.py            Trend dip buy strategy
    sma_crossover.py            SMA crossover strategy
    rsi_mean_reversion.py       RSI mean reversion strategy

references/
  schema.md                     Complete schema and output field reference
  example_rsi_schema.json       RSI mean reversion example with grid search
  example_rsi_aapl_schema.json  RSI example for AAPL
  example_trend_dip_single_schema.json   Trend dip single run
  example_trend_dip_grid_schema.json     Trend dip with grid + validation split
  example_sma_schema.json       SMA crossover example

tests/
  test_runner.py        Unit tests for runner, schema adapter, and all templates
```

---

## Setup

**Python 3.12 or 3.13 required.** `ziplime` does not support 3.11 or earlier.

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

**Dependencies:**

| Package | Purpose |
|---------|---------|
| `ziplime` | Backtesting engine (installed from GitHub) |
| `yfinance` | Market data download |
| `pandas`, `numpy`, `scipy`, `polars` | Data processing and analytics |
| `fastapi`, `uvicorn` | Web server and REST API |
| `aiofiles` | Async file I/O |

---

## Install as an Agent Skill

```bash
npx skills add https://github.com/leo-lightfoot/backtesting-skill -a opencode -y
```

See `SKILL.md` for the full agent workflow guide.

---

## API Docs

FastAPI generates interactive API documentation automatically:

- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

## Running Tests

```bash
python -m pytest tests/test_runner.py -v
```

## Known Limitations

- **One backtest at a time** — the API serialises jobs due to SQLite's single-writer constraint. Concurrent submissions queue up and run sequentially.
- **Job results reset on restart** — the in-memory job store is cleared when the server restarts. Save results to a file if you need persistence.
- **Benchmark must be in the bundle** — setting a benchmark symbol that was not ingested will cause a runtime error. See [Benchmark Warning](#benchmark-warning).
- **No live trading** — the live data and execution interfaces are reserved stubs. The framework is backtest-only.
- **Grid search has no size limit** — large parameter grids (e.g. 5 params × 5 values each = 3,125 runs) will take a long time. Validate your grid size before submitting.
- **Daily data only for multi-year backtests** — Yahoo Finance's intraday history is limited to ~60 days. Long-horizon backtests should use `"frequency": "daily"`.

---

## License

MIT. See `LICENSE`.
