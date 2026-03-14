TEMPLATE_NAME = "oversold_bounce_long_only"
HAS_PORTFOLIO_CONTROLS = False

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


def _ema_last(values, period):
    if len(values) < period:
        return float("nan")
    alpha = 2.0 / (period + 1.0)
    ema = float(values[0])
    for v in values[1:]:
        ema = alpha * float(v) + (1.0 - alpha) * ema
    return ema


def _consecutive_down(closes):
    if len(closes) < 2:
        return 0
    c = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            c += 1
        else:
            break
    return c


def _higher_low_simple(lows, closes):
    if len(lows) < 4 or len(closes) < 3:
        return False
    return (lows[-1] > lows[-3]) and (closes[-1] >= closes[-2])


def _to_daily(intra_df, sid, today_date):
    if intra_df.is_empty():
        return pl.DataFrame()

    df = (
        intra_df
        .filter(pl.col("sid") == sid)
        .select("date", "open", "high", "low", "close", "volume")
    )

    if df.is_empty():
        return pl.DataFrame()

    daily = (
        df.with_columns(day=pl.col("date").dt.date())
        .group_by("day")
        .agg(
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
        )
        .sort("day")
        .rename({"day": "date"})
        .filter(pl.col("date") < today_date)
    )
    return daily


def _compute_setup(daily):
    if daily.height < 25:
        return {"ok": False}

    closes = daily["close"].to_numpy()
    highs = daily["high"].to_numpy()
    lows = daily["low"].to_numpy()
    vols = daily["volume"].to_numpy()

    last_close = float(closes[-1])
    avg_vol_20 = float(np.mean(vols[-20:]))
    ema10 = _ema_last(closes, int(PARAMS["ema_period"]))
    sma20 = _sma_last(closes, int(PARAMS["sma_period"]))
    adr20 = float(np.mean((highs - lows)[-20:]))

    ext_10 = (last_close - ema10) / ema10 if ema10 and not np.isnan(ema10) else float("nan")
    ext_20 = (last_close - sma20) / sma20 if sma20 and not np.isnan(sma20) else float("nan")
    down_days = _consecutive_down(closes)

    ok_base = (last_close >= float(PARAMS["min_price"])) and (avg_vol_20 >= float(PARAMS["min_avg_daily_volume"]))
    ok_oversold = (
        (ext_10 <= float(PARAMS["ext_10"]))
        and (ext_20 <= float(PARAMS["ext_20"]))
        and (down_days >= int(PARAMS["min_down_days"]))
    )

    return {
        "ok": bool(ok_base and ok_oversold),
        "ema10": float(ema10),
        "sma20": float(sma20),
        "adr20": float(adr20),
        "prev_day_low": float(lows[-1]),
    }


def _is_after_time(sim_dt):
    local = sim_dt.astimezone(ZoneInfo(PARAMS["market_tz"]))
    return (local.hour, local.minute) >= (int(PARAMS["entry_after_hour"]), int(PARAMS["entry_after_minute"]))


async def initialize(context):
    context.assets = [await context.symbol(s) for s in PARAMS["symbols"]]
    context.asset = context.assets[0]

    context.current_day = None
    context.today_open = None
    context.hod = None
    context.lod = None
    context.vwap_num = 0.0
    context.vwap_den = 0.0
    context.prev_price = None

    context.setup = {"ok": False}
    context.entry_day = None
    context.days_held = 0
    context.scaled_out = False


