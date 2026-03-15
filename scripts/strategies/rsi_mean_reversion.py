TEMPLATE_NAME = "rsi_mean_reversion_long_only"
HAS_PORTFOLIO_CONTROLS = False

ALGORITHM_SOURCE = """
import datetime as dt
import numpy as np
import polars as pl

from ziplime.finance.execution import MarketOrder

PARAMS = __PARAMS_JSON__


def _sma_last(values, period):
    if len(values) < period:
        return float("nan")
    return float(np.mean(values[-period:]))


def _rsi(values, period):
    \"\"\"Wilder's RSI using exponential smoothing (alpha = 1/period).\"\"\"
    needed = period + 1
    if len(values) < needed:
        return float("nan")
    window = np.array(values[-needed:], dtype=float)
    deltas = np.diff(window)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    alpha = 1.0 / float(period)
    avg_gain = float(gains[0])
    avg_loss = float(losses[0])
    for g, l in zip(gains[1:], losses[1:]):
        avg_gain = alpha * float(g) + (1.0 - alpha) * avg_gain
        avg_loss = alpha * float(l) + (1.0 - alpha) * avg_loss
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


async def initialize(context):
    context.asset = await context.symbol(PARAMS["symbol"])
    context.days_held = 0


async def handle_data(context, data):
    asset = context.asset
    rsi_period = int(PARAMS["rsi_period"])
    trend_period = int(PARAMS["trend_filter_period"])
    freq_min = int(PARAMS["frequency_minutes"])

    bar_count = max(trend_period + 5, rsi_period + 10, 60)

    hist = data.history(
        assets=[asset],
        fields=["close", "volume"],
        bar_count=bar_count,
        frequency=dt.timedelta(minutes=freq_min),
    )
    if hist.is_empty():
        return

    frame = hist.filter(pl.col("sid") == asset.sid)
    if frame.is_empty():
        return

    closes = frame["close"].to_numpy()
    vols = frame["volume"].to_numpy()

    if len(closes) < trend_period + 1 or len(vols) < 20:
        return

    close_today = float(closes[-1])
    avg_vol_20 = float(np.mean(vols[-20:]))

    if close_today < float(PARAMS["min_price"]) or avg_vol_20 < float(PARAMS["min_avg_daily_volume"]):
        return

    rsi_val = _rsi(closes, rsi_period)
    trend_sma = _sma_last(closes, trend_period)

    if np.isnan(rsi_val) or np.isnan(trend_sma):
        return

    in_position = (
        asset in context.portfolio.positions
        and context.portfolio.positions[asset].amount > 0
    )

    if in_position:
        context.days_held += 1
        rsi_recovered = rsi_val > float(PARAMS["exit_rsi"])
        held_too_long = context.days_held >= int(PARAMS["max_hold_days"])
        if rsi_recovered or held_too_long:
            await context.order_target_percent(asset=asset, target=0.0, style=MarketOrder())
            context.days_held = 0
    else:
        oversold = rsi_val < float(PARAMS["oversold_threshold"])
        in_uptrend = close_today > trend_sma
        if oversold and in_uptrend:
            await context.order_target_percent(asset=asset, target=1.0, style=MarketOrder())
            context.days_held = 0
"""


def get_defaults(
    symbol: str, symbols: list, frequency_minutes: int, market_tz: str
) -> dict:
    return {
        "symbol": symbol,
        "symbols": symbols,
        "frequency_minutes": frequency_minutes,
        "market_tz": market_tz,
        "rsi_period": 14,
        "oversold_threshold": 30.0,
        "exit_rsi": 60.0,
        "trend_filter_period": 200,
        "max_hold_days": 20,
        "min_price": 5.0,
        "min_avg_daily_volume": 2_000_000,
    }
