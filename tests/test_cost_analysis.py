import pytest
import pandas as pd
import numpy as np

from src.battery_simulation import simulate_battery
from src.cost_analysis import format_wh, process_battery_data


class TestFormatWh:
    def test_none_returns_none(self):
        assert format_wh(None) is None

    def test_single_value(self):
        assert format_wh(1000) == 1.0

    def test_two_values(self):
        assert format_wh(1000, 2000) == 3.0

    def test_zero(self):
        assert format_wh(0) == 0.0


class TestProcessBatteryData:
    @pytest.fixture
    def simulated_df(self):
        dates = pd.date_range("2024-09-01", periods=96, freq="15min")
        np.random.seed(42)
        hours = (dates.hour + dates.minute / 60).values.astype(float)
        production = np.maximum(0, 1000 * np.sin(np.pi * (hours - 6) / 12))
        production[hours < 6] = 0
        production[hours > 18] = 0
        consumption = 300 + 100 * np.random.rand(96)

        df = pd.DataFrame({
            "produced_wh": production,
            "consumed_wh": consumption,
            "imported_wh": np.maximum(0, consumption - production),
            "exported_wh": np.maximum(0, production - consumption),
        }, index=dates)
        df.index.name = "time_stamp"

        return simulate_battery(
            df, max_battery_capacity_wh=10000,
            battery_discharge_lower_limit_pc=5,
            battery_charge_upper_limit_pc=100,
            battery_efficiency_pc=96,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=False)

    def test_returns_dataframe(self, simulated_df):
        result = process_battery_data(
            simulated_df, "2024-09-01", "2024-09-01",
            wh_price_high_eur=0.0002081,
            wh_price_low_eur=0.0001635,
            wh_price_sale_eur=0.0001000,
            subscription_monthly_fee_eur=47.02)
        assert isinstance(result, pd.DataFrame)

    def test_has_expected_categories(self, simulated_df):
        result = process_battery_data(
            simulated_df, "2024-09-01", "2024-09-01",
            wh_price_high_eur=0.0002081,
            wh_price_low_eur=0.0001635,
            wh_price_sale_eur=0.0001000,
            subscription_monthly_fee_eur=47.02)

        categories = result.index.get_level_values('Category').unique()
        assert 'Metric' in categories
        assert 'Total' in categories
        assert 'Saving' in categories

    def test_total_cost_exists(self, simulated_df):
        result = process_battery_data(
            simulated_df, "2024-09-01", "2024-09-01",
            wh_price_high_eur=0.0002081,
            wh_price_low_eur=0.0001635,
            wh_price_sale_eur=0.0001000,
            subscription_monthly_fee_eur=47.02)
        assert ('Total', 'Total Cost') in result.index

    def test_custom_hp_hours(self, simulated_df):
        result = process_battery_data(
            simulated_df, "2024-09-01", "2024-09-01",
            wh_price_high_eur=0.0002081,
            wh_price_low_eur=0.0001635,
            wh_price_sale_eur=0.0001000,
            subscription_monthly_fee_eur=47.02,
            hp_start_hour=8, hp_end_hour=20)
        assert isinstance(result, pd.DataFrame)
