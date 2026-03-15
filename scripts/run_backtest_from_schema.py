import argparse
import asyncio
import contextlib
import datetime as dt
import io
import itertools
import json
import math
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, cast
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from strategies import REGISTRY
from schema_adapter import normalize_schema


def parse_date(date_str: str, tz_name: str, end_of_day: bool = False) -> dt.datetime:
    y, m, d = [int(x) for x in date_str.split("-")]
    if end_of_day:
        return dt.datetime(y, m, d, 23, 59, tzinfo=ZoneInfo(tz_name))
    return dt.datetime(y, m, d, tzinfo=ZoneInfo(tz_name))


def _parse_iso_date(date_str: str) -> dt.date:
    return dt.date.fromisoformat(date_str)


def _format_iso_date(d: dt.date) -> str:
    return d.isoformat()


def resolve_validation_split(schema: dict[str, Any]) -> dict[str, Any] | None:
    cfg = schema.get("validation_split", {})
    if not bool(cfg.get("enabled", False)):
        return None

    start_date = _parse_iso_date(str(schema["start"]))
    end_date = _parse_iso_date(str(schema["end"]))
    if end_date <= start_date:
        raise ValueError("end must be after start for validation_split")

    method = str(cfg.get("method", "date")).lower()
    gap_bars = int(cfg.get("gap_bars", 0))
    if gap_bars < 0:
        raise ValueError("validation_split.gap_bars must be >= 0")

    if method == "date":
        if "split_date" not in cfg:
            raise ValueError("validation_split.split_date is required for method=date")
        split_date = _parse_iso_date(str(cfg["split_date"]))
    elif method == "ratio":
        train_ratio = float(cfg.get("train_ratio", 0.7))
        if train_ratio <= 0.0 or train_ratio >= 1.0:
            raise ValueError("validation_split.train_ratio must be in (0, 1)")
        total_days = (end_date - start_date).days
        split_offset = int(round(total_days * train_ratio))
        split_offset = max(1, min(total_days - 1, split_offset))
        split_date = start_date + dt.timedelta(days=split_offset)
        # Advance to Monday if split lands on a weekend
        if split_date.weekday() == 5:  # Saturday
            split_date += dt.timedelta(days=2)
        elif split_date.weekday() == 6:  # Sunday
            split_date += dt.timedelta(days=1)
    else:
        raise ValueError("validation_split.method must be 'date' or 'ratio'")

    train_end = split_date - dt.timedelta(days=1)
    test_start = split_date + dt.timedelta(days=gap_bars)

    if train_end < start_date:
        raise ValueError("validation_split results in empty train window")
    if test_start > end_date:
        raise ValueError("validation_split results in empty test window")

    rank_on_raw = str(cfg.get("rank_on", "test_sharpe"))
    rank_on = (
        rank_on_raw
        if rank_on_raw.startswith("test_") or rank_on_raw.startswith("train_")
        else f"test_{rank_on_raw}"
    )

    return {
        "enabled": True,
        "method": method,
        "gap_bars": gap_bars,
        "rank_on": rank_on,
        "train": {
            "start": _format_iso_date(start_date),
            "end": _format_iso_date(train_end),
        },
        "test": {
            "start": _format_iso_date(test_start),
            "end": _format_iso_date(end_date),
        },
    }


def get_schema_symbols(schema: dict[str, Any]) -> list[str]:
    raw = schema.get("data", {}).get("symbols")
    if isinstance(raw, list) and len(raw) > 0:
        symbols = [str(s) for s in raw if str(s).strip()]
    else:
        symbols = [str(schema.get("symbol", ""))]

    out: list[str] = []
    seen: set[str] = set()
    for sym in symbols:
        key = sym.strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)

    if len(out) == 0:
        raise ValueError("No symbols provided")
    return out


def build_execution_config(schema: dict[str, Any]) -> dict[str, Any]:
    execution = schema.get("execution", {})
    costs = execution.get("costs", {})

    price = str(execution.get("price_used_in_order_execution", "close")).lower()
    if price not in {"open", "close", "high", "low"}:
        raise ValueError(
            "execution.price_used_in_order_execution must be open|close|high|low"
        )

    volume_limit_fraction = float(costs.get("volume_limit_fraction", 0.1))
    if volume_limit_fraction <= 0 or volume_limit_fraction > 1:
        raise ValueError("execution.costs.volume_limit_fraction must be in (0, 1]")

    return {
        "max_leverage": float(execution.get("max_leverage", 1.0)),
        "same_bar_execution": bool(execution.get("same_bar_execution", False)),
        "price_used_in_order_execution": price,
        "slippage_bps": float(costs.get("slippage_bps", 5.0)),
        "volume_limit_fraction": volume_limit_fraction,
        "commission_per_share_usd": float(costs.get("commission_per_share_usd", 0.001)),
        "commission_min_trade_usd": float(costs.get("commission_min_trade_usd", 0.0)),
    }


def get_rank_metric(item: dict[str, Any], rank_by: str) -> float | None:
    rank_key = str(rank_by)

    if rank_key.startswith("test_"):
        metric_key = rank_key[len("test_") :]
        metrics = item.get("test", {}).get("metrics", {})
        return _safe_num(metrics.get(metric_key)) if isinstance(metrics, dict) else None

    if rank_key.startswith("train_"):
        metric_key = rank_key[len("train_") :]
        metrics = item.get("train", {}).get("metrics", {})
        return _safe_num(metrics.get(metric_key)) if isinstance(metrics, dict) else None

    metrics = item.get("metrics", {})
    return _safe_num(metrics.get(rank_key)) if isinstance(metrics, dict) else None


def normalize_rank_by(rank_by: str, validation_enabled: bool) -> str:
    key = str(rank_by)
    if not validation_enabled:
        return key
    if key.startswith("test_") or key.startswith("train_"):
        return key
    return f"test_{key}"


def attach_rank_values(
    rows: list[dict[str, Any]], rank_by: str
) -> list[dict[str, Any]]:
    for row in rows:
        row["rank_value"] = get_rank_metric(row, rank_by)
    return rows


