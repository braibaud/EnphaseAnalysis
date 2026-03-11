import numpy as np
import pandas as pd


def rescale_solar_production(df_original, original_capacity, new_capacity):
    """
    Rescale solar production data from original PV capacity to new PV capacity.

    Assumptions:
    1. Solar production scales linearly with panel capacity.
    2. Consumption remains the same.
    3. Export is increased production minus any additional self-consumption.
    4. Import is reduced by any additional self-consumption.

    Parameters:
    - df_original: Original DataFrame with energy data.
    - original_capacity: Original solar capacity in W.
    - new_capacity: New solar capacity in W.

    Returns:
    - New DataFrame with rescaled values.
    """
    if original_capacity == new_capacity:
        return df_original.copy()

    df = df_original.copy()
    scaling_factor = new_capacity / original_capacity

    df['produced_wh'] = df['produced_wh'] * scaling_factor

    additional_production = df['produced_wh'] - df_original['produced_wh']

    additional_self_consumption = np.minimum(
        additional_production,
        df_original['imported_wh']
    )

    df['imported_wh'] = np.maximum(0, df_original['imported_wh'] - additional_self_consumption)

    remaining_additional = additional_production - additional_self_consumption
    df['exported_wh'] = df_original['exported_wh'] + remaining_additional

    return df


def simulate_battery(
    df,
    max_battery_capacity_wh,
    battery_discharge_lower_limit_pc,
    battery_charge_upper_limit_pc,
    battery_efficiency_pc,
    max_battery_charge_rate_w,
    max_battery_discharge_rate_w,
    enable_hc_charging,
    hp_start_hour=7,
    hp_end_hour=23):
    """
    Simulate battery behavior over time using NumPy arrays for performance.

    Parameters:
    - df: DataFrame with columns produced_wh, consumed_wh, and time_stamp as index.
    - max_battery_capacity_wh: Maximum capacity of the battery in Wh.
    - battery_discharge_lower_limit_pc: Minimum SOC percentage (0-25).
    - battery_charge_upper_limit_pc: Maximum SOC percentage (75-100).
    - battery_efficiency_pc: Battery round-trip efficiency percentage (0-100).
    - max_battery_charge_rate_w: Maximum charge rate in watts (None = auto).
    - max_battery_discharge_rate_w: Maximum discharge rate in watts (None = auto).
    - enable_hc_charging: Boolean flag to enable battery charging from grid during HC.
    - hp_start_hour: Hour when high-price period starts (default: 7).
    - hp_end_hour: Hour when high-price period ends (default: 23).

    Returns:
    - DataFrame with columns tracking energy flows between components.
    """
    # Validate parameters
    if not (0 <= battery_discharge_lower_limit_pc <= 25):
        raise ValueError("battery_discharge_lower_limit_pc must be between 0 and 25")
    if not (75 <= battery_charge_upper_limit_pc <= 100):
        raise ValueError("battery_charge_upper_limit_pc must be between 75 and 100")
    if not (0 <= battery_efficiency_pc <= 100):
        raise ValueError("battery_efficiency_pc must be between 0 and 100")

    # Calculate battery limits in Wh
    battery_lower_wh = max_battery_capacity_wh * battery_discharge_lower_limit_pc / 100
    battery_upper_wh = max_battery_capacity_wh * battery_charge_upper_limit_pc / 100

    # Auto-calculate charge/discharge rates if not specified
    if max_battery_charge_rate_w is None:
        max_battery_charge_rate_w = 2 * max_battery_capacity_wh / 3
    if max_battery_discharge_rate_w is None:
        max_battery_discharge_rate_w = 2 * max_battery_capacity_wh / 3

    max_charge_rate_wh = max_battery_charge_rate_w / 4  # Wh per 15 minutes
    max_discharge_rate_wh = max_battery_discharge_rate_w / 4

    efficiency = battery_efficiency_pc / 100

    # Extract arrays for fast iteration
    n = len(df)
    produced = df['produced_wh'].values
    consumed = df['consumed_wh'].values
    hours = df.index.hour

    # Pre-compute HP flag array
    is_hp = (hours >= hp_start_hour) & (hours < hp_end_hour)

    # Output arrays
    grid_to_house = np.zeros(n)
    grid_to_battery = np.zeros(n)
    solar_to_house = np.zeros(n)
    battery_to_house = np.zeros(n)
    solar_to_battery = np.zeros(n)
    solar_to_grid = np.zeros(n)
    battery_soc_arr = np.zeros(n)

    battery_soc = 0.0

    for i in range(n):
        p = produced[i]
        c = consumed[i]

        s2h = min(p, c)
        net = p - c

        g2h = 0.0
        g2b = 0.0
        b2h = 0.0
        s2b = 0.0
        s2g = 0.0

        if net < 0:
            # Deficit: try battery discharge first
            needed = -net
            available = max(0.0, battery_soc - battery_lower_wh)
            discharge = min(needed, max_discharge_rate_wh, available)

            if discharge > 0:
                soc_decrease = discharge / efficiency
                b2h = discharge
                battery_soc -= soc_decrease
                remaining = needed - discharge
            else:
                remaining = needed

            if remaining > 0:
                g2h = remaining

        elif net > 0:
            # Surplus: charge battery, then export
            max_charge = min(net, max_charge_rate_wh)
            space = battery_upper_wh - battery_soc

            if space > 0:
                charge = min(max_charge, space)
            else:
                charge = 0.0

            if charge > 0:
                battery_soc += charge * efficiency
                s2b = charge
                excess = net - charge
                if excess > 0:
                    s2g = excess
            else:
                s2g = net

        # Clamp SOC
        battery_soc = max(battery_lower_wh, min(battery_soc, battery_upper_wh))

        # HC grid charging
        if not is_hp[i] and enable_hc_charging:
            space = battery_upper_wh - battery_soc
            if space > 0:
                charge = min(space, max_charge_rate_wh)
                if charge > 0:
                    battery_soc += charge * efficiency
                    g2b = charge

        # Final clamp
        battery_soc = max(battery_lower_wh, min(battery_soc, battery_upper_wh))

        grid_to_house[i] = g2h
        grid_to_battery[i] = g2b
        solar_to_house[i] = s2h
        battery_to_house[i] = b2h
        solar_to_battery[i] = s2b
        solar_to_grid[i] = s2g
        battery_soc_arr[i] = battery_soc

    # Build result DataFrame
    result = df.copy()
    result['Grid > House'] = grid_to_house
    result['Grid > Battery'] = grid_to_battery
    result['Solar > House'] = solar_to_house
    result['Battery > House'] = battery_to_house
    result['Solar > Battery'] = solar_to_battery
    result['Solar > Grid'] = solar_to_grid
    result['Battery SOC'] = battery_soc_arr

    return result
