import pytest
import pandas as pd
import numpy as np
import os
import tempfile

from src.data_loader import load_and_prepare_data, filter_data


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV file for testing."""
    csv_content = (
        "Date/Heure,Énergie produite (Wh),Énergie consommée (Wh),"
        "Importée depuis le réseau (Wh),Exportée vers le réseau (Wh)\n"
        "09/01/2024 00:00,0,500,500,0\n"
        "09/01/2024 00:15,0,400,400,0\n"
        "09/01/2024 06:00,100,300,200,0\n"
        "09/01/2024 08:00,800,300,0,500\n"
        "09/01/2024 12:00,1500,600,0,900\n"
        "09/01/2024 18:00,200,700,500,0\n"
        "09/01/2024 23:00,0,300,300,0\n"
    )
    csv_file = tmp_path / "test_data.csv"
    csv_file.write_text(csv_content)
    return str(csv_file)


@pytest.fixture
def columns_map():
    return {
        "produced_wh": "Énergie produite (Wh)",
        "consumed_wh": "Énergie consommée (Wh)",
        "exported_wh": "Exportée vers le réseau (Wh)",
        "imported_wh": "Importée depuis le réseau (Wh)",
        "time_stamp": "Date/Heure",
    }


class TestLoadAndPrepareData:
    def test_loads_and_renames_columns(self, sample_csv, columns_map):
        df = load_and_prepare_data(sample_csv, columns_map)
        assert "produced_wh" in df.columns
        assert "consumed_wh" in df.columns
        assert "imported_wh" in df.columns
        assert "exported_wh" in df.columns

    def test_datetime_index(self, sample_csv, columns_map):
        df = load_and_prepare_data(sample_csv, columns_map)
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.name == "time_stamp"

    def test_sorted_chronologically(self, sample_csv, columns_map):
        df = load_and_prepare_data(sample_csv, columns_map)
        assert df.index.is_monotonic_increasing

    def test_correct_row_count(self, sample_csv, columns_map):
        df = load_and_prepare_data(sample_csv, columns_map)
        assert len(df) == 7

    def test_missing_columns_raises(self, tmp_path, columns_map):
        csv_content = "Date/Heure,Énergie produite (Wh)\n09/01/2024 00:00,100\n"
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(csv_content)
        with pytest.raises(ValueError, match="Missing required columns"):
            load_and_prepare_data(str(csv_file), columns_map)

    def test_negative_values_raises(self, tmp_path, columns_map):
        csv_content = (
            "Date/Heure,Énergie produite (Wh),Énergie consommée (Wh),"
            "Importée depuis le réseau (Wh),Exportée vers le réseau (Wh)\n"
            "09/01/2024 00:00,-100,500,500,0\n"
        )
        csv_file = tmp_path / "negative.csv"
        csv_file.write_text(csv_content)
        with pytest.raises(ValueError, match="negative values"):
            load_and_prepare_data(str(csv_file), columns_map)


class TestFilterData:
    @pytest.fixture
    def sample_df(self):
        dates = pd.date_range("2024-09-01", periods=96, freq="15min")
        df = pd.DataFrame({
            "produced_wh": np.random.rand(96) * 1000,
            "consumed_wh": np.random.rand(96) * 500,
        }, index=dates)
        df.index.name = "time_stamp"
        return df

    def test_no_filter(self, sample_df):
        result = filter_data(sample_df)
        assert len(result) == len(sample_df)
        assert "is_hp" in result.columns
        assert "is_hc" in result.columns

    def test_start_date_filter(self, sample_df):
        result = filter_data(sample_df, start_date="2024-09-01 12:00:00")
        assert all(result.index >= pd.Timestamp("2024-09-01 12:00:00"))

    def test_end_date_filter(self, sample_df):
        result = filter_data(sample_df, end_date="2024-09-01 12:00:00")
        assert all(result.index <= pd.Timestamp("2024-09-01 12:00:00"))

    def test_hp_hc_default_hours(self, sample_df):
        result = filter_data(sample_df)
        for idx, row in result.iterrows():
            hour = idx.hour
            if 7 <= hour < 23:
                assert row["is_hp"] == True
                assert row["is_hc"] == False
            else:
                assert row["is_hp"] == False
                assert row["is_hc"] == True

    def test_custom_hp_hours(self, sample_df):
        result = filter_data(sample_df, hp_start_hour=6, hp_end_hour=22)
        for idx, row in result.iterrows():
            hour = idx.hour
            if 6 <= hour < 22:
                assert row["is_hp"] == True
            else:
                assert row["is_hp"] == False
