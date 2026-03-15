# Static metadata for every strategy template.
# Param names match the two-tier schema format (schema_adapter.py).
# The frontend uses this to render the correct form fields per strategy.

TEMPLATES = [
    {
        "id": "rsi_mean_reversion_long_only",
        "name": "RSI Mean Reversion",
        "description": (
            "Buys when RSI drops into oversold territory while price is above "
            "a long-term trend filter. Exits when RSI recovers or after a max hold period."
        ),
        "frequency": "daily",
        "multi_symbol": False,
        "params": {
            "rsi_period": {
                "type": "int",
                "default": 14,
                "min": 2,
                "max": 50,
                "label": "RSI Period",
            },
            "oversold_threshold": {
                "type": "float",
                "default": 30,
                "min": 10,
                "max": 50,
                "label": "Oversold Threshold",
            },
            "exit_rsi": {
                "type": "float",
                "default": 60,
                "min": 50,
                "max": 90,
                "label": "Exit RSI",
            },
            "trend_filter_period": {
                "type": "int",
                "default": 200,
                "min": 50,
                "max": 300,
                "label": "Trend Filter (SMA Period)",
            },
            "max_hold_days": {
                "type": "int",
                "default": 20,
                "min": 1,
                "max": 60,
                "label": "Max Hold Days",
            },
        },
    },
    {
        "id": "sma_crossover_long_only",
        "name": "SMA Crossover",
        "description": (
            "Buys when the short-term SMA crosses above the long-term SMA. "
            "Supports multiple symbols ranked by MA ratio."
        ),
        "frequency": "daily",
        "multi_symbol": True,
        "params": {
            "short_ma": {
                "type": "int",
                "default": 50,
                "min": 5,
                "max": 100,
                "label": "Short MA Period",
            },
            "long_ma": {
                "type": "int",
                "default": 200,
                "min": 50,
                "max": 300,
                "label": "Long MA Period",
            },
        },
    },
    {
        "id": "trend_dip_buy_long_only",
        "name": "Trend Dip Buy",
        "description": (
            "Buys pullbacks in an established uptrend using three moving averages. "
            "Exits when price closes below a chosen MA."
        ),
        "frequency": "daily",
        "multi_symbol": True,
        "params": {
            "fast_ma": {
                "type": "int",
                "default": 10,
                "min": 3,
                "max": 50,
                "label": "Fast MA Period",
            },
            "medium_ma": {
                "type": "int",
                "default": 20,
                "min": 10,
                "max": 100,
                "label": "Medium MA Period",
            },
            "slow_ma": {
                "type": "int",
                "default": 50,
                "min": 20,
                "max": 200,
                "label": "Slow MA Period",
            },
            "entry_on": {
                "type": "select",
                "default": "fast",
                "options": ["fast", "medium", "slow"],
                "label": "Entry MA",
            },
            "exit_below": {
                "type": "select",
                "default": "medium",
                "options": ["fast", "medium", "slow"],
                "label": "Exit Below MA",
            },
        },
    },
]

# Lookup by id for O(1) access
TEMPLATES_BY_ID: dict = {t["id"]: t for t in TEMPLATES}
