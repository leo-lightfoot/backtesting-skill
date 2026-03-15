"""
schema_adapter.py

Translates the human-friendly two-tier schema format into the internal
format expected by run_backtest_from_schema.py.

A schema is in the new format when it contains a "strategy" key.
A schema already in the internal format is returned unchanged.

New format fields
-----------------
Top level (required):
  template        str   — same as internal
  symbols         list  — e.g. ["QQQ"] or ["QQQ", "SPY"]
  frequency       str   — "daily" | "5min" | "1min" | "hourly"
  start           str   — "YYYY-MM-DD"
  end             str   — "YYYY-MM-DD"
  initial_cash    float — e.g. 100000

strategy block (template-specific, human-readable names):
  trend_dip_buy_long_only:
    fast_ma         int    — fast SMA period
    medium_ma       int    — medium SMA period
    slow_ma         int    — slow SMA period
    entry_on        str    — "fast" | "medium" | "slow"
    exit_below      str    — "fast" | "medium" | "slow"

  sma_crossover_long_only:
    short_ma        int    — short SMA period
    long_ma         int    — long SMA period

  oversold_bounce_long_only:
    ema_period        int    — EMA period for extension calc
    sma_period        int    — SMA period for extension calc
    ema_extension     float  — e.g. -0.30 (how far below EMA to trigger)
    sma_extension     float  — e.g. -0.40 (how far below SMA to trigger)
    min_down_days     int    — consecutive down days required
    max_hold_days     int    — max bars to hold position
    entry_after_hour  int    — hour after which entries are allowed (24h, e.g. 10)
    entry_after_minute int   — minute after which entries are allowed (e.g. 0)

advanced block (optional):
  benchmark         str    — benchmark symbol, e.g. "QQQ"
  timezone          str    — e.g. "America/New_York"
  max_positions     int    — max simultaneous positions
  rank_by           str    — how to rank assets
  rebalance         str    — "daily" | "weekly" | "monthly"
  min_price         float  — minimum price filter
  min_daily_volume  int    — minimum avg daily volume filter
  slope_lookback    int    — bars to measure MA slope
  bounce_range_ratio float — min close position within day range
  range_mult        float  — intraday range multiplier (oversold)
  stop_buffer       float  — stop loss buffer (oversold)
  allow_yahoo_ingest bool  — allow auto-download of data

  execution:
    slippage_bps         float — slippage in basis points
    commission_per_share float — commission per share in USD

  grid_search:
    enabled   bool  — run a parameter sweep
    rank_by   str   — metric to rank results by, e.g. "sharpe"
    top_n     int   — number of top results to return
    params    dict  — param name (human-friendly) → list of values to try
                      e.g. { "fast_ma": [5, 8, 10], "medium_ma": [20, 30] }

  validation_split:
    enabled     bool   — enable train/test split
    method      str    — "date" | "ratio"
    split_date  str    — first day of test window (method=date)
    train_ratio float  — fraction of window used for training (method=ratio)
    gap_bars    int    — bars to skip between train and test (default 0)
    rank_on     str    — metric to rank grid results by, e.g. "test_sharpe"
"""

from typing import Any

_FREQUENCY_MAP = {
    "daily":  (1440, "1d"),
    "hourly": (60,   "1h"),
    "5min":   (5,    "5m"),
    "1min":   (1,    "1m"),
}

_MA_NAME_MAP = {
    "fast":   "sma_fast",
    "medium": "sma_med",
    "slow":   "sma_slow",
}