def build_stability_diagnostics(
    rows: list[dict[str, Any]], rank_by: str, top_k: int = 5
) -> dict[str, Any]:
    if len(rows) == 0:
        return {
            "top_k": 0,
            "rank_metric": rank_by,
            "top1": None,
            "top5_mean": None,
            "top5_std": None,
            "metric_cv": None,
            "parameter_concentration": {},
            "stability_label": "insufficient",
        }

    def _score(item: dict[str, Any]) -> float:
        v = get_rank_metric(item, rank_by)
        return float(v) if v is not None else -1e18

    sorted_rows = sorted(rows, key=_score, reverse=True)
    k = max(1, min(int(top_k), len(sorted_rows)))
    top_rows = sorted_rows[:k]

    vals: list[float] = []
    for r in top_rows:
        rv = get_rank_metric(r, rank_by)
        if rv is None:
            continue
        vals.append(float(rv))
    if len(vals) == 0:
        mean_v = None
        std_v = None
        cv_v = None
        top1 = None
    else:
        arr = np.asarray(vals, dtype=float)
        top1 = float(arr[0])
        mean_v = float(np.mean(arr))
        std_v = float(np.std(arr, ddof=0))
        cv_v = abs(std_v / mean_v) if mean_v not in (0.0, -0.0) else None

    param_conc: dict[str, dict[str, Any]] = {}
    param_keys: set[str] = set()
    for r in top_rows:
        p = r.get("params", {})
        if isinstance(p, dict):
            param_keys.update(p.keys())

    for key in sorted(param_keys):
        counts: dict[str, int] = {}
        for r in top_rows:
            p = r.get("params", {})
            if not isinstance(p, dict) or key not in p:
                continue
            v = repr(p[key])
            counts[v] = counts.get(v, 0) + 1
        if len(counts) == 0:
            continue
        mode_val, mode_cnt = max(counts.items(), key=lambda kv: kv[1])
        param_conc[str(key)] = {
            "mode_value": mode_val,
            "mode_share": float(mode_cnt) / float(k),
            "unique_count": len(counts),
        }

    max_mode_share = 0.0
    if len(param_conc) > 0:
        max_mode_share = max(
            float(v.get("mode_share", 0.0)) for v in param_conc.values()
        )

    if cv_v is None:
        label = "insufficient"
    elif cv_v <= 0.10 and max_mode_share <= 0.80:
        label = "stable"
    elif cv_v <= 0.25 and max_mode_share <= 0.95:
        label = "moderate"
    else:
        label = "fragile"

    return {
        "top_k": k,
        "rank_metric": rank_by,
        "top1": top1,
        "top5_mean": mean_v,
        "top5_std": std_v,
        "metric_cv": cv_v,
        "parameter_concentration": param_conc,
        "stability_label": label,
    }


def _max_drawdown_from_returns(returns: np.ndarray) -> float | None:
    if len(returns) == 0:
        return None
    eq = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(eq)
    dd = (eq / peak) - 1.0
    if len(dd) == 0:
        return None
    return float(np.min(dd))


def build_risk_attribution_from_perf(perf) -> dict[str, Any]:
    out: dict[str, Any] = {
        "corr_with_benchmark": None,
        "beta_up": None,
        "beta_down": None,
        "capture_up": None,
        "capture_down": None,
        "avg_return_on_up_benchmark_days": None,
        "avg_return_on_down_benchmark_days": None,
        "rolling_sharpe_63_end": None,
        "rolling_vol_20_end": None,
        "rolling_dd_63_end": None,
    }

    if perf is None or len(perf) == 0:
        return out
    if "returns" not in perf.columns:
        return out

    r = np.asarray(perf["returns"], dtype=float)
    r = r[~np.isnan(r)]
    if len(r) == 0:
        return out

    if "benchmark_period_return" in perf.columns:
        b = np.asarray(perf["benchmark_period_return"], dtype=float)
        m = (~np.isnan(b)) & (~np.isnan(np.asarray(perf["returns"], dtype=float)))
        rb = np.asarray(perf["returns"], dtype=float)[m]
        bb = b[m]
        if len(rb) > 1 and np.std(rb) > 0 and np.std(bb) > 0:
            out["corr_with_benchmark"] = float(np.corrcoef(rb, bb)[0, 1])

        up = bb > 0
        dn = bb < 0
        if np.any(up):
            b_up = bb[up]
            r_up = rb[up]
            if len(b_up) > 1 and np.var(b_up) > 0:
                out["beta_up"] = float(np.cov(r_up, b_up)[0, 1] / np.var(b_up))
            b_up_mean = float(np.mean(b_up)) if len(b_up) > 0 else None
            r_up_mean = float(np.mean(r_up)) if len(r_up) > 0 else None
            out["avg_return_on_up_benchmark_days"] = r_up_mean
            if b_up_mean is not None and b_up_mean != 0 and r_up_mean is not None:
                out["capture_up"] = float(r_up_mean / b_up_mean)

        if np.any(dn):
            b_dn = bb[dn]
            r_dn = rb[dn]
            if len(b_dn) > 1 and np.var(b_dn) > 0:
                out["beta_down"] = float(np.cov(r_dn, b_dn)[0, 1] / np.var(b_dn))
            b_dn_mean = float(np.mean(b_dn)) if len(b_dn) > 0 else None
            r_dn_mean = float(np.mean(r_dn)) if len(r_dn) > 0 else None
            out["avg_return_on_down_benchmark_days"] = r_dn_mean
            if b_dn_mean is not None and b_dn_mean != 0 and r_dn_mean is not None:
                out["capture_down"] = float(r_dn_mean / b_dn_mean)

    if len(r) >= 63:
        tail63 = r[-63:]
        s = float(np.std(tail63, ddof=1)) if len(tail63) > 1 else 0.0
        if s > 0:
            out["rolling_sharpe_63_end"] = float(np.mean(tail63) * np.sqrt(252.0) / s)
        out["rolling_dd_63_end"] = _max_drawdown_from_returns(tail63)

    if len(r) >= 20:
        tail20 = r[-20:]
        s20 = float(np.std(tail20, ddof=1)) if len(tail20) > 1 else 0.0
        out["rolling_vol_20_end"] = float(s20 * np.sqrt(252.0))

    return out


def build_data_interface(schema: dict[str, Any]) -> dict[str, Any]:
    data_cfg = schema.get("data", {})
    source = str(data_cfg.get("source", "bundle")).lower()
    symbols = data_cfg.get("symbols") or (
        [schema.get("symbol")] if schema.get("symbol") else []
    )
    symbol_count = len([s for s in symbols if s])

    if source == "bundle":
        return {
            "source": source,
            "status": "active",
            "symbol_count": symbol_count,
            "note": "Bundle source is active in this runner.",
        }

    if source in {"csv", "parquet", "custom"}:
        required: list[str]
        if source in {"csv", "parquet"}:
            required = ["path"]
        else:
            required = ["provider"]

        missing = [k for k in required if data_cfg.get(k) in (None, "")]
        return {
            "source": source,
            "status": "reserved_interface_only",
            "symbol_count": symbol_count,
            "required_fields_missing": missing,
            "note": "Data adapter is reserved for extension and is not active in this runner.",
        }

    return {
        "source": source,
        "status": "invalid",
        "symbol_count": symbol_count,
        "required_fields_missing": [],
        "note": "Unsupported data.source. Use bundle/csv/parquet/custom.",
    }


