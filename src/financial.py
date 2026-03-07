import pandas as pd

from .battery_simulation import rescale_solar_production, simulate_battery
from .cost_analysis import process_battery_data


def expand_array(input_list, key, length):
    output = [None] * length
    for entry in input_list:
        key_value = entry[key]
        if 0 <= key_value < length:
            output[key_value] = entry
    return output


def add_row(df, index, column_value_pairs):
    if df.index.isin([index]).any():
        for col, val in column_value_pairs:
            df.loc[index, col] = val
    else:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    index=pd.MultiIndex.from_tuples([index], names=df.index.names),
                    data=column_value_pairs)
            ],
            names=df.index.names)
    return df


def add_to_first_n(ar, val, nb):
    if len(ar) < nb:
        ar.extend([0.0] * (nb - len(ar)))
    for i in range(min(nb, len(ar))):
        ar[i] += val
    return ar


def financial_projection(raw_df, config):
    solar_degradation_pc_per_year = config["solar_degradation_pc_per_year"]
    battery_degradation_pc_per_year = config["battery_degradation_pc_per_year"]
    year_zero = config["year_zero"]
    price_escalation_pc = config["financials"]["price_escalation_pc"]

    investments = expand_array(
        config["financials"]["investments"],
        key="year",
        length=config["nb_years_projection"])

    energy_prices = expand_array(
        config["financials"]["energy_prices"],
        key="year",
        length=config["nb_years_projection"])

    solar_capacity = 0.0
    battery_capacity = 0.0

    solar_capex_eur_per_kwc = None
    battery_capex_eur_per_kwh = None

    solar_capacity_effective = 0.0
    battery_capacity_effective = 0.0

    wh_price_high_eur = None
    wh_price_low_eur = None
    wh_price_sale_eur = None
    subscription_monthly_fee_eur = None

    solar_opex = config["financials"]["fixed_opex_per_year"]["solar_eur"]
    battery_opex = config["financials"]["fixed_opex_per_year"]["battery_eur"]

    solar_capex_projection = []
    battery_capex_projection = []

    nb_years_depreciation = config["nb_years_depreciation"]
    battery_charge_upper_limit_pc = config["battery_charge_upper_limit_pc"]

    hp_start_hour = config.get("hp_start_hour", 7)
    hp_end_hour = config.get("hp_end_hour", 23)

    df_previous = raw_df.copy()
    df_global = None

    for year_index in range(config["nb_years_projection"]):

        current_year = year_zero + year_index

        previous_solar_capacity_effective = solar_capacity_effective if year_index > 0 else None

        solar_capacity_effective = solar_capacity_effective * (1 - solar_degradation_pc_per_year / 100)
        battery_capacity_effective = battery_capacity_effective * (1 - battery_degradation_pc_per_year / 100)

        solar_capex = 0.0
        battery_capex = 0.0

        if investments[year_index] is not None:
            added_solar_capacity_kwc = investments[year_index]["added_solar_capacity_kwc"]
            added_battery_capacity_kwh = investments[year_index]["added_battery_capacity_kwh"]
            solar_capex_eur_per_kwc = investments[year_index]["solar_capex_eur_per_kwc"]
            battery_capex_eur_per_kwh = investments[year_index]["battery_capex_eur_per_kwh"]

            solar_capacity += added_solar_capacity_kwc * 1000
            battery_capacity += added_battery_capacity_kwh * 1000

            solar_capacity_effective += added_solar_capacity_kwc * 1000
            battery_capacity_effective += added_battery_capacity_kwh * 1000

            solar_capex = added_solar_capacity_kwc * solar_capex_eur_per_kwc
            battery_capex = added_battery_capacity_kwh * battery_capex_eur_per_kwh

        # Opex
        opex = 0.0
        opex += solar_opex if solar_capacity > 0 else 0.0
        opex += battery_opex if battery_capacity > 0 else 0.0

        # Capex depreciation
        capex = solar_capex + battery_capex

        if solar_capex > 0:
            solar_capex_yearly = solar_capex / nb_years_depreciation
            add_to_first_n(solar_capex_projection, solar_capex_yearly, nb_years_depreciation)

        solar_capex_yearly_depreciation = solar_capex_projection.pop(0) if len(solar_capex_projection) > 0 else 0.0

        if battery_capex > 0:
            battery_capex_yearly = battery_capex / nb_years_depreciation
            add_to_first_n(battery_capex_projection, battery_capex_yearly, nb_years_depreciation)

        battery_capex_yearly_depreciation = battery_capex_projection.pop(0) if len(battery_capex_projection) > 0 else 0.0

        # Energy prices
        if energy_prices[year_index] is not None:
            wh_price_high_eur = energy_prices[year_index]["wh_price_high_eur"]
            wh_price_low_eur = energy_prices[year_index]["wh_price_low_eur"]
            wh_price_sale_eur = energy_prices[year_index]["wh_price_sale_eur"]
            subscription_monthly_fee_eur = energy_prices[year_index]["subscription_monthly_fee_eur"]
        else:
            wh_price_high_eur *= (1 + price_escalation_pc["high"] / 100)
            wh_price_low_eur *= (1 + price_escalation_pc["low"] / 100)
            wh_price_sale_eur *= (1 + price_escalation_pc["sale"] / 100)
            subscription_monthly_fee_eur *= (1 + price_escalation_pc["subscription_fee"] / 100)

        # Rescale solar production
        if previous_solar_capacity_effective is not None:
            if previous_solar_capacity_effective != solar_capacity_effective:
                df_previous = rescale_solar_production(
                    df_previous,
                    previous_solar_capacity_effective,
                    solar_capacity_effective)

        # Simulate battery
        simulated_df = simulate_battery(
            df_previous,
            battery_capacity_effective,
            battery_discharge_lower_limit_pc=config["battery_discharge_lower_limit_pc"],
            battery_charge_upper_limit_pc=battery_charge_upper_limit_pc,
            battery_efficiency_pc=config["battery_efficiency_pc"],
            max_battery_charge_rate_w=config["max_battery_charge_rate_w"],
            max_battery_discharge_rate_w=config["max_battery_discharge_rate_w"],
            enable_hc_charging=config["enable_hc_charging"],
            hp_start_hour=hp_start_hour,
            hp_end_hour=hp_end_hour)

        # Process battery data
        processed_df = process_battery_data(
            simulated_df,
            start_date=None,
            end_date=None,
            wh_price_high_eur=wh_price_high_eur,
            wh_price_low_eur=wh_price_low_eur,
            wh_price_sale_eur=wh_price_sale_eur,
            subscription_monthly_fee_eur=subscription_monthly_fee_eur,
            hp_start_hour=hp_start_hour,
            hp_end_hour=hp_end_hour)

        year_processed_df = processed_df[['Total Cost']]

        year_processed_df = add_row(
            year_processed_df,
            ('Variables', 'Solar Capacity'),
            {'Total Cost': solar_capacity})
        year_processed_df = add_row(
            year_processed_df,
            ('Variables', 'Solar Capacity (effective)'),
            {'Total Cost': solar_capacity_effective})
        year_processed_df = add_row(
            year_processed_df,
            ('Variables', 'Battery Capacity'),
            {'Total Cost': battery_capacity})
        year_processed_df = add_row(
            year_processed_df,
            ('Variables', 'Battery Capacity (effective)'),
            {'Total Cost': battery_capacity_effective})
        year_processed_df = add_row(
            year_processed_df,
            ('Total', 'Solar Capex (one-time)'),
            {'Total Cost': solar_capex})
        year_processed_df = add_row(
            year_processed_df,
            ('Total', 'Solar Capex (depreciation)'),
            {'Total Cost': solar_capex_yearly_depreciation})
        year_processed_df = add_row(
            year_processed_df,
            ('Total', 'Solar Opex'),
            {'Total Cost': solar_opex})
        year_processed_df = add_row(
            year_processed_df,
            ('Total', 'Battery Capex (one-time)'),
            {'Total Cost': battery_capex})
        year_processed_df = add_row(
            year_processed_df,
            ('Total', 'Battery Capex (depreciation)'),
            {'Total Cost': battery_capex_yearly_depreciation})
        year_processed_df = add_row(
            year_processed_df,
            ('Total', 'Battery Opex'),
            {'Total Cost': battery_opex})
        year_processed_df = add_row(
            year_processed_df,
            ('Pricing', 'HC Price/kWh'),
            {'Total Cost': wh_price_low_eur * 1000})
        year_processed_df = add_row(
            year_processed_df,
            ('Pricing', 'HP Price/kWh'),
            {'Total Cost': wh_price_high_eur * 1000})
        year_processed_df = add_row(
            year_processed_df,
            ('Pricing', 'Sales Price/kWh'),
            {'Total Cost': wh_price_sale_eur * 1000})

        year_processed_df = year_processed_df.rename(
            columns={'Total Cost': f'{current_year}'})

        if df_global is None:
            df_global = year_processed_df
        else:
            df_global = year_processed_df.merge(
                df_global,
                how='inner',
                on=df_global.index.names)

    df_global = df_global.reindex(sorted(df_global.columns), axis=1)
    df_global = df_global.sort_index()

    return df_global
