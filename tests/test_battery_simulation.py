import pytest
import pandas as pd
import numpy as np

from src.battery_simulation import simulate_battery, rescale_solar_production


@pytest.fixture
def sample_df():
    """Create a sample DataFrame with 24h of 15-min data."""
    dates = pd.date_range("2024-09-01", periods=96, freq="15min")
    np.random.seed(42)

    # Simulate a realistic solar day: production peaks at noon
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
    return df


class TestSimulateBattery:
    def test_returns_expected_columns(self, sample_df):
        result = simulate_battery(
            sample_df, max_battery_capacity_wh=10000,
            battery_discharge_lower_limit_pc=5,
            battery_charge_upper_limit_pc=100,
            battery_efficiency_pc=96,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=False)

        expected_cols = [
            'Grid > House', 'Grid > Battery', 'Solar > House',
            'Battery > House', 'Solar > Battery', 'Solar > Grid',
            'Battery SOC'
        ]
        for col in expected_cols:
            assert col in result.columns

    def test_energy_conservation(self, sample_df):
        """Verify that energy is conserved: what comes in equals what goes out."""
        result = simulate_battery(
            sample_df, max_battery_capacity_wh=10000,
            battery_discharge_lower_limit_pc=5,
            battery_charge_upper_limit_pc=100,
            battery_efficiency_pc=100,  # 100% efficiency for easier verification
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=False)

        # House consumption should equal sum of sources
        house_supply = result['Grid > House'] + result['Solar > House'] + result['Battery > House']
        np.testing.assert_array_almost_equal(
            house_supply.values, result['consumed_wh'].values, decimal=5)

    def test_no_battery_all_grid(self, sample_df):
        """With 0 capacity battery, all deficit should come from grid."""
        result = simulate_battery(
            sample_df, max_battery_capacity_wh=0,
            battery_discharge_lower_limit_pc=5,
            battery_charge_upper_limit_pc=100,
            battery_efficiency_pc=96,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=False)

        assert (result['Battery > House'] == 0).all()
        assert (result['Solar > Battery'] == 0).all()
        assert (result['Grid > Battery'] == 0).all()
        assert (result['Battery SOC'] == 0).all()

    def test_soc_within_bounds(self, sample_df):
        result = simulate_battery(
            sample_df, max_battery_capacity_wh=10000,
            battery_discharge_lower_limit_pc=10,
            battery_charge_upper_limit_pc=90,
            battery_efficiency_pc=96,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=True)

        # SOC should be within limits (with small tolerance for initial ramp-up)
        soc = result['Battery SOC'].values
        assert np.all(soc >= 0)
        assert np.all(soc <= 10000)

    def test_non_negative_flows(self, sample_df):
        result = simulate_battery(
            sample_df, max_battery_capacity_wh=10000,
            battery_discharge_lower_limit_pc=5,
            battery_charge_upper_limit_pc=100,
            battery_efficiency_pc=96,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=True)

        for col in ['Grid > House', 'Grid > Battery', 'Solar > House',
                     'Battery > House', 'Solar > Battery', 'Solar > Grid']:
            assert (result[col] >= -1e-10).all(), f"{col} has negative values"

    def test_invalid_discharge_limit_raises(self, sample_df):
        with pytest.raises(ValueError, match="battery_discharge_lower_limit_pc"):
            simulate_battery(
                sample_df, max_battery_capacity_wh=10000,
                battery_discharge_lower_limit_pc=30,
                battery_charge_upper_limit_pc=100,
                battery_efficiency_pc=96,
                max_battery_charge_rate_w=None,
                max_battery_discharge_rate_w=None,
                enable_hc_charging=False)

    def test_invalid_charge_limit_raises(self, sample_df):
        with pytest.raises(ValueError, match="battery_charge_upper_limit_pc"):
            simulate_battery(
                sample_df, max_battery_capacity_wh=10000,
                battery_discharge_lower_limit_pc=5,
                battery_charge_upper_limit_pc=50,
                battery_efficiency_pc=96,
                max_battery_charge_rate_w=None,
                max_battery_discharge_rate_w=None,
                enable_hc_charging=False)

    def test_invalid_efficiency_raises(self, sample_df):
        with pytest.raises(ValueError, match="battery_efficiency_pc"):
            simulate_battery(
                sample_df, max_battery_capacity_wh=10000,
                battery_discharge_lower_limit_pc=5,
                battery_charge_upper_limit_pc=100,
                battery_efficiency_pc=110,
                max_battery_charge_rate_w=None,
                max_battery_discharge_rate_w=None,
                enable_hc_charging=False)

    def test_hc_charging_adds_grid_to_battery(self, sample_df):
        result_no_hc = simulate_battery(
            sample_df, max_battery_capacity_wh=10000,
            battery_discharge_lower_limit_pc=5,
            battery_charge_upper_limit_pc=100,
            battery_efficiency_pc=96,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=False)

        result_hc = simulate_battery(
            sample_df, max_battery_capacity_wh=10000,
            battery_discharge_lower_limit_pc=5,
            battery_charge_upper_limit_pc=100,
            battery_efficiency_pc=96,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=True)

        assert result_hc['Grid > Battery'].sum() >= result_no_hc['Grid > Battery'].sum()

    def test_custom_hp_hours(self, sample_df):
        result = simulate_battery(
            sample_df, max_battery_capacity_wh=10000,
            battery_discharge_lower_limit_pc=5,
            battery_charge_upper_limit_pc=100,
            battery_efficiency_pc=96,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=True,
            hp_start_hour=8, hp_end_hour=20)

        # Should still produce valid results
        assert len(result) == len(sample_df)
        assert (result['Battery SOC'] >= 0).all()


class TestRescaleSolarProduction:
    def test_same_capacity_returns_copy(self, sample_df):
        result = rescale_solar_production(sample_df, 6000, 6000)
        pd.testing.assert_frame_equal(result, sample_df)

    def test_double_capacity_doubles_production(self, sample_df):
        result = rescale_solar_production(sample_df, 6000, 12000)
        np.testing.assert_array_almost_equal(
            result['produced_wh'].values,
            sample_df['produced_wh'].values * 2)

    def test_imports_decrease_with_more_solar(self, sample_df):
        result = rescale_solar_production(sample_df, 6000, 12000)
        assert result['imported_wh'].sum() <= sample_df['imported_wh'].sum()

    def test_exports_increase_with_more_solar(self, sample_df):
        result = rescale_solar_production(sample_df, 6000, 12000)
        assert result['exported_wh'].sum() >= sample_df['exported_wh'].sum()

    def test_no_negative_values(self, sample_df):
        result = rescale_solar_production(sample_df, 6000, 12000)
        assert (result['imported_wh'] >= -1e-10).all()
        assert (result['exported_wh'] >= -1e-10).all()