def build_live_interface(schema: dict[str, Any]) -> dict[str, Any] | None:
    cfg = schema.get("live_data", {})
    if not bool(cfg.get("enabled", False)):
        return None

    provider = str(cfg.get("provider", "ibkr")).lower()
    required = ["host", "port", "client_id"] if provider == "ibkr" else []
    missing = [k for k in required if cfg.get(k) in (None, "")]

    return {
        "enabled": True,
        "provider": provider,
        "status": "reserved_interface_only",
        "required_fields_missing": missing,
        "next_step_hint": "Integrate provider SDK in a dedicated runtime module. Keep backtest runner unchanged.",
    }


def make_algorithm_source(template_name: str, params: dict[str, Any]) -> str:
    if template_name not in REGISTRY:
        raise ValueError(f"Unsupported template: {template_name}")
    return REGISTRY[template_name].ALGORITHM_SOURCE.replace(
        "__PARAMS_JSON__", json.dumps(params)
    )


def build_params(
    schema: dict[str, Any], run_params: dict[str, Any] | None = None
) -> dict[str, Any]:
    p = dict(schema.get("params", {}))
    if run_params:
        p.update(run_params)

    template = schema["template"]
    if template not in REGISTRY:
        raise ValueError(f"Unsupported template: {template}")

    symbols = get_schema_symbols(schema)
    symbol = str(schema.get("symbol", symbols[0]))
    frequency_minutes = int(schema.get("frequency_minutes", 5))
    market_tz = schema.get("timezone", "America/New_York")

    strategy = REGISTRY[template]
    defaults = strategy.get_defaults(symbol, symbols, frequency_minutes, market_tz)
    defaults.update(p)

    if strategy.HAS_PORTFOLIO_CONTROLS:
        max_positions_raw = defaults.get("max_positions", len(symbols))
        if max_positions_raw is None:
            max_positions = len(symbols)
        else:
            max_positions = int(max_positions_raw)
        if max_positions < 1:
            raise ValueError("params.max_positions must be >= 1")
        defaults["max_positions"] = min(max_positions, len(symbols))

        rebalance_rule = str(defaults.get("rebalance_rule", "daily")).lower()
        if rebalance_rule not in {"daily", "weekly", "monthly"}:
            raise ValueError("params.rebalance_rule must be daily|weekly|monthly")
        defaults["rebalance_rule"] = rebalance_rule

        defaults["rank_metric"] = str(defaults.get("rank_metric", "ma_ratio"))

    if template == "sma_crossover_long_only":
        short_w = int(defaults.get("short_window", 50))
        long_w = int(defaults.get("long_window", 200))
        if short_w >= long_w:
            raise ValueError(
                f"sma_crossover: short_ma ({short_w}) must be less than long_ma ({long_w})"
            )

    return defaults


def extract_metrics(result, initial_cash: float) -> dict[str, float | None]:
    perf = result.perf
    if perf is None or len(perf) == 0:
        return {
            "total_return": None,
            "sharpe": None,
            "max_drawdown": None,
            "alpha": None,
            "beta": None,
            "algo_volatility": None,
            "ending_portfolio_value": None,
        }

    row = perf.iloc[-1]

    total_return = row.get("algorithm_period_return")
    if total_return is None or (
        isinstance(total_return, float) and math.isnan(total_return)
    ):
        total_return = row.get("returns")

    ending_value = row.get("portfolio_value")
    if ending_value is None or (
        isinstance(ending_value, float) and math.isnan(ending_value)
    ):
        if total_return is not None and not (
            isinstance(total_return, float) and math.isnan(total_return)
        ):
            ending_value = initial_cash * (1.0 + float(total_return))
        else:
            ending_value = None

    def _to_num(v):
        if v is None:
            return None
        try:
            fv = float(v)
            if math.isnan(fv):
                return None
            return fv
        except Exception:
            return None

    return {
        "total_return": _to_num(total_return),
        "sharpe": _to_num(row.get("sharpe")),
        "max_drawdown": _to_num(row.get("max_drawdown")),
        "alpha": _to_num(row.get("alpha")),
        "beta": _to_num(row.get("beta")),
        "algo_volatility": _to_num(row.get("algo_volatility")),
        "ending_portfolio_value": _to_num(ending_value),
    }


def extract_performance_metrics(
    result, core_metrics: dict[str, float | None]
) -> dict[str, float | None]:
    perf = result.perf
    if perf is None or len(perf) == 0:
        return {
            "Performance": None,
            "Win Days": None,
            "Sharpe": None,
            "Avg. Drawdown": None,
            "Beta": None,
            "Avg. Drawdown Days": None,
            "Alpha": None,
            "Volatility": None,
            "Recovery Factor": None,
            "Profit Factor": None,
            "Calmar": None,
        }

    if "returns" in perf.columns:
        returns_series = perf["returns"].dropna()
        returns = np.asarray(returns_series, dtype=float)
    else:
        returns = np.asarray([], dtype=float)

    total_return = core_metrics.get("total_return")
    max_drawdown = core_metrics.get("max_drawdown")
    sharpe = core_metrics.get("sharpe")
    alpha = core_metrics.get("alpha")
    beta = core_metrics.get("beta")
    volatility = core_metrics.get("algo_volatility")

    # fallback
    if (volatility is None) and len(returns) > 1:
        volatility = float(np.std(returns, ddof=1) * np.sqrt(252.0))

    if (sharpe is None) and len(returns) > 1:
        std = float(np.std(returns, ddof=1))
        if std > 0:
            sharpe = float(np.mean(returns) / std * np.sqrt(252.0))

    # drawdown stats
    avg_drawdown = None
    avg_drawdown_days = None
    drawdown_series = np.asarray([], dtype=float)
    if len(returns) > 0:
        equity = np.cumprod(1.0 + returns)
        running_max = np.maximum.accumulate(equity)
        drawdown_series = (equity / running_max) - 1.0

        episode_mins: list[float] = []
        episode_days: list[int] = []
        in_dd = False
        cur_min = 0.0
        cur_days = 0

        for dd in drawdown_series:
            if dd < 0:
                if not in_dd:
                    in_dd = True
                    cur_min = float(dd)
                    cur_days = 1
                else:
                    cur_min = min(cur_min, float(dd))
                    cur_days += 1
            elif in_dd:
                episode_mins.append(cur_min)
                episode_days.append(cur_days)
                in_dd = False
                cur_min = 0.0
                cur_days = 0

        if in_dd:
            episode_mins.append(cur_min)
            episode_days.append(cur_days)

        if len(episode_mins) > 0:
            avg_drawdown = float(np.mean(episode_mins))
            avg_drawdown_days = float(np.mean(episode_days))

        if max_drawdown is None and len(drawdown_series) > 0:
            max_drawdown = float(np.min(drawdown_series))

    # win rate
    win_days = None
    if len(returns) > 0:
        win_days = float(np.mean(returns > 0.0))

    # profit factor
    profit_factor = None
    if len(returns) > 0:
        pos_sum = float(np.sum(returns[returns > 0.0]))
        neg_sum_abs = float(np.abs(np.sum(returns[returns < 0.0])))
        if neg_sum_abs > 0:
            profit_factor = pos_sum / neg_sum_abs

    # cagr and ratios
    cagr = None
    if (
        total_return is not None
        and len(returns) > 0
        and (1.0 + float(total_return)) > 0
    ):
        cagr = float((1.0 + float(total_return)) ** (252.0 / len(returns)) - 1.0)

    recovery_factor = None
    calmar = None
    if max_drawdown is not None and float(max_drawdown) < 0:
        dd_abs = abs(float(max_drawdown))
        if total_return is not None:
            recovery_factor = float(total_return) / dd_abs
        if cagr is not None:
            calmar = cagr / dd_abs

    return {
        "Performance": total_return,
        "Win Days": win_days,
        "Sharpe": sharpe,
        "Avg. Drawdown": avg_drawdown,
        "Beta": beta,
        "Avg. Drawdown Days": avg_drawdown_days,
        "Alpha": alpha,
        "Volatility": volatility,
        "Recovery Factor": recovery_factor,
        "Profit Factor": profit_factor,
        "Calmar": calmar,
    }


