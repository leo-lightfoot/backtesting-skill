TEMPLATE_NAME = "sma_crossover_long_only"
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


def _rebalance_key(sim_dt, rule, tz_name):
    local = sim_dt.astimezone(ZoneInfo(tz_name))
    if rule == "weekly":
        iso = local.isocalendar()
        return f"{iso[0]}-{iso[1]}"
    if rule == "monthly":
        return f"{local.year}-{local.month}"
    return f"{local.year}-{local.month}-{local.day}"


def _score_asset(metric, short_sma, long_sma, closes):
    if metric == "one_bar_return" and len(closes) >= 2:
        prev = float(closes[-2])
        if prev != 0:
            return float(closes[-1]) / prev - 1.0
        return -1e9
    if long_sma == 0:
        return -1e9
    return float(short_sma) / float(long_sma) - 1.0


async def initialize(context):
    context.assets = [await context.symbol(s) for s in PARAMS["symbols"]]
    context.last_rebalance_key = None


async def handle_data(context, data):
    assets = context.assets
    long_window = int(PARAMS["long_window"])
    short_window = int(PARAMS["short_window"])

    rule = str(PARAMS["rebalance_rule"])
    key = _rebalance_key(context.simulation_dt, rule, PARAMS["market_tz"])
    if context.last_rebalance_key == key:
        return
    context.last_rebalance_key = key

    hist = data.history(
        assets=assets,
        fields=["close"],
        bar_count=long_window,
        frequency=dt.timedelta(minutes=int(PARAMS["frequency_minutes"])),
    )
    if hist.is_empty():
        return

    candidates = []
    metric = str(PARAMS["rank_metric"])
    for asset in assets:
        frame = hist.filter(pl.col("sid") == asset.sid)
        if frame.is_empty():
            continue

        closes = frame["close"].to_numpy()
        if len(closes) < long_window:
            continue

        short_sma = _sma_last(closes, short_window)
        long_sma = _sma_last(closes, long_window)
        if np.isnan(short_sma) or np.isnan(long_sma):
            continue

        if short_sma > long_sma:
            score = _score_asset(metric, short_sma, long_sma, closes)
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
        "short_window": 50,
        "long_window": 200,
        "max_positions": len(symbols),
        "rank_metric": "ma_ratio",
        "rebalance_rule": "daily",
    }
