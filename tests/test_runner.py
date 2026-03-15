import importlib.util
import pathlib
import unittest
from types import SimpleNamespace

import pandas as pd


def _load_runner_module():
    root = pathlib.Path(__file__).resolve().parents[1]
    path = root / "scripts" / "run_backtest_from_schema.py"
    spec = importlib.util.spec_from_file_location("run_backtest_from_schema", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = _load_runner_module()

    # ------------------------------------------------------------------
    # Algorithm source compilation
    # ------------------------------------------------------------------

    def test_make_algorithm_source_supports_trend_template(self):
        params = {
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "sma_fast_period": 10,
            "sma_med_period": 20,
            "sma_slow_period": 50,
            "slope_lookback": 5,
            "touch_ma": "sma_fast",
            "bounce_range_ratio": 0.5,
            "exit_below_ma": "sma_med",
        }
        source = self.runner.make_algorithm_source("trend_dip_buy_long_only", params)
        self.assertIn("PARAMS =", source)
        self.assertIn("sma_fast_period", source)

    def test_make_algorithm_source_oversold_sets_context_asset(self):
        params = {
            "symbol": "QQQ",
            "symbols": ["QQQ"],
            "frequency_minutes": 5,
            "market_tz": "America/New_York",
            "ema_period": 10,
            "sma_period": 20,
            "ext_10": -0.3,
            "ext_20": -0.4,
            "min_down_days": 3,
            "range_mult": 1.5,
            "stop_buffer": 0.01,
            "max_hold_days": 3,
            "min_price": 5.0,
            "min_avg_daily_volume": 2000000,
            "entry_after_hour": 10,
            "entry_after_minute": 0,
            "setup_lookback_bars": 2500,
            "hl_window": 6,
        }
        source = self.runner.make_algorithm_source("oversold_bounce_long_only", params)
        self.assertIn("context.asset =", source)

    def test_make_algorithm_source_supports_rsi_template(self):
        params = {
            "symbol": "QQQ",
            "symbols": ["QQQ"],
            "frequency_minutes": 1440,
            "market_tz": "America/New_York",
            "rsi_period": 14,
            "oversold_threshold": 30.0,
            "exit_rsi": 60.0,
            "trend_filter_period": 200,
            "max_hold_days": 20,
            "min_price": 5.0,
            "min_avg_daily_volume": 2000000,
        }
        source = self.runner.make_algorithm_source("rsi_mean_reversion_long_only", params)
        self.assertIn("PARAMS =", source)
        self.assertIn("_rsi", source)
        self.assertIn("oversold_threshold", source)
        self.assertIn("trend_filter_period", source)

    # ------------------------------------------------------------------
    # build_params — defaults and validation
    # ------------------------------------------------------------------

    def test_build_params_defaults_for_trend_template(self):
        schema = {
            "template": "trend_dip_buy_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "timezone": "America/New_York",
            "params": {},
        }
        params = self.runner.build_params(schema)
        self.assertEqual(params["symbol"], "QQQ")
        self.assertEqual(params["frequency_minutes"], 1440)
        self.assertEqual(params["sma_fast_period"], 10)
        self.assertEqual(params["sma_med_period"], 20)
        self.assertEqual(params["sma_slow_period"], 50)
        self.assertEqual(params["touch_ma"], "sma_fast")
        self.assertEqual(params["exit_below_ma"], "sma_med")

    def test_build_params_defaults_for_rsi_template(self):
        schema = {
            "template": "rsi_mean_reversion_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "timezone": "America/New_York",
            "params": {},
        }
        params = self.runner.build_params(schema)
        self.assertEqual(params["symbol"], "QQQ")
        self.assertEqual(params["rsi_period"], 14)
        self.assertEqual(params["oversold_threshold"], 30.0)
        self.assertEqual(params["exit_rsi"], 60.0)
        self.assertEqual(params["trend_filter_period"], 200)
        self.assertEqual(params["max_hold_days"], 20)

    def test_build_params_uses_data_symbols_for_sma(self):
        schema = {
            "template": "sma_crossover_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "data": {"symbols": ["AAPL", "MSFT", "NVDA"]},
            "params": {},
        }
        params = self.runner.build_params(schema)
        self.assertEqual(params["symbols"], ["AAPL", "MSFT", "NVDA"])

    def test_build_params_has_portfolio_controls_for_sma(self):
        schema = {
            "template": "sma_crossover_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "timezone": "America/New_York",
            "data": {"symbols": ["AAPL", "MSFT", "NVDA"]},
            "params": {},
        }
        params = self.runner.build_params(schema)
        self.assertEqual(params["max_positions"], 3)
        self.assertEqual(params["rank_metric"], "ma_ratio")
        self.assertEqual(params["rebalance_rule"], "daily")

    def test_build_params_has_portfolio_controls_for_trend(self):
        schema = {
            "template": "trend_dip_buy_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "timezone": "America/New_York",
            "data": {"symbols": ["QQQ", "SPY"]},
            "params": {},
        }
        params = self.runner.build_params(schema)
        self.assertEqual(params["max_positions"], 2)
        self.assertEqual(params["rank_metric"], "trend_strength")
        self.assertEqual(params["rebalance_rule"], "daily")

    def test_build_params_supports_rebalance_and_max_positions_override(self):
        schema = {
            "template": "trend_dip_buy_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "timezone": "America/New_York",
            "data": {"symbols": ["QQQ", "SPY", "IWM"]},
            "params": {
                "max_positions": 1,
                "rebalance_rule": "weekly",
                "rank_metric": "close_vs_sma_slow",
            },
        }
        params = self.runner.build_params(schema)
        self.assertEqual(params["max_positions"], 1)
        self.assertEqual(params["rebalance_rule"], "weekly")
        self.assertEqual(params["rank_metric"], "close_vs_sma_slow")

    def test_build_params_rejects_invalid_rebalance_rule(self):
        schema = {
            "template": "sma_crossover_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "params": {"rebalance_rule": "hourly"},
        }
        with self.assertRaises(ValueError):
            self.runner.build_params(schema)

    def test_build_params_rejects_sma_crossover_short_ge_long(self):
        schema = {
            "template": "sma_crossover_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
            "params": {"short_window": 200, "long_window": 50},
        }
        with self.assertRaises(ValueError):
            self.runner.build_params(schema)

    # ------------------------------------------------------------------
    # Yahoo download wrapper
    # ------------------------------------------------------------------

    def test_yahoo_download_wrapper_flattens_multiindex(self):
        calls = []

        def fake_download(*args, **kwargs):
            calls.append(kwargs.copy())
            cols = pd.MultiIndex.from_tuples(
                [
                    ("Open", "QQQ"),
                    ("High", "QQQ"),
                    ("Low", "QQQ"),
                    ("Close", "QQQ"),
                    ("Volume", "QQQ"),
                ]
            )
            return pd.DataFrame([[1, 2, 0.5, 1.5, 1000]], columns=cols)

        wrapped = self.runner._wrap_yfinance_download(fake_download)
        out = wrapped("QQQ", start="2025-01-01", end="2025-01-10")

        self.assertFalse(isinstance(out.columns, pd.MultiIndex))
        self.assertEqual(list(out.columns), ["Open", "High", "Low", "Close", "Volume"])
        self.assertIn("multi_level_index", calls[0])
        self.assertFalse(calls[0]["multi_level_index"])

    def test_yahoo_download_wrapper_overrides_multi_level_index_true(self):
        calls = []

        def fake_download(*args, **kwargs):
            calls.append(kwargs.copy())
            cols = pd.MultiIndex.from_tuples(
                [("Open", "QQQ"), ("Close", "QQQ"), ("Volume", "QQQ")]
            )
            return pd.DataFrame([[1, 2, 3]], columns=cols)

        wrapped = self.runner._wrap_yfinance_download(fake_download)
        wrapped("QQQ", start="2025-01-01", end="2025-01-10", multi_level_index=True)

        self.assertFalse(calls[0]["multi_level_index"])

    def test_yahoo_download_wrapper_uses_multiindex_with_ticker_grouping(self):
        calls = []

        def fake_download(*args, **kwargs):
            calls.append(kwargs.copy())
            cols = pd.MultiIndex.from_tuples(
                [("QQQ", "Open"), ("QQQ", "Close"), ("QQQ", "Volume")]
            )
            return pd.DataFrame([[1, 2, 3]], columns=cols)

        wrapped = self.runner._wrap_yfinance_download(fake_download)
        wrapped(
            ["QQQ"],
            start="2025-01-01",
            end="2025-01-10",
            group_by="Ticker",
            multi_level_index=False,
        )

        self.assertTrue(calls[0]["multi_level_index"])

    # ------------------------------------------------------------------
    # Date utilities
    # ------------------------------------------------------------------

    def test_parse_date_supports_end_of_day(self):
        start_dt = self.runner.parse_date("2026-03-10", "America/New_York")
        end_dt = self.runner.parse_date(
            "2026-03-10", "America/New_York", end_of_day=True
        )

        self.assertEqual((start_dt.hour, start_dt.minute), (0, 0))
        self.assertEqual((end_dt.hour, end_dt.minute), (23, 59))

    # ------------------------------------------------------------------
    # Practical assessment
    # ------------------------------------------------------------------

    def test_practical_assessment_has_global_required_sections(self):
        schema = {
            "template": "trend_dip_buy_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
        }
        params = {
            "min_avg_daily_volume": 2_000_000,
            "min_price": 5.0,
        }
        metrics = {
            "sharpe": 0.86,
            "max_drawdown": -0.10,
        }

        assessment = self.runner.build_practical_assessment(
            schema=schema,
            params=params,
            metrics=metrics,
        )

        self.assertIn("future_leakage", assessment)
        self.assertIn("slippage_commission", assessment)
        self.assertIn("overfitting_risk", assessment)
        self.assertIn("capacity_liquidity", assessment)

    def test_practical_assessment_uses_grid_context_for_overfitting(self):
        schema = {
            "template": "trend_dip_buy_long_only",
            "symbol": "QQQ",
            "frequency_minutes": 1440,
        }
        params = {
            "min_avg_daily_volume": 2_000_000,
            "min_price": 5.0,
        }

        assessment = self.runner.build_practical_assessment(
            schema=schema,
            params=params,
            metrics={"sharpe": 0.8},
            grid_context={
                "total_trials": 16,
                "top_sharpe": 0.86,
                "second_sharpe": 0.83,
            },
        )

        overfit = assessment["overfitting_risk"]
        self.assertEqual(overfit["grid_trials"], 16)
        self.assertEqual(overfit["sharpe_gap_top1_top2"], 0.03)

    def test_practical_assessment_reads_execution_config(self):
        schema = {
            "symbol": "QQQ",
            "execution": {
                "same_bar_execution": True,
                "price_used_in_order_execution": "open",
                "costs": {
                    "slippage_bps": 9.0,
                    "volume_limit_fraction": 0.3,
                    "commission_per_share_usd": 0.004,
                },
            },
        }
        assessment = self.runner.build_practical_assessment(
            schema=schema,
            params={"min_price": 5.0, "min_avg_daily_volume": 2_000_000},
            metrics={"sharpe": 0.7},
        )

        self.assertTrue(assessment["future_leakage"]["same_bar_execution"])
        self.assertEqual(assessment["future_leakage"]["execution_price"], "open")
        self.assertEqual(assessment["slippage_commission"]["slippage_bps"], 9.0)
        self.assertEqual(
            assessment["slippage_commission"]["volume_limit_fraction"], 0.3
        )
        self.assertEqual(
            assessment["slippage_commission"]["commission_per_share_usd"], 0.004
        )

    # ------------------------------------------------------------------
    # Validation split
    # ------------------------------------------------------------------

    def test_resolve_validation_split_date_method(self):
        schema = {
            "start": "2024-01-01",
            "end": "2024-12-31",
            "validation_split": {
                "enabled": True,
                "method": "date",
                "split_date": "2024-07-01",
                "gap_bars": 1,
                "rank_on": "test_sharpe",
            },
        }

        split = self.runner.resolve_validation_split(schema)
        self.assertIsNotNone(split)
        self.assertEqual(split["train"]["start"], "2024-01-01")
        self.assertEqual(split["train"]["end"], "2024-06-30")
        self.assertEqual(split["test"]["start"], "2024-07-02")
        self.assertEqual(split["test"]["end"], "2024-12-31")
        self.assertEqual(split["rank_on"], "test_sharpe")

    def test_resolve_validation_split_ratio_method(self):
        schema = {
            "start": "2024-01-01",
            "end": "2024-01-11",
            "validation_split": {
                "enabled": True,
                "method": "ratio",
                "train_ratio": 0.6,
                "gap_bars": 0,
            },
        }

        split = self.runner.resolve_validation_split(schema)
        self.assertIsNotNone(split)
        self.assertEqual(split["train"]["start"], "2024-01-01")
        # split_date=2024-01-07 (Sun) is advanced to Mon 2024-01-08;
        # train_end = 2024-01-07, test_start = 2024-01-08
        self.assertEqual(split["train"]["end"], "2024-01-07")
        self.assertEqual(split["test"]["start"], "2024-01-08")
        self.assertEqual(split["test"]["end"], "2024-01-11")
        self.assertEqual(split["rank_on"], "test_sharpe")

    # ------------------------------------------------------------------
    # Grid utilities
    # ------------------------------------------------------------------

    def test_get_rank_metric_supports_test_prefix(self):
        row = {
            "metrics": {"sharpe": 0.2},
            "train": {"metrics": {"sharpe": 0.4}},
            "test": {"metrics": {"sharpe": 0.8}},
        }

        self.assertEqual(self.runner.get_rank_metric(row, "test_sharpe"), 0.8)
        self.assertEqual(self.runner.get_rank_metric(row, "train_sharpe"), 0.4)
        self.assertEqual(self.runner.get_rank_metric(row, "sharpe"), 0.2)

    def test_normalize_rank_by_defaults_to_test_in_split_mode(self):
        self.assertEqual(
            self.runner.normalize_rank_by("sharpe", validation_enabled=True),
            "test_sharpe",
        )
        self.assertEqual(
            self.runner.normalize_rank_by("test_sharpe", validation_enabled=True),
            "test_sharpe",
        )
        self.assertEqual(
            self.runner.normalize_rank_by("train_sharpe", validation_enabled=True),
            "train_sharpe",
        )
        self.assertEqual(
            self.runner.normalize_rank_by("sharpe", validation_enabled=False),
            "sharpe",
        )

    def test_attach_rank_values_adds_rank_value_field(self):
        rows = [
            {"metrics": {"sharpe": 0.4}},
            {"metrics": {"sharpe": 0.9}},
            {"metrics": {"sharpe": 0.1}},
        ]
        out = self.runner.attach_rank_values(rows, "sharpe")
        self.assertEqual(out[0]["rank_value"], 0.4)
        self.assertEqual(out[1]["rank_value"], 0.9)
        self.assertEqual(out[2]["rank_value"], 0.1)

    def test_build_stability_diagnostics_basic(self):
        rows = [
            {"params": {"a": 1}, "metrics": {"sharpe": 1.1}},
            {"params": {"a": 1}, "metrics": {"sharpe": 1.0}},
            {"params": {"a": 2}, "metrics": {"sharpe": 0.9}},
            {"params": {"a": 3}, "metrics": {"sharpe": 0.5}},
        ]
        out = self.runner.build_stability_diagnostics(rows, rank_by="sharpe", top_k=3)
        self.assertEqual(out["top_k"], 3)
        self.assertEqual(out["rank_metric"], "sharpe")
        self.assertEqual(out["top1"], 1.1)
        self.assertIn("parameter_concentration", out)
        self.assertIn("stability_label", out)

    # ------------------------------------------------------------------
    # Trade summary
    # ------------------------------------------------------------------

    def test_extract_trade_summary_from_perf(self):
        perf = pd.DataFrame(
            {
                "transactions": [
                    [{"sid": 1, "amount": 10, "price": 100.0}],
                    [],
                    [{"sid": 1, "amount": -10, "price": 110.0}],
                    [{"sid": 1, "amount": 5, "price": 120.0}],
                    [{"sid": 1, "amount": -5, "price": 114.0}],
                ]
            },
            index=pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                ]
            ),
        )

        summary = self.runner.extract_trade_summary_from_perf(perf)
        self.assertEqual(summary["trade_count"], 2)
        self.assertAlmostEqual(summary["win_rate"], 0.5, places=6)
        self.assertAlmostEqual(summary["avg_trade_return"], 0.025, places=6)
        self.assertAlmostEqual(summary["best_trade_return"], 0.10, places=6)
        self.assertAlmostEqual(summary["worst_trade_return"], -0.05, places=6)

    def test_extract_trade_summary_handles_missing_transactions(self):
        perf = pd.DataFrame({"returns": [0.01, -0.01]})
        summary = self.runner.extract_trade_summary_from_perf(perf)
        self.assertEqual(summary["trade_count"], 0)
        self.assertIsNone(summary["win_rate"])

    def test_extract_trade_summary_from_result_wrapper(self):
        perf = pd.DataFrame(
            {
                "transactions": [
                    [{"sid": 1, "amount": 1, "price": 10.0}],
                    [{"sid": 1, "amount": -1, "price": 11.0}],
                ]
            },
            index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        )
        result = SimpleNamespace(perf=perf)
        summary = self.runner.extract_trade_summary(result)
        self.assertEqual(summary["trade_count"], 1)
        self.assertAlmostEqual(summary["avg_trade_return"], 0.10, places=6)

    def test_extract_trade_summary_supports_transaction_objects(self):
        tx_buy = SimpleNamespace(
            asset=SimpleNamespace(sid=7),
            amount=10,
            price=100.0,
            dt=pd.Timestamp("2024-01-01"),
        )
        tx_sell = SimpleNamespace(
            asset=SimpleNamespace(sid=7),
            amount=-10,
            price=110.0,
            dt=pd.Timestamp("2024-01-03"),
        )
        perf = pd.DataFrame(
            {
                "transactions": [
                    [tx_buy],
                    [tx_sell],
                ]
            },
            index=pd.to_datetime(["2024-01-01", "2024-01-03"]),
        )

        summary = self.runner.extract_trade_summary_from_perf(perf)
        self.assertEqual(summary["trade_count"], 1)
        self.assertAlmostEqual(summary["avg_trade_return"], 0.10, places=6)

    # ------------------------------------------------------------------
    # Execution config
    # ------------------------------------------------------------------

    def test_build_execution_config_defaults(self):
        cfg = self.runner.build_execution_config({})
        self.assertEqual(cfg["max_leverage"], 1.0)
        self.assertFalse(cfg["same_bar_execution"])
        self.assertEqual(cfg["price_used_in_order_execution"], "close")
        self.assertEqual(cfg["slippage_bps"], 5.0)
        self.assertEqual(cfg["volume_limit_fraction"], 0.1)
        self.assertEqual(cfg["commission_per_share_usd"], 0.001)
        self.assertEqual(cfg["commission_min_trade_usd"], 0.0)

    def test_build_execution_config_overrides(self):
        schema = {
            "execution": {
                "max_leverage": 0.8,
                "same_bar_execution": True,
                "price_used_in_order_execution": "open",
                "costs": {
                    "slippage_bps": 8.0,
                    "volume_limit_fraction": 0.2,
                    "commission_per_share_usd": 0.002,
                    "commission_min_trade_usd": 1.0,
                },
            }
        }
        cfg = self.runner.build_execution_config(schema)
        self.assertEqual(cfg["max_leverage"], 0.8)
        self.assertTrue(cfg["same_bar_execution"])
        self.assertEqual(cfg["price_used_in_order_execution"], "open")
        self.assertEqual(cfg["slippage_bps"], 8.0)
        self.assertEqual(cfg["volume_limit_fraction"], 0.2)
        self.assertEqual(cfg["commission_per_share_usd"], 0.002)
        self.assertEqual(cfg["commission_min_trade_usd"], 1.0)

    # ------------------------------------------------------------------
    # Risk, capacity, data and live interfaces
    # ------------------------------------------------------------------

    def test_build_risk_attribution_from_perf(self):
        perf = pd.DataFrame(
            {
                "returns": [0.01, -0.02, 0.03, 0.01, -0.01],
                "benchmark_period_return": [0.02, -0.01, 0.01, 0.0, -0.02],
            }
        )
        out = self.runner.build_risk_attribution_from_perf(perf)
        self.assertIn("corr_with_benchmark", out)
        self.assertIn("beta_up", out)
        self.assertIn("beta_down", out)
        self.assertIn("capture_up", out)
        self.assertIn("capture_down", out)
        self.assertIn("rolling_sharpe_63_end", out)

    def test_build_capacity_diagnostics_from_perf(self):
        perf = pd.DataFrame(
            {
                "portfolio_value": [100000.0, 101000.0, 100500.0],
                "transactions": [
                    [{"sid": 1, "amount": 10, "price": 100.0}],
                    [{"sid": 1, "amount": -5, "price": 102.0}],
                    [],
                ],
            }
        )
        params = {
            "min_avg_daily_volume": 2_000_000,
            "min_price": 5.0,
        }
        out = self.runner.build_capacity_diagnostics_from_perf(perf, params)
        self.assertIn("avg_daily_trade_notional", out)
        self.assertIn("avg_daily_turnover", out)
        self.assertIn("annualized_turnover", out)
        self.assertIn("participation_vs_adv_floor", out)
        self.assertIn("participation_risk", out)
        self.assertIsNotNone(out["participation_vs_adv_floor"])

    def test_build_capacity_diagnostics_without_adv_floor(self):
        perf = pd.DataFrame(
            {
                "portfolio_value": [100000.0, 101000.0],
                "transactions": [
                    [{"sid": 1, "amount": 10, "price": 100.0}],
                    [{"sid": 1, "amount": -10, "price": 100.0}],
                ],
            }
        )
        out = self.runner.build_capacity_diagnostics_from_perf(perf, params={})
        self.assertIsNone(out["adv_floor_dollar"])
        self.assertIsNone(out["participation_vs_adv_floor"])
        self.assertEqual(out["participation_risk"], "not_assessed")

    def test_build_live_interface_reserved(self):
        schema = {
            "live_data": {
                "enabled": True,
                "provider": "ibkr",
                "host": "127.0.0.1",
                "port": 7497,
                "client_id": 12,
            }
        }
        out = self.runner.build_live_interface(schema)
        self.assertEqual(out["status"], "reserved_interface_only")
        self.assertEqual(out["provider"], "ibkr")
        self.assertIn("next_step_hint", out)

    def test_build_live_interface_missing_required_fields(self):
        schema = {
            "live_data": {
                "enabled": True,
                "provider": "ibkr",
            }
        }
        out = self.runner.build_live_interface(schema)
        self.assertIn("required_fields_missing", out)
        self.assertTrue(len(out["required_fields_missing"]) >= 1)

    def test_build_data_interface_bundle_active(self):
        schema = {
            "data": {
                "source": "bundle",
                "symbols": ["QQQ"],
            }
        }
        out = self.runner.build_data_interface(schema)
        self.assertEqual(out["status"], "active")
        self.assertEqual(out["source"], "bundle")

    def test_build_data_interface_csv_reserved(self):
        schema = {
            "data": {
                "source": "csv",
            }
        }
        out = self.runner.build_data_interface(schema)
        self.assertEqual(out["status"], "reserved_interface_only")
        self.assertIn("required_fields_missing", out)


if __name__ == "__main__":
    unittest.main()