# Maps human-friendly param names → internal param names per template.
# Keys that need value translation (entry_on, exit_below) are handled
# separately via _MA_NAME_MAP.
_PARAM_KEY_MAP: dict[str, dict[str, str]] = {
    "trend_dip_buy_long_only": {
        "fast_ma":            "sma_fast_period",
        "medium_ma":          "sma_med_period",
        "slow_ma":            "sma_slow_period",
        "min_price":          "min_price",
        "min_daily_volume":   "min_avg_daily_volume",
        "slope_lookback":     "slope_lookback",
        "bounce_range_ratio": "bounce_range_ratio",
        "max_positions":      "max_positions",
        "rebalance":          "rebalance_rule",
        "rank_by":            "rank_metric",
    },
    "sma_crossover_long_only": {
        "short_ma":         "short_window",
        "long_ma":          "long_window",
        "min_price":        "min_price",
        "min_daily_volume": "min_avg_daily_volume",
        "max_positions":    "max_positions",
        "rebalance":        "rebalance_rule",
        "rank_by":          "rank_metric",
    },
    "oversold_bounce_long_only": {
        "ema_period":          "ema_period",
        "sma_period":          "sma_period",
        "ema_extension":       "ext_10",
        "sma_extension":       "ext_20",
        "min_down_days":       "min_down_days",
        "max_hold_days":       "max_hold_days",
        "entry_after_hour":    "entry_after_hour",
        "entry_after_minute":  "entry_after_minute",
        "min_price":           "min_price",
        "min_daily_volume":    "min_avg_daily_volume",
        "range_mult":          "range_mult",
        "stop_buffer":         "stop_buffer",
    },
    "rsi_mean_reversion_long_only": {
        "rsi_period":           "rsi_period",
        "oversold_threshold":   "oversold_threshold",
        "exit_rsi":             "exit_rsi",
        "trend_filter_period":  "trend_filter_period",
        "max_hold_days":        "max_hold_days",
        "min_price":            "min_price",
        "min_daily_volume":     "min_avg_daily_volume",
    },
}

# Param keys whose values also need translating through _MA_NAME_MAP
_MA_VALUE_KEYS = {"entry_on", "exit_below"}
_MA_VALUE_INTERNAL_KEYS = {"entry_on": "touch_ma", "exit_below": "exit_below_ma"}


def _is_new_format(schema: dict[str, Any]) -> bool:
    return "strategy" in schema


def _derive_bundle(symbols: list[str], freq_tag: str) -> str:
    label = "_".join(s.lower() for s in symbols)
    return f"yahoo_{freq_tag}_{label}"


def _translate_param_key(template: str, key: str) -> str:
    """Translate a human-friendly param key to its internal name."""
    if key in _MA_VALUE_KEYS:
        return _MA_VALUE_INTERNAL_KEYS[key]
    return _PARAM_KEY_MAP.get(template, {}).get(key, key)


def _translate_param_value(key: str, value: Any) -> Any:
    """Translate a param value if it requires mapping (e.g. MA name strings)."""
    if key in _MA_VALUE_KEYS:
        if isinstance(value, str):
            raw = value.lower()
            if raw not in _MA_NAME_MAP:
                raise ValueError(
                    f"'{key}' must be fast|medium|slow, got '{raw}'"
                )
            return _MA_NAME_MAP[raw]
    return value