def _empty_trade_summary() -> dict[str, Any]:
    return {
        "trade_count": 0,
        "win_rate": None,
        "avg_hold_days": None,
        "avg_trade_return": None,
        "avg_win_return": None,
        "avg_loss_return": None,
        "expectancy_return": None,
        "best_trade_return": None,
        "worst_trade_return": None,
        "total_realized_pnl": None,
    }


def _to_datetime_like(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)
    to_py = getattr(value, "to_pydatetime", None)
    if callable(to_py):
        try:
            out = to_py()
            if isinstance(out, dt.datetime):
                return out
        except Exception:
            return None
    return None


def _tx_field(tx: Any, key: str, default: Any = None) -> Any:
    if isinstance(tx, dict):
        return tx.get(key, default)
    return getattr(tx, key, default)


def _tx_sid(tx: Any) -> str:
    sid = _tx_field(tx, "sid", None)
    if sid is not None:
        return str(sid)

    asset = _tx_field(tx, "asset", None)
    if asset is None:
        return "unknown"

    asset_sid = getattr(asset, "sid", None)
    if asset_sid is not None:
        return str(asset_sid)

    asset_symbol = getattr(asset, "symbol", None)
    if asset_symbol is not None:
        return str(asset_symbol)

    return str(asset)


def build_capacity_diagnostics_from_perf(
    perf, params: dict[str, Any]
) -> dict[str, Any]:
    out = {
        "avg_daily_trade_notional": None,
        "avg_portfolio_value": None,
        "avg_daily_turnover": None,
        "annualized_turnover": None,
        "adv_floor_dollar": None,
        "participation_vs_adv_floor": None,
        "participation_risk": "not_assessed",
        "note": "Capacity diagnostics are not available.",
    }

    if perf is None or len(perf) == 0:
        return out

    traded_notional_by_day: list[float] = []
    if "transactions" in perf.columns:
        for _, row in perf.iterrows():
            txs = row.get("transactions")
            day_notional = 0.0
            if isinstance(txs, list):
                for tx in txs:
                    amount = _safe_num(_tx_field(tx, "amount", None))
                    price = _safe_num(_tx_field(tx, "price", None))
                    if amount is None or price is None:
                        continue
                    day_notional += abs(float(amount) * float(price))
            traded_notional_by_day.append(day_notional)
    elif "capital_used" in perf.columns:
        cap = np.asarray(perf["capital_used"], dtype=float)
        cap = np.nan_to_num(cap, nan=0.0)
        traded_notional_by_day = [float(abs(v)) for v in cap]
    else:
        traded_notional_by_day = [0.0 for _ in range(len(perf))]

    if len(traded_notional_by_day) == 0:
        return out

    avg_daily_trade_notional = float(
        np.mean(np.asarray(traded_notional_by_day, dtype=float))
    )
    out["avg_daily_trade_notional"] = avg_daily_trade_notional

    avg_portfolio_value = None
    if "portfolio_value" in perf.columns:
        pv = np.asarray(perf["portfolio_value"], dtype=float)
        pv = pv[~np.isnan(pv)]
        if len(pv) > 0:
            avg_portfolio_value = float(np.mean(pv))
            out["avg_portfolio_value"] = avg_portfolio_value

    if avg_portfolio_value is not None and avg_portfolio_value > 0:
        avg_daily_turnover = avg_daily_trade_notional / avg_portfolio_value
        out["avg_daily_turnover"] = avg_daily_turnover
        out["annualized_turnover"] = float(avg_daily_turnover * 252.0)

    min_adv = _safe_num(params.get("min_avg_daily_volume"))
    min_price = _safe_num(params.get("min_price"))
    adv_floor_dollar = None
    if min_adv is not None and min_price is not None and min_adv > 0 and min_price > 0:
        adv_floor_dollar = float(min_adv * min_price)
        out["adv_floor_dollar"] = adv_floor_dollar

    if adv_floor_dollar is not None and adv_floor_dollar > 0:
        participation = float(avg_daily_trade_notional / adv_floor_dollar)
        out["participation_vs_adv_floor"] = participation
        if participation <= 0.01:
            out["participation_risk"] = "low"
        elif participation <= 0.05:
            out["participation_risk"] = "medium"
        else:
            out["participation_risk"] = "high"
        out["note"] = (
            "Participation is estimated versus ADV floor from strategy filters."
        )
    else:
        out["note"] = (
            "ADV floor is unavailable; set min_price and min_avg_daily_volume for participation diagnostics."
        )

    return out