async def handle_data(context, data):
    asset = context.asset
    cur = data.current(assets=[asset], fields=["open", "high", "low", "close", "volume", "price"])
    if cur.is_empty():
        return

    cur_open = float(cur["open"][0])
    cur_high = float(cur["high"][0])
    cur_low = float(cur["low"][0])
    cur_close = float(cur["close"][0])
    cur_vol = float(cur["volume"][0])
    cur_price = float(cur["price"][0])

    sim_dt = context.simulation_dt
    today = sim_dt.astimezone(ZoneInfo(PARAMS["market_tz"])).date()

    if context.current_day != today:
        context.current_day = today
        context.today_open = cur_open
        context.hod = cur_high
        context.lod = cur_low
        context.vwap_num = 0.0
        context.vwap_den = 0.0
        context.prev_price = None

        if context.entry_day is not None:
            context.days_held += 1

        intra_hist = data.history(
            assets=[asset],
            fields=["open", "high", "low", "close", "volume"],
            bar_count=int(PARAMS["setup_lookback_bars"]),
            frequency=dt.timedelta(minutes=int(PARAMS["frequency_minutes"])),
        )
        daily = _to_daily(intra_hist, sid=asset.sid, today_date=today)
        context.setup = _compute_setup(daily)

    context.hod = max(context.hod, cur_high) if context.hod is not None else cur_high
    context.lod = min(context.lod, cur_low) if context.lod is not None else cur_low

    typical = (cur_high + cur_low + cur_close) / 3.0
    context.vwap_num += typical * cur_vol
    context.vwap_den += cur_vol
    vwap = context.vwap_num / context.vwap_den if context.vwap_den > 0 else float("nan")

    position_amount = getattr(context.portfolio.positions.get(asset, 0), "amount", 0)
    in_position = position_amount > 0

    stop_price = context.lod * (1.0 - float(PARAMS["stop_buffer"])) if context.lod is not None else None

    # exits
    if in_position:
        if stop_price is not None and cur_price <= stop_price:
            await context.order_target_percent(asset=asset, target=0.0, style=MarketOrder())
            context.entry_day = None
            context.days_held = 0
            context.scaled_out = False
            return

        if context.days_held >= int(PARAMS["max_hold_days"]):
            await context.order_target_percent(asset=asset, target=0.0, style=MarketOrder())
            context.entry_day = None
            context.days_held = 0
            context.scaled_out = False
            return

        ema10 = float(context.setup.get("ema10", float("nan")))
        sma20 = float(context.setup.get("sma20", float("nan")))

        if (not context.scaled_out) and (not np.isnan(ema10)) and cur_price >= ema10:
            await context.order_target_percent(asset=asset, target=0.5, style=MarketOrder())
            context.scaled_out = True

        if (not np.isnan(sma20)) and cur_price >= sma20:
            await context.order_target_percent(asset=asset, target=0.0, style=MarketOrder())
            context.entry_day = None
            context.days_held = 0
            context.scaled_out = False
            return

        return

    # entries
    setup_ok = bool(context.setup.get("ok", False))
    adr20 = float(context.setup.get("adr20", float("nan")))
    intraday_range_ok = (
        (context.hod - context.lod) >= (float(PARAMS["range_mult"]) * adr20)
        if (context.hod is not None and context.lod is not None and not np.isnan(adr20))
        else False
    )

    if setup_ok and intraday_range_ok:
        prev_day_low = float(context.setup.get("prev_day_low", float("nan")))
        crossed_up = (
            (context.prev_price is not None)
            and (context.prev_price <= prev_day_low)
            and (cur_price > prev_day_low)
        )

        trigger_a = (context.today_open is not None) and (context.today_open < prev_day_low) and crossed_up

        trigger_b = False
        if _is_after_time(sim_dt) and (not np.isnan(vwap)) and (cur_price > vwap):
            win = max(int(PARAMS["hl_window"]), 6)
            intraday_win = data.history(
                assets=[asset],
                fields=["date", "low", "close"],
                bar_count=win,
                frequency=dt.timedelta(minutes=int(PARAMS["frequency_minutes"])),
            )
            if not intraday_win.is_empty():
                same_day = (
                    intraday_win
                    .filter(pl.col("sid") == asset.sid)
                    .with_columns(day=pl.col("date").dt.date())
                    .filter(pl.col("day") == today)
                )
                if same_day.height >= 4:
                    lows = same_day["low"].to_numpy()
                    closes = same_day["close"].to_numpy()
                    trigger_b = _higher_low_simple(lows, closes)

        if trigger_a or trigger_b:
            await context.order_target_percent(asset=asset, target=1.0, style=MarketOrder())
            context.entry_day = today
            context.days_held = 0
            context.scaled_out = False

    context.prev_price = cur_price
"""


def get_defaults(
    symbol: str, symbols: list, frequency_minutes: int, market_tz: str
) -> dict:
    return {
        "symbol": symbol,
        "symbols": symbols,
        "frequency_minutes": frequency_minutes,
        "market_tz": market_tz,
        "ema_period": 10,
        "sma_period": 20,
        "ext_10": -0.30,
        "ext_20": -0.40,
        "min_down_days": 3,
        "range_mult": 1.5,
        "stop_buffer": 0.01,
        "max_hold_days": 3,
        "min_price": 5.0,
        "min_avg_daily_volume": 2_000_000,
        "entry_after_hour": 10,
        "entry_after_minute": 0,
        "setup_lookback_bars": 2500,
        "hl_window": 6,
    }