def _translate_grid_params(template: str, grid_params: dict[str, Any]) -> dict[str, Any]:
    """Translate grid_search.params keys and values from human-friendly to internal."""
    translated: dict[str, Any] = {}
    for key, values in grid_params.items():
        internal_key = _translate_param_key(template, key)
        if isinstance(values, list):
            translated[internal_key] = [
                _translate_param_value(key, v) for v in values
            ]
        else:
            translated[internal_key] = _translate_param_value(key, values)
    return translated


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return schema in internal format. No-op if already internal format."""
    if not _is_new_format(schema):
        return schema

    template = str(schema["template"])
    symbols = [str(s).strip().upper() for s in schema["symbols"]]
    symbol = symbols[0]

    freq_str = str(schema.get("frequency", "daily")).lower()
    if freq_str not in _FREQUENCY_MAP:
        raise ValueError(
            f"frequency must be one of: {list(_FREQUENCY_MAP.keys())}, got '{freq_str}'"
        )
    frequency_minutes, freq_tag = _FREQUENCY_MAP[freq_str]

    advanced = schema.get("advanced", {})
    exec_adv = advanced.get("execution", {})

    # --- build params ---
    params: dict[str, Any] = {}
    strategy = schema.get("strategy", {})

    if template == "trend_dip_buy_long_only":
        if "fast_ma" in strategy:
            params["sma_fast_period"] = int(strategy["fast_ma"])
        if "medium_ma" in strategy:
            params["sma_med_period"] = int(strategy["medium_ma"])
        if "slow_ma" in strategy:
            params["sma_slow_period"] = int(strategy["slow_ma"])
        if "entry_on" in strategy:
            params["touch_ma"] = _translate_param_value("entry_on", strategy["entry_on"])
        if "exit_below" in strategy:
            params["exit_below_ma"] = _translate_param_value("exit_below", strategy["exit_below"])

    elif template == "sma_crossover_long_only":
        if "short_ma" in strategy:
            params["short_window"] = int(strategy["short_ma"])
        if "long_ma" in strategy:
            params["long_window"] = int(strategy["long_ma"])

    elif template == "oversold_bounce_long_only":
        if "ema_period" in strategy:
            params["ema_period"] = int(strategy["ema_period"])
        if "sma_period" in strategy:
            params["sma_period"] = int(strategy["sma_period"])
        if "ema_extension" in strategy:
            params["ext_10"] = float(strategy["ema_extension"])
        if "sma_extension" in strategy:
            params["ext_20"] = float(strategy["sma_extension"])
        if "min_down_days" in strategy:
            params["min_down_days"] = int(strategy["min_down_days"])
        if "max_hold_days" in strategy:
            params["max_hold_days"] = int(strategy["max_hold_days"])
        if "entry_after_hour" in strategy:
            params["entry_after_hour"] = int(strategy["entry_after_hour"])
        if "entry_after_minute" in strategy:
            params["entry_after_minute"] = int(strategy["entry_after_minute"])

    elif template == "rsi_mean_reversion_long_only":
        for key in ("rsi_period", "trend_filter_period", "max_hold_days"):
            if key in strategy:
                params[key] = int(strategy[key])
        for key in ("oversold_threshold", "exit_rsi"):
            if key in strategy:
                params[key] = float(strategy[key])

    # advanced → params
    for key in ("min_price", "slope_lookback", "bounce_range_ratio", "range_mult", "stop_buffer"):
        if key in advanced:
            params[key] = advanced[key]
    if "min_daily_volume" in advanced:
        params["min_avg_daily_volume"] = advanced["min_daily_volume"]
    if "max_positions" in advanced:
        params["max_positions"] = int(advanced["max_positions"])
    if "rank_by" in advanced:
        params["rank_metric"] = str(advanced["rank_by"])
    if "rebalance" in advanced:
        params["rebalance_rule"] = str(advanced["rebalance"])

    # --- build execution block ---
    execution: dict[str, Any] = {
        "max_leverage": 1.0,
        "same_bar_execution": False,
        "price_used_in_order_execution": "close",
        "costs": {
            "slippage_bps": float(exec_adv.get("slippage_bps", 5.0)),
            "volume_limit_fraction": 0.1,
            "commission_per_share_usd": float(exec_adv.get("commission_per_share", 0.001)),
            "commission_min_trade_usd": 0.0,
        },
    }

    # --- grid search ---
    grid_cfg = advanced.get("grid_search", {})
    grid_enabled = bool(grid_cfg.get("enabled", False))
    raw_grid_params = grid_cfg.get("params", {})
    grid_search: dict[str, Any] = {
        "enabled": grid_enabled,
        "rank_by": str(grid_cfg.get("rank_by", "sharpe")),
        "top_n": int(grid_cfg.get("top_n", 5)),
        "params": _translate_grid_params(template, raw_grid_params) if raw_grid_params else {},
    }

    # --- validation split ---
    split_cfg = advanced.get("validation_split", {})
    validation_split: dict[str, Any] | None = None
    if bool(split_cfg.get("enabled", False)):
        validation_split = {
            "enabled": True,
            "method": str(split_cfg.get("method", "date")),
            "gap_bars": int(split_cfg.get("gap_bars", 0)),
        }
        if "split_date" in split_cfg:
            validation_split["split_date"] = str(split_cfg["split_date"])
        if "train_ratio" in split_cfg:
            validation_split["train_ratio"] = float(split_cfg["train_ratio"])
        if "rank_on" in split_cfg:
            validation_split["rank_on"] = str(split_cfg["rank_on"])

    # --- assemble internal schema ---
    internal: dict[str, Any] = {
        "template": template,
        "symbol": symbol,
        "bundle": _derive_bundle(symbols, freq_tag),
        "frequency_minutes": frequency_minutes,
        "start": str(schema["start"]),
        "end": str(schema["end"]),
        "timezone": str(advanced.get("timezone", "America/New_York")),
        "initial_cash": float(schema.get("initial_cash", 100_000.0)),
        "benchmark_symbol": str(advanced.get("benchmark", symbol)),
        "execution": execution,
        "data": {
            "source": "bundle",
            "allow_yahoo_ingest": bool(advanced.get("allow_yahoo_ingest", False)),
            "symbols": symbols,
        },
        "params": params,
        "grid_search": grid_search,
    }

    if validation_split is not None:
        internal["validation_split"] = validation_split

    return internal
