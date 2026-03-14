TEMPLATE_NAME = "trend_dip_buy_long_only"
HAS_PORTFOLIO_CONTROLS = True

ALGORITHM_SOURCE = """
import datetime as dt
import numpy as np
import polars as pl
from zoneinfo import ZoneInfo

from ziplime.finance.execution import MarketOrder

PARAMS = __PARAMS_JSON__


def _sma_last(values, period):
    if len(values) < period:
        return float("nan")
    return float(np.mean(values[-period:]))


def _sma_shifted(values, period, shift):
    end = len(values) - int(shift)
    start = end - int(period)
    if start < 0 or end <= start:
        return float("nan")
    return float(np.mean(values[start:end]))


def _select_ma(name, sma_fast, sma_med, sma_slow):
    if name == "sma_fast":
        return float(sma_fast)
    if name == "sma_slow":
        return float(sma_slow)
    return float(sma_med)


def _rebalance_key(sim_dt, rule, tz_name):
    local = sim_dt.astimezone(ZoneInfo(tz_name))
    if rule == "weekly":
        iso = local.isocalendar()
        return f"{iso[0]}-{iso[1]}"
    if rule == "monthly":
        return f"{local.year}-{local.month}"
    return f"{local.year}-{local.month}-{local.day}"


def _score_asset(metric, close_today, sma_fast, sma_med, sma_slow, vol_today, avg_vol_20):
    if metric == "close_vs_sma_slow" and sma_slow != 0:
        return float(close_today) / float(sma_slow) - 1.0
    if metric == "volume_ratio" and avg_vol_20 > 0:
        return float(vol_today) / float(avg_vol_20)
    if sma_med == 0:
        return -1e9
    return float(sma_fast) / float(sma_med) - 1.0


async def initialize(context):
    context.assets = [await context.symbol(s) for s in PARAMS["symbols"]]
    context.last_rebalance_key = None


async def handle_data(context, data):
    assets = context.assets

    fast = int(PARAMS["sma_fast_period"])
    med = int(PARAMS["sma_med_period"])
    slow = int(PARAMS["sma_slow_period"])
    slope_lookback = int(PARAMS["slope_lookback"])
    freq_min = int(PARAMS["frequency_minutes"])

    rule = str(PARAMS["rebalance_rule"])
    key = _rebalance_key(context.simulation_dt, rule, PARAMS["market_tz"])
    if context.last_rebalance_key == key:
        return
    context.last_rebalance_key = key

    required = slow + slope_lookback + 2
    bar_count = max(required, 90)

    hist = data.history(
        assets=assets,
        fields=["open", "high", "low", "close", "volume"],
        bar_count=bar_count,
        frequency=dt.timedelta(minutes=freq_min),
    )
    if hist.is_empty():
        return

    candidates = []
    metric = str(PARAMS["rank_metric"])
    for asset in assets:
        frame = hist.filter(pl.col("sid") == asset.sid)
        pos = getattr(context.portfolio.positions.get(asset, 0), "amount", 0)
        in_position = pos > 0

        if frame.is_empty():
            if in_position:
                desired_assets.append(asset)
            continue

        closes = frame["close"].to_numpy()
        highs = frame["high"].to_numpy()
        lows = frame["low"].to_numpy()
        vols = frame["volume"].to_numpy()

        if len(closes) < required or len(vols) < 20:
            if in_position:
                desired_assets.append(asset)
            continue

        close_today = float(closes[-1])
        high_today = float(highs[-1])
        low_today = float(lows[-1])
        vol_today = float(vols[-1])
        avg_vol_20 = float(np.mean(vols[-20:]))

        if close_today < float(PARAMS["min_price"]) or avg_vol_20 < float(PARAMS["min_avg_daily_volume"]):
            continue

        sma_fast = _sma_last(closes, fast)
        sma_med = _sma_last(closes, med)
        sma_slow = _sma_last(closes, slow)
        if np.isnan(sma_fast) or np.isnan(sma_med) or np.isnan(sma_slow):
            continue

        sma_fast_prev = _sma_shifted(closes, fast, slope_lookback)
        sma_med_prev = _sma_shifted(closes, med, slope_lookback)
        sma_slow_prev = _sma_shifted(closes, slow, slope_lookback)
        if np.isnan(sma_fast_prev) or np.isnan(sma_med_prev) or np.isnan(sma_slow_prev):
            continue

        regime_ok = (
            (sma_fast > sma_med)
            and (close_today > sma_slow)
            and (sma_fast > sma_fast_prev)
            and (sma_med > sma_med_prev)
            and (sma_slow > sma_slow_prev)
        )

        touch_name = str(PARAMS["touch_ma"])
        touch_ma = _select_ma(touch_name, sma_fast, sma_med, sma_slow)
        touched = low_today <= touch_ma

        day_range = high_today - low_today
        bounce_ok = False
        if day_range > 0:
            close_pos = (close_today - low_today) / day_range
            bounce_ok = close_pos >= float(PARAMS["bounce_range_ratio"])

        exit_name = str(PARAMS["exit_below_ma"])
        exit_ma = _select_ma(exit_name, sma_fast, sma_med, sma_slow)

        should_hold = False
        if in_position:
            should_hold = close_today >= exit_ma
        elif regime_ok and touched and bounce_ok:
            should_hold = True

        if should_hold:
            score = _score_asset(
                metric,
                close_today,
                sma_fast,
                sma_med,
                sma_slow,
                vol_today,
                avg_vol_20,
            )
            candidates.append((float(score), asset))

    candidates.sort(key=lambda x: x[0], reverse=True)
    max_positions = max(1, int(PARAMS["max_positions"]))
    desired_assets = [asset for _, asset in candidates[:max_positions]]

    desired_sids = {a.sid for a in desired_assets}
    target = (1.0 / len(desired_assets)) if len(desired_assets) > 0 else 0.0

    for asset in assets:
        pos = getattr(context.portfolio.positions.get(asset, 0), "amount", 0)
        if asset.sid in desired_sids:
            await context.order_target_percent(asset=asset, target=target, style=MarketOrder())
        elif pos > 0:
            await context.order_target_percent(asset=asset, target=0.0, style=MarketOrder())
"""


def get_defaults(
    symbol: str, symbols: list, frequency_minutes: int, market_tz: str
) -> dict:
    return {
        "symbol": symbol,
        "symbols": symbols,
        "frequency_minutes": frequency_minutes,
        "market_tz": market_tz,
        "sma_fast_period": 10,
        "sma_med_period": 20,
        "sma_slow_period": 50,
        "slope_lookback": 5,
        "touch_ma": "sma_fast",
        "bounce_range_ratio": 0.5,
        "exit_below_ma": "sma_med",
        "min_price": 5.0,
        "min_avg_daily_volume": 2_000_000,
        "max_positions": len(symbols),
        "rank_metric": "trend_strength",
        "rebalance_rule": "daily",
    }