def extract_trade_summary_from_perf(perf) -> dict[str, Any]:
    if perf is None or len(perf) == 0:
        return _empty_trade_summary()
    if "transactions" not in perf.columns:
        return _empty_trade_summary()

    open_lots: dict[str, list[dict[str, Any]]] = {}
    trade_returns: list[float] = []
    trade_pnls: list[float] = []
    hold_days: list[float] = []

    for idx, row in perf.iterrows():
        txs = row.get("transactions")
        if not isinstance(txs, list) or len(txs) == 0:
            continue

        row_dt = _to_datetime_like(idx)
        for tx in txs:
            amount = _safe_num(_tx_field(tx, "amount", None))
            price = _safe_num(_tx_field(tx, "price", None))
            if amount is None or price is None or amount == 0:
                continue

            sid = _tx_sid(tx)
            tx_dt = _to_datetime_like(_tx_field(tx, "dt", None)) or row_dt
            if tx_dt is None:
                tx_dt = dt.datetime(1970, 1, 1)

            lots = open_lots.setdefault(sid, [])

            if amount > 0:
                lots.append({"qty": float(amount), "price": float(price), "dt": tx_dt})
                continue

            sell_qty = float(-amount)
            while sell_qty > 0 and lots:
                lot = lots[0]
                lot_qty = float(lot["qty"])
                lot_price = float(lot["price"])
                lot_dt = lot["dt"]

                close_qty = min(lot_qty, sell_qty)
                pnl = (float(price) - lot_price) * close_qty
                ret = (float(price) / lot_price - 1.0) if lot_price > 0 else None
                hold = max(0.0, float((tx_dt.date() - lot_dt.date()).days))

                trade_pnls.append(float(pnl))
                if ret is not None:
                    trade_returns.append(float(ret))
                hold_days.append(hold)

                lot_qty -= close_qty
                sell_qty -= close_qty

                if lot_qty <= 0:
                    lots.pop(0)
                else:
                    lot["qty"] = lot_qty

    if len(trade_pnls) == 0:
        return _empty_trade_summary()

    returns_arr = (
        np.asarray(trade_returns, dtype=float)
        if len(trade_returns) > 0
        else np.asarray([], dtype=float)
    )
    pnl_arr = np.asarray(trade_pnls, dtype=float)
    holds_arr = (
        np.asarray(hold_days, dtype=float)
        if len(hold_days) > 0
        else np.asarray([], dtype=float)
    )

    win_rate = None
    avg_trade_return = None
    avg_win_return = None
    avg_loss_return = None
    expectancy_return = None
    best_trade_return = None
    worst_trade_return = None

    if len(returns_arr) > 0:
        win_rate = float(np.mean(returns_arr > 0.0))
        avg_trade_return = float(np.mean(returns_arr))
        expectancy_return = avg_trade_return
        best_trade_return = float(np.max(returns_arr))
        worst_trade_return = float(np.min(returns_arr))

        wins = returns_arr[returns_arr > 0.0]
        losses = returns_arr[returns_arr < 0.0]
        if len(wins) > 0:
            avg_win_return = float(np.mean(wins))
        if len(losses) > 0:
            avg_loss_return = float(np.mean(losses))

    avg_hold = float(np.mean(holds_arr)) if len(holds_arr) > 0 else None

    return {
        "trade_count": int(len(trade_pnls)),
        "win_rate": win_rate,
        "avg_hold_days": avg_hold,
        "avg_trade_return": avg_trade_return,
        "avg_win_return": avg_win_return,
        "avg_loss_return": avg_loss_return,
        "expectancy_return": expectancy_return,
        "best_trade_return": best_trade_return,
        "worst_trade_return": worst_trade_return,
        "total_realized_pnl": float(np.sum(pnl_arr)),
    }


def extract_trade_summary(result) -> dict[str, Any]:
    perf = getattr(result, "perf", None)
    return extract_trade_summary_from_perf(perf)


def _safe_num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
        if math.isnan(out):
            return None
        return out
    except Exception:
        return None


