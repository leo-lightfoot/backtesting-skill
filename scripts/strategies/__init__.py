from . import oversold_bounce, rsi_mean_reversion, sma_crossover, trend_dip_buy
from typing import Any

REGISTRY: dict[str, Any] = {
    oversold_bounce.TEMPLATE_NAME: oversold_bounce,
    rsi_mean_reversion.TEMPLATE_NAME: rsi_mean_reversion,
    sma_crossover.TEMPLATE_NAME: sma_crossover,
    trend_dip_buy.TEMPLATE_NAME: trend_dip_buy,
}
