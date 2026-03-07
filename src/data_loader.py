import pandas as pd
from datetime import datetime


REQUIRED_COLUMNS = ["produced_wh", "consumed_wh", "exported_wh", "imported_wh"]


def load_and_prepare_data(import_file, columns_map):
    """
    Load raw energy data from a CSV file, clean it, and prepare it for simulation.

    Parameters:
    - import_file: Path to the CSV file.
    - columns_map: Dict mapping internal names to CSV column names.

    Returns:
    - DataFrame with datetime index and standardized column names.

    Raises:
    - ValueError: If required columns are missing after renaming.
    - ValueError: If any energy column contains negative values.
    """
    df = pd.read_csv(import_file)

    # Reverse the columns_map to map CSV names to internal names
    reverse_columns_map = {v: k for k, v in columns_map.items()}
    df = df.rename(columns=reverse_columns_map)

    # Validate required columns
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns after renaming: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    if "time_stamp" not in df.columns:
        raise ValueError(
            "Missing 'time_stamp' column. Ensure columns_map maps 'time_stamp' "
            "or the CSV contains a 'time_stamp' column."
        )

    # Validate non-negative energy values
    for col in REQUIRED_COLUMNS:
        if (df[col] < 0).any():
            neg_count = (df[col] < 0).sum()
            raise ValueError(
                f"Column '{col}' contains {neg_count} negative values. "
                f"Energy values must be non-negative."
            )

    # Set datetime index
    df['time_stamp'] = pd.to_datetime(df['time_stamp'], format='%m/%d/%Y %H:%M')
    df.set_index('time_stamp', inplace=True)
    df.sort_index(inplace=True)

    return df


def filter_data(df, start_date=None, end_date=None, hp_start_hour=7, hp_end_hour=23):
    """
    Filter input data by date range and add HP/HC period flags.

    Parameters:
    - df: DataFrame with a datetime index.
    - start_date: Optional start date string (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
    - end_date: Optional end date string (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
    - hp_start_hour: Hour when high-price period starts (default: 7).
    - hp_end_hour: Hour when high-price period ends (default: 23).

    Returns:
    - Filtered DataFrame with 'is_hp' and 'is_hc' boolean columns.
    """
    mask = pd.Series(True, index=df.index)

    if start_date is not None:
        try:
            start_date = pd.Timestamp(datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            start_date = pd.Timestamp(datetime.strptime(start_date, "%Y-%m-%d"))
        mask &= (df.index >= start_date)

    if end_date is not None:
        try:
            end_date = pd.Timestamp(datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            end_date = pd.Timestamp(datetime.strptime(end_date, "%Y-%m-%d"))
        mask &= (df.index <= end_date)

    filtered_df = df.loc[mask].copy()

    hours = filtered_df.index.hour
    filtered_df['is_hp'] = (hours >= hp_start_hour) & (hours < hp_end_hour)
    filtered_df['is_hc'] = ~filtered_df['is_hp']

    return filtered_df