def build_practical_assessment(
    schema: dict[str, Any],
    params: dict[str, Any],
    metrics: dict[str, Any],
    grid_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sharpe = _safe_num(metrics.get("sharpe")) if isinstance(metrics, dict) else None
    exec_cfg = build_execution_config(schema)

    same_bar_execution = bool(exec_cfg["same_bar_execution"])
    execution_price = str(exec_cfg["price_used_in_order_execution"])
    future_leakage = {
        "risk_level": "low" if not same_bar_execution else "medium",
        "same_bar_execution": same_bar_execution,
        "execution_price": execution_price,
        "note": (
            "Signals use completed bars; orders are executed on later bars."
            if not same_bar_execution
            else "Same-bar execution is enabled; check signal timing."
        ),
    }

    slippage_bps = float(exec_cfg["slippage_bps"])
    volume_limit_fraction = float(exec_cfg["volume_limit_fraction"])
    commission_per_share_usd = float(exec_cfg["commission_per_share_usd"])
    slippage_commission = {
        "slippage_bps": slippage_bps,
        "volume_limit_fraction": volume_limit_fraction,
        "commission_per_share_usd": commission_per_share_usd,
        "live_impact_direction": "likely_worse_than_backtest",
        "note": (
            "Backtest uses fixed slippage and simple fees; live execution is usually worse in stress."
        ),
    }

    grid_trials = None
    sharpe_gap = None
    if isinstance(grid_context, dict):
        grid_trials = int(grid_context.get("total_trials", 0))
        top_sharpe = _safe_num(grid_context.get("top_sharpe"))
        second_sharpe = _safe_num(grid_context.get("second_sharpe"))
        if top_sharpe is not None and second_sharpe is not None:
            sharpe_gap = round(top_sharpe - second_sharpe, 6)

    if grid_trials is None:
        overfit_level = "not_assessed"
        overfit_note = "Single run only; use grid plus out-of-sample checks."
    else:
        if grid_trials >= 100 or (sharpe_gap is not None and sharpe_gap >= 0.2):
            overfit_level = "elevated"
        elif grid_trials >= 30 or (sharpe_gap is not None and sharpe_gap >= 0.1):
            overfit_level = "medium"
        else:
            overfit_level = "controlled"
        overfit_note = (
            "Quick grid used. Confirm with walk-forward or out-of-sample checks."
        )

    overfitting_risk = {
        "risk_level": overfit_level,
        "grid_trials": grid_trials,
        "sharpe_gap_top1_top2": sharpe_gap,
        "note": overfit_note,
    }

    symbols = get_schema_symbols(schema)
    symbol = symbols[0]
    min_price = _safe_num(params.get("min_price"))
    min_adv = _safe_num(params.get("min_avg_daily_volume"))
    capacity_liquidity = {
        "symbol": symbol,
        "symbol_count": len(symbols),
        "min_price_filter": min_price,
        "min_avg_daily_volume_filter": min_adv,
        "suitability": "good_for_liquid_etf"
        if symbol in {"QQQ", "SPY", "IWM"}
        else "depends_on_liquidity",
        "note": (
            "Liquid ETFs usually scale better; monitor turnover and slippage as size increases."
        ),
    }

    return {
        "future_leakage": future_leakage,
        "slippage_commission": slippage_commission,
        "overfitting_risk": overfitting_risk,
        "capacity_liquidity": capacity_liquidity,
        "headline": {
            "sharpe": sharpe,
            "overall": "research_ready_not_production"
            if sharpe is None or sharpe < 1.2
            else "candidate_for_paper_trading",
        },
    }


def format_percentage_output(payload: dict[str, Any]) -> dict[str, Any]:
    def _pct(v: Any) -> Any:
        if v is None:
            return None
        try:
            return f"{float(v) * 100.0:.2f}%"
        except Exception:
            return v

    metric_percent_keys = {
        "total_return",
        "max_drawdown",
        "alpha",
        "algo_volatility",
    }
    perf_metric_percent_keys = {
        "Performance",
        "Win Days",
        "Avg. Drawdown",
        "Alpha",
        "Volatility",
    }
    trade_percent_keys = {
        "win_rate",
        "avg_trade_return",
        "avg_win_return",
        "avg_loss_return",
        "expectancy_return",
        "best_trade_return",
        "worst_trade_return",
    }
    risk_percent_keys = {
        "avg_return_on_up_benchmark_days",
        "avg_return_on_down_benchmark_days",
        "rolling_vol_20_end",
        "rolling_dd_63_end",
    }
    capacity_percent_keys = {
        "avg_daily_turnover",
        "annualized_turnover",
        "participation_vs_adv_floor",
    }

    def _format_result_block(block: dict[str, Any]) -> None:
        metrics = block.get("metrics")
        if isinstance(metrics, dict):
            for k in metric_percent_keys:
                if k in metrics:
                    metrics[k] = _pct(metrics.get(k))

        performance_metrics = block.get("performance_metrics")
        if isinstance(performance_metrics, dict):
            for k in perf_metric_percent_keys:
                if k in performance_metrics:
                    performance_metrics[k] = _pct(performance_metrics.get(k))

        trade_summary = block.get("trade_summary")
        if isinstance(trade_summary, dict):
            for k in trade_percent_keys:
                if k in trade_summary:
                    trade_summary[k] = _pct(trade_summary.get(k))

        risk_attr = block.get("risk_attribution")
        if isinstance(risk_attr, dict):
            for k in risk_percent_keys:
                if k in risk_attr:
                    risk_attr[k] = _pct(risk_attr.get(k))

        capacity = block.get("capacity_diagnostics")
        if isinstance(capacity, dict):
            for k in capacity_percent_keys:
                if k in capacity:
                    capacity[k] = _pct(capacity.get(k))

        for nested_key in ("train", "test"):
            nested = block.get(nested_key)
            if isinstance(nested, dict):
                _format_result_block(nested)

    _format_result_block(payload)

    top_results = payload.get("top_results")
    if isinstance(top_results, list):
        for row in top_results:
            if isinstance(row, dict):
                _format_result_block(row)

    return payload


def build_backtest_window(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "start": schema.get("start"),
        "end": schema.get("end"),
        "timezone": schema.get("timezone", "America/New_York"),
        "frequency_minutes": schema.get("frequency_minutes", 5),
    }


def _flatten_column_name(col: Any) -> str:
    if isinstance(col, tuple):
        for part in col:
            if part is None:
                continue
            text = str(part).strip()
            if text:
                return text
        return "col"

    text = str(col).strip()
    return text if text else "col"


def _wrap_yfinance_download(download_func):
    def _wrapped(*args, **kwargs):
        call_kwargs = dict(kwargs)
        is_ticker_group = str(call_kwargs.get("group_by", "")).lower() == "ticker"
        call_kwargs["multi_level_index"] = bool(is_ticker_group)

        df = download_func(*args, **call_kwargs)
        cols = getattr(df, "columns", None)
        if cols is None:
            return df

        try:
            if getattr(df.index, "has_duplicates", False):
                df = df[~df.index.duplicated(keep="last")]
        except Exception:
            pass

        if is_ticker_group:
            return df

        nlevels = getattr(cols, "nlevels", 1)
        if int(nlevels) <= 1:
            return df

        flat_cols: list[str] = []
        seen: dict[str, int] = {}
        for c in cols:
            base = _flatten_column_name(c)
            idx = seen.get(base, 0)
            seen[base] = idx + 1
            flat_cols.append(base if idx == 0 else f"{base}_{idx}")

        df = df.copy()
        df.columns = flat_cols
        return df

    return _wrapped


async def maybe_ingest_if_needed(
    schema: dict[str, Any], data_dir: str, ingest_if_missing: bool
) -> None:
    if not ingest_if_missing:
        return

    data_cfg = schema.get("data", {})
    if not bool(data_cfg.get("allow_yahoo_ingest", False)):
        return

    tz_name = schema.get("timezone", "America/New_York")
    start = parse_date(schema["start"], tz_name)
    end = parse_date(schema["end"], tz_name) + dt.timedelta(days=1)

    symbols = data_cfg.get("symbols") or [schema["symbol"]]
    freq_min = int(schema.get("frequency_minutes", 5))
    bundle_name = schema["bundle"]

    from ziplime.core.ingest_data import (
        get_asset_service,
        ingest_default_assets,
        ingest_market_data,
    )
    from ziplime.data.data_sources.yahoo_finance_data_source import (
        YahooFinanceDataSource,
    )

    try:
        import yfinance as yf

        if not bool(getattr(yf.download, "__opencode_flattened__", False)):
            wrapped_download = _wrap_yfinance_download(yf.download)
            setattr(wrapped_download, "__opencode_flattened__", True)
            yf.download = wrapped_download
    except Exception:
        pass

    asset_service = get_asset_service(
        db_path=str(Path(data_dir, "assets.sqlite")), clear_asset_db=True
    )
    await ingest_default_assets(
        asset_service=asset_service, asset_data_source=cast(Any, None)
    )
    source = YahooFinanceDataSource(maximum_threads=1)

    await ingest_market_data(
        start_date=start,
        end_date=end,
        trading_calendar="NYSE",
        bundle_name=bundle_name,
        symbols=symbols,
        data_frequency=dt.timedelta(minutes=freq_min),
        data_bundle_source=source,
        asset_service=asset_service,
        bundle_storage_path=data_dir,
    )


async def load_market_bundle(schema: dict[str, Any], data_dir: str):
    from ziplime.data.services.bundle_service import BundleService
    from ziplime.data.services.file_system_bundle_registry import (
        FileSystemBundleRegistry,
    )

    bundle_registry = FileSystemBundleRegistry(base_data_path=data_dir)
    bundle_service = BundleService(bundle_registry=bundle_registry)

    tz_name = schema.get("timezone", "America/New_York")
    start = parse_date(schema["start"], tz_name)
    end = parse_date(schema["end"], tz_name) + dt.timedelta(days=1)
    symbols = schema.get("data", {}).get("symbols") or [schema["symbol"]]

    return await bundle_service.load_bundle(
        bundle_name=schema["bundle"],
        bundle_version=None,
        frequency=dt.timedelta(minutes=int(schema.get("frequency_minutes", 5))),
        start_date=start,
        end_date=end,
        symbols=symbols,
    )


async def run_once(
    schema: dict[str, Any],
    data_dir: str,
    run_params: dict[str, Any] | None = None,
    window: dict[str, str] | None = None,
    asset_service: Any | None = None,
    market_bundle: Any | None = None,
) -> dict[str, Any]:
    from ziplime.core.run_simulation import run_simulation
    from ziplime.exchanges.simulation_exchange import SimulationExchange
    from ziplime.finance.commission import PerContract, PerShare
    from ziplime.finance.constants import FUTURE_EXCHANGE_FEES_BY_SYMBOL
    from ziplime.finance.slippage.fixed_basis_points_slippage import (
        FixedBasisPointsSlippage,
    )
    from ziplime.finance.slippage.slippage_model import (
        DEFAULT_FUTURE_VOLUME_SLIPPAGE_BAR_LIMIT,
    )
    from ziplime.finance.slippage.volatility_volume_share import VolatilityVolumeShare
    from ziplime.gens.domain.simulation_clock import SimulationClock
    from ziplime.utils.calendar_utils import get_calendar

    tz_name = schema.get("timezone", "America/New_York")
    start_str = schema["start"] if window is None else window["start"]
    end_str = schema["end"] if window is None else window["end"]
    start = parse_date(start_str, tz_name)
    end = parse_date(end_str, tz_name)

    final_params = build_params(schema, run_params=run_params)
    exec_cfg = build_execution_config(schema)
    algo_source = make_algorithm_source(schema["template"], final_params)

    with NamedTemporaryFile(
        mode="w", suffix="_algo.py", delete=False, encoding="utf-8"
    ) as f:
        f.write(algo_source)
        algo_file = f.name

    if asset_service is None:
        from ziplime.core.ingest_data import get_asset_service

        asset_service = get_asset_service(
            db_path=str(Path(data_dir, "assets.sqlite")), clear_asset_db=False
        )
    if market_bundle is None:
        market_bundle = await load_market_bundle(schema, data_dir=data_dir)

    initial_cash = float(schema.get("initial_cash", 100_000.0))
    emission_rate = dt.timedelta(minutes=int(schema.get("frequency_minutes", 5)))

    calendar = get_calendar("NYSE")
    clock = SimulationClock(
        trading_calendar=calendar,
        start_date=start,
        end_date=end,
        emission_rate=emission_rate,
    )
    equity_commission = PerShare(
        cost=float(exec_cfg["commission_per_share_usd"]),
        min_trade_cost=float(exec_cfg["commission_min_trade_usd"]),
    )
    future_commission = PerContract(
        cost=0.85,
        exchange_fee=FUTURE_EXCHANGE_FEES_BY_SYMBOL,
        min_trade_cost=0.0,
    )
    exchange = SimulationExchange(
        name="LIME",
        country_code="US",
        trading_calendar=calendar,
        clock=clock,
        cash_balance=initial_cash,
        equity_slippage=FixedBasisPointsSlippage(
            basis_points=float(exec_cfg["slippage_bps"]),
            volume_limit=float(exec_cfg["volume_limit_fraction"]),
        ),
        future_slippage=VolatilityVolumeShare(
            volume_limit=DEFAULT_FUTURE_VOLUME_SLIPPAGE_BAR_LIMIT,
        ),
        equity_commission=equity_commission,
        future_commission=future_commission,
        data_source=market_bundle,
        price_used_in_order_execution=cast(
            Any, str(exec_cfg["price_used_in_order_execution"])
        ),
    )

    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        result = await run_simulation(
            asset_service=asset_service,
            start_date=start,
            end_date=end,
            trading_calendar="NYSE",
            algorithm_file=algo_file,
            total_cash=initial_cash,
            market_data_source=market_bundle,
            custom_data_sources=[],
            config_file=None,
            emission_rate=emission_rate,
            benchmark_asset_symbol=schema.get("benchmark_symbol"),
            benchmark_returns=None,
            exchange=exchange,
            equity_commission=equity_commission,
            future_commission=future_commission,
            clock=clock,
            stop_on_error=False,
            max_leverage=float(exec_cfg["max_leverage"]),
            same_bar_execution=bool(exec_cfg["same_bar_execution"]),
            price_used_in_order_execution=cast(
                Any, str(exec_cfg["price_used_in_order_execution"])
            ),
        )

    metrics = extract_metrics(result, initial_cash=initial_cash)
    performance_metrics = extract_performance_metrics(result, metrics)
    trade_summary = extract_trade_summary(result)
    capacity_diagnostics = build_capacity_diagnostics_from_perf(
        perf=getattr(result, "perf", None), params=final_params
    )
    risk_attribution = build_risk_attribution_from_perf(getattr(result, "perf", None))
    practical_assessment = build_practical_assessment(
        schema=schema,
        params=final_params,
        metrics=metrics,
    )
    live_interface = build_live_interface(schema)
    return {
        "params": final_params,
        "window": {
            "start": start_str,
            "end": end_str,
        },
        "metrics": metrics,
        "performance_metrics": performance_metrics,
        "trade_summary": trade_summary,
        "capacity_diagnostics": capacity_diagnostics,
        "risk_attribution": risk_attribution,
        "practical_assessment": practical_assessment,
        "live_interface": live_interface,
        "errors": result.errors,
    }


async def run_grid(
    schema: dict[str, Any],
    data_dir: str,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from ziplime.core.ingest_data import get_asset_service

    grid_cfg = schema.get("grid_search", {})
    grid_params = grid_cfg.get("params", {})
    if not grid_params:
        raise ValueError("grid_search.params is empty")

    keys = list(grid_params.keys())
    combos = list(itertools.product(*[grid_params[k] for k in keys]))

    shared_asset_service = get_asset_service(
        db_path=str(Path(data_dir, "assets.sqlite")), clear_asset_db=False
    )
    shared_market_bundle = await load_market_bundle(schema, data_dir=data_dir)

    rows = []
    for combo in combos:
        trial_params = dict(zip(keys, combo))
        if validation is None:
            out = await run_once(
                schema,
                data_dir=data_dir,
                run_params=trial_params,
                asset_service=shared_asset_service,
                market_bundle=shared_market_bundle,
            )
            row = {
                "params": out["params"],
                "metrics": out["metrics"],
                "performance_metrics": out.get("performance_metrics"),
                "trade_summary": out.get("trade_summary"),
                "capacity_diagnostics": out.get("capacity_diagnostics"),
                "risk_attribution": out.get("risk_attribution"),
                "errors": out["errors"],
            }
        else:
            train_out = await run_once(
                schema,
                data_dir=data_dir,
                run_params=trial_params,
                window=validation["train"],
                asset_service=shared_asset_service,
                market_bundle=shared_market_bundle,
            )
            test_out = await run_once(
                schema,
                data_dir=data_dir,
                run_params=trial_params,
                window=validation["test"],
                asset_service=shared_asset_service,
                market_bundle=shared_market_bundle,
            )
            row = {
                "params": test_out["params"],
                "window": {
                    "train": train_out.get("window"),
                    "test": test_out.get("window"),
                },
                "train": train_out,
                "test": test_out,
                "metrics": test_out["metrics"],
                "performance_metrics": test_out.get("performance_metrics"),
                "trade_summary": test_out.get("trade_summary"),
                "capacity_diagnostics": test_out.get("capacity_diagnostics"),
                "risk_attribution": test_out.get("risk_attribution"),
                "practical_assessment": test_out.get("practical_assessment"),
                "errors": list(train_out.get("errors", []))
                + list(test_out.get("errors", [])),
            }
        rows.append(row)

    raw_rank_by = (
        str(validation.get("rank_on", "test_sharpe"))
        if validation is not None
        else str(grid_cfg.get("rank_by", "sharpe"))
    )
    rank_by = normalize_rank_by(
        raw_rank_by, validation_enabled=(validation is not None)
    )
    top_n = int(grid_cfg.get("top_n", 5))

    def _score(item: dict[str, Any]) -> float:
        v = get_rank_metric(item, rank_by)
        if v is None:
            return -1e18
        return float(v)

    rows_sorted = sorted(rows, key=_score, reverse=True)
    rows_sorted = attach_rank_values(rows_sorted, rank_by)

    if rows_sorted:
        best = rows_sorted[0]
        best_metrics = (
            best.get("test", {}).get("metrics")
            if validation is not None
            else best.get("metrics")
        ) or {}
        second_metrics = (
            rows_sorted[1].get("test", {}).get("metrics")
            if (validation is not None and len(rows_sorted) > 1)
            else (rows_sorted[1].get("metrics") if len(rows_sorted) > 1 else {})
        )
        practical_assessment = build_practical_assessment(
            schema=schema,
            params=best.get("params") or {},
            metrics=best_metrics,
            grid_context={
                "total_trials": len(rows_sorted),
                "top_sharpe": (best_metrics or {}).get("sharpe"),
                "second_sharpe": (second_metrics or {}).get("sharpe"),
            },
        )
        risk_attribution = best.get("risk_attribution")
        capacity_diagnostics = best.get("capacity_diagnostics")
    else:
        practical_assessment = build_practical_assessment(
            schema=schema,
            params=build_params(schema),
            metrics={},
            grid_context={"total_trials": 0},
        )
        risk_attribution = None
        capacity_diagnostics = None

    stability_diagnostics = build_stability_diagnostics(
        rows_sorted, rank_by=rank_by, top_k=5
    )
    live_interface = build_live_interface(schema)

    return {
        "rank_by": rank_by,
        "total_trials": len(rows_sorted),
        "top_results": rows_sorted[:top_n],
        "stability_diagnostics": stability_diagnostics,
        "capacity_diagnostics": capacity_diagnostics,
        "risk_attribution": risk_attribution,
        "practical_assessment": practical_assessment,
        "live_interface": live_interface,
        "validation": validation,
    }


async def async_main(args):
    schema_path = Path(args.schema).resolve()
    schema = normalize_schema(json.loads(schema_path.read_text(encoding="utf-8")))
    validation = resolve_validation_split(schema)
    live_interface = build_live_interface(schema)
    data_interface = build_data_interface(schema)

    data_dir = args.data_dir or str(Path(Path.home(), ".ziplime", "data"))

    if args.validate_only:
        base_params = build_params(schema)
        source = make_algorithm_source(schema["template"], base_params)
        compile(source, "generated_algorithm.py", "exec")

        grid_enabled = bool(schema.get("grid_search", {}).get("enabled", False))
        validated_grid = 0
        if grid_enabled:
            grid_cfg = schema.get("grid_search", {})
            grid_params = grid_cfg.get("params", {})
            if grid_params:
                keys = list(grid_params.keys())
                for combo in itertools.product(*[grid_params[k] for k in keys]):
                    trial = dict(zip(keys, combo))
                    p = build_params(schema, run_params=trial)
                    s = make_algorithm_source(schema["template"], p)
                    compile(s, "generated_algorithm_grid.py", "exec")
                    validated_grid += 1

        print(
            json.dumps(
                {
                    "mode": "validate_only",
                    "template": schema["template"],
                    "schema_ok": True,
                    "validation_split": validation,
                    "data_interface": data_interface,
                    "live_interface": live_interface,
                    "grid_variants_compiled": validated_grid,
                },
                indent=2,
            )
        )
        return

    if data_interface.get("status") != "active":
        raise ValueError(
            f"data.source '{data_interface.get('source')}' is reserved. Use --validate-only for interface checks or switch to data.source='bundle'."
        )

    await maybe_ingest_if_needed(
        schema, data_dir=data_dir, ingest_if_missing=args.ingest_if_missing
    )

    grid_enabled = bool(schema.get("grid_search", {}).get("enabled", False))
    backtest_window = build_backtest_window(schema)
    if grid_enabled:
        res = await run_grid(schema, data_dir=data_dir, validation=validation)
        out = format_percentage_output(
            {"mode": "grid", "backtest_window": backtest_window, **res}
        )
        out["data_interface"] = data_interface
        print(json.dumps(out, indent=2))
    else:
        if validation is None:
            res = await run_once(schema, data_dir=data_dir)
            out = format_percentage_output(
                {"mode": "single", "backtest_window": backtest_window, **res}
            )
        else:
            from ziplime.core.ingest_data import get_asset_service

            shared_asset_service = get_asset_service(
                db_path=str(Path(data_dir, "assets.sqlite")), clear_asset_db=False
            )
            shared_market_bundle = await load_market_bundle(schema, data_dir=data_dir)

            train_res = await run_once(
                schema,
                data_dir=data_dir,
                window=validation["train"],
                asset_service=shared_asset_service,
                market_bundle=shared_market_bundle,
            )
            test_res = await run_once(
                schema,
                data_dir=data_dir,
                window=validation["test"],
                asset_service=shared_asset_service,
                market_bundle=shared_market_bundle,
            )
            out = format_percentage_output(
                {
                    "mode": "single",
                    "backtest_window": backtest_window,
                    "validation": validation,
                    "data_interface": data_interface,
                    "params": test_res.get("params"),
                    "window": {
                        "train": train_res.get("window"),
                        "test": test_res.get("window"),
                    },
                    "train": train_res,
                    "test": test_res,
                    "metrics": test_res.get("metrics"),
                    "performance_metrics": test_res.get("performance_metrics"),
                    "trade_summary": test_res.get("trade_summary"),
                    "capacity_diagnostics": test_res.get("capacity_diagnostics"),
                    "risk_attribution": test_res.get("risk_attribution"),
                    "practical_assessment": test_res.get("practical_assessment"),
                    "live_interface": test_res.get("live_interface"),
                    "errors": list(train_res.get("errors", []))
                    + list(test_res.get("errors", [])),
                }
            )
        if validation is None:
            out["data_interface"] = data_interface
        print(json.dumps(out, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, help="Path to schema JSON")
    parser.add_argument(
        "--ingest-if-missing",
        action="store_true",
        help="Allow Yahoo ingestion if schema permits",
    )
    parser.add_argument(
        "--data-dir", default=None, help="Ziplime data root, default: ~/.ziplime/data"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate schema and compile generated algorithm without running ziplime backtest",
    )
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
