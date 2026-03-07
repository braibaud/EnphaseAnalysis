import pandas as pd
import numpy as np
from itertools import product

from .battery_simulation import rescale_solar_production, simulate_battery
from .data_loader import filter_data


def format_wh(first, second=None):
    if first is None:
        return None
    if second is None:
        return round(first / 1000, 2)
    return round((first + second) / 1000, 2)


def calculate_cost(row, category, wh_column, results,
                   wh_price_high_eur, wh_price_low_eur, wh_price_sale_eur):
    wh = abs(row[wh_column])

    if wh == 0:
        return

    if category == 'Solar > Grid':
        cost = wh * wh_price_sale_eur * -1
        if row['is_hp']:
            results[category]['hp_cost'] += cost
            results[category]['hp_wh'] += wh
        else:
            results[category]['hc_cost'] += cost
            results[category]['hc_wh'] += wh

    elif category == 'Solar > Battery':
        cost = wh * wh_price_sale_eur
        if row['is_hp']:
            results[category]['hp_cost'] += cost
            results[category]['hp_wh'] += wh
        else:
            results[category]['hc_cost'] += cost
            results[category]['hc_wh'] += wh

    elif category in ['Grid > House', 'Grid > Battery']:
        if row['is_hp']:
            rate = wh_price_high_eur
            period = 'hp'
        else:
            rate = wh_price_low_eur
            period = 'hc'
        cost = wh * rate
        results[category][f'{period}_cost'] += cost
        results[category][f'{period}_wh'] += wh

    elif category == 'Battery > House':
        if row['is_hp']:
            rate = wh_price_high_eur
            period = 'hp'
        else:
            rate = wh_price_low_eur
            period = 'hc'
        cost = wh * rate * -1
        results[category][f'{period}_cost'] += cost
        results[category][f'{period}_wh'] += wh

    elif category == 'Solar > House':
        if row['is_hp']:
            rate = wh_price_high_eur
            period = 'hp'
        else:
            rate = wh_price_low_eur
            period = 'hc'
        cost = wh * rate * -1
        results[category][f'{period}_cost'] += cost
        results[category][f'{period}_wh'] += wh


def optimize_capacity(
    df,
    wh_price_sale_eur,
    wh_price_high_eur,
    wh_price_low_eur,
    subscription_monthly_fee_eur,
    original_solar_capacity,
    solar_capacities_w,
    battery_capacities_wh,
    battery_discharge_lower_limit_pc,
    battery_charge_upper_limit_pc,
    battery_efficiency_pc,
    enable_hc_charging,
    hp_start_hour=7,
    hp_end_hour=23,
    debug=False):

    results = []

    for solar_capacity, battery_capacity in product(solar_capacities_w, battery_capacities_wh):

        scaled_df = rescale_solar_production(
            df, original_solar_capacity, solar_capacity)

        simulated_df = simulate_battery(
            scaled_df,
            battery_capacity,
            battery_discharge_lower_limit_pc,
            battery_charge_upper_limit_pc,
            battery_efficiency_pc,
            max_battery_charge_rate_w=None,
            max_battery_discharge_rate_w=None,
            enable_hc_charging=enable_hc_charging,
            hp_start_hour=hp_start_hour,
            hp_end_hour=hp_end_hour,
        )

        result = {
            'solar_capacity': solar_capacity,
            'battery_capacity': battery_capacity,
            'data': simulated_df,
        }

        results.append(result)

        if debug:
            print(f'--------------------------------------------------------------------')
            print(f'solar       -> {int(solar_capacity/1000.0)}kWc')
            print(f'battery     -> {int(battery_capacity/1000.0)}kWh')
            print(f'HC charging -> {enable_hc_charging}')
            print(f'--------------------------------------------------------------------')
            print()

    return results


def process_battery_data(
    df,
    start_date,
    end_date,
    wh_price_high_eur,
    wh_price_low_eur,
    wh_price_sale_eur,
    subscription_monthly_fee_eur,
    hp_start_hour=7,
    hp_end_hour=23):
    """
    Process battery data and calculate various metrics and costs.

    Parameters:
    - df: DataFrame containing the battery data.
    - start_date: Start date for the data range.
    - end_date: End date for the data range.
    - wh_price_high_eur: Price per Wh during high period.
    - wh_price_low_eur: Price per Wh during low period.
    - wh_price_sale_eur: Price per Wh for selling energy back to the grid.
    - subscription_monthly_fee_eur: Monthly subscription fee.
    - hp_start_hour: Hour when HP starts (default: 7).
    - hp_end_hour: Hour when HP ends (default: 23).

    Returns:
    - results_df: DataFrame containing the calculated metrics and totals.
    """
    filtered_df = filter_data(df, start_date, end_date,
                              hp_start_hour=hp_start_hour, hp_end_hour=hp_end_hour)

    num_intervals = len(filtered_df)
    if num_intervals > 0:
        fixed_cost_per_interval = (12 * subscription_monthly_fee_eur) / (365 * 24 * 4)
    else:
        fixed_cost_per_interval = 0

    results = {
        'Grid > House': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0},
        'Battery > House': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0},
        'Solar > Grid': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0},
        'Grid > Battery': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0},
        'Solar > House': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0},
        'Solar > Battery': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0},
        'Solar Saving': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0},
        'Battery Saving': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0},
        'Subscription Fee': {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0}
    }

    for _, row in filtered_df.iterrows():
        calculate_cost(row, 'Grid > House', 'Grid > House', results, wh_price_high_eur, wh_price_low_eur, wh_price_sale_eur)
        calculate_cost(row, 'Battery > House', 'Battery > House', results, wh_price_high_eur, wh_price_low_eur, wh_price_sale_eur)
        calculate_cost(row, 'Solar > Grid', 'Solar > Grid', results, wh_price_high_eur, wh_price_low_eur, wh_price_sale_eur)
        calculate_cost(row, 'Grid > Battery', 'Grid > Battery', results, wh_price_high_eur, wh_price_low_eur, wh_price_sale_eur)
        calculate_cost(row, 'Solar > House', 'Solar > House', results, wh_price_high_eur, wh_price_low_eur, wh_price_sale_eur)

        wh = row['Solar > Battery']
        if wh > 0:
            period = 'hp' if row['is_hp'] else 'hc'
            results['Solar > Battery'][f'{period}_wh'] += wh
            cost = wh * wh_price_sale_eur
            results['Solar > Battery'][f'{period}_cost'] += cost

    # Fixed costs
    if num_intervals > 0:
        total_fixed_cost = fixed_cost_per_interval * num_intervals
        num_hp_intervals = filtered_df['is_hp'].sum()
        num_hc_intervals = num_intervals - num_hp_intervals
        if num_hp_intervals > 0:
            results['Subscription Fee']['hp_cost'] = (total_fixed_cost * num_hp_intervals) / num_intervals
        if num_hc_intervals > 0:
            results['Subscription Fee']['hc_cost'] = (total_fixed_cost * num_hc_intervals) / num_intervals

    # Solar Savings
    results['Solar Saving'] = {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0}
    results['Battery Saving'] = {'hp_cost': 0, 'hp_wh': 0, 'hc_cost': 0, 'hc_wh': 0}

    for period in ['hp', 'hc']:
        solar_to_grid = results['Solar > Grid'][f'{period}_cost']
        solar_to_house = results['Solar > House'][f'{period}_cost']
        solar_to_battery = results['Solar > Battery'][f'{period}_cost']
        results['Solar Saving'][f'{period}_cost'] = solar_to_grid + solar_to_house + solar_to_battery
        results['Solar Saving'][f'{period}_wh'] = None

    for period in ['hp', 'hc']:
        battery_to_house = results['Battery > House'][f'{period}_cost']
        solar_to_battery = results['Solar > Battery'][f'{period}_cost']
        grid_to_battery = results['Grid > Battery'][f'{period}_cost']
        results['Battery Saving'][f'{period}_cost'] = battery_to_house - solar_to_battery + grid_to_battery
        results['Battery Saving'][f'{period}_wh'] = None

    # Totals
    total_consumed_naked_hp_wh = (results['Grid > House']['hp_wh'] +
                                  results['Solar > House']['hp_wh'] +
                                  results['Battery > House']['hp_wh'])
    total_consumed_naked_hc_wh = (results['Grid > House']['hc_wh'] +
                                  results['Solar > House']['hc_wh'] +
                                  results['Battery > House']['hc_wh'])
    total_consumed_naked_hp_cost = total_consumed_naked_hp_wh * wh_price_high_eur
    total_consumed_naked_hc_cost = total_consumed_naked_hc_wh * wh_price_low_eur

    total_consumed_hp_wh = total_consumed_naked_hp_wh
    total_consumed_hc_wh = total_consumed_naked_hc_wh
    total_consumed_hp_cost = (results['Grid > House']['hp_cost'] +
                              results['Solar > House']['hp_cost'] +
                              results['Battery > House']['hp_cost'])
    total_consumed_hc_cost = (results['Grid > House']['hc_cost'] +
                              results['Solar > House']['hc_cost'] +
                              results['Battery > House']['hc_cost'])

    total_stored_hp_wh = results['Grid > Battery']['hp_wh'] + results['Solar > Battery']['hp_wh']
    total_stored_hc_wh = results['Grid > Battery']['hc_wh'] + results['Solar > Battery']['hc_wh']
    total_stored_hp_cost = results['Grid > Battery']['hp_cost'] + results['Solar > Battery']['hp_cost']
    total_stored_hc_cost = results['Grid > Battery']['hc_cost'] + results['Solar > Battery']['hc_cost']

    total_produced_hp_wh = (results['Solar > Battery']['hp_wh'] +
                            results['Solar > Grid']['hp_wh'] +
                            results['Solar > House']['hp_wh'])
    total_produced_hc_wh = (results['Solar > Battery']['hc_wh'] +
                            results['Solar > Grid']['hc_wh'] +
                            results['Solar > House']['hc_wh'])
    total_produced_hp_cost = (results['Solar > Battery']['hp_cost'] +
                              results['Solar > Grid']['hp_cost'] +
                              results['Solar > House']['hp_cost'])
    total_produced_hc_cost = (results['Solar > Battery']['hc_cost'] +
                              results['Solar > Grid']['hc_cost'] +
                              results['Solar > House']['hc_cost'])

    total_imported_hp_wh = results['Grid > House']['hp_wh'] + results['Grid > Battery']['hp_wh']
    total_imported_hc_wh = results['Grid > House']['hc_wh'] + results['Grid > Battery']['hc_wh']
    total_imported_hp_cost = results['Grid > House']['hp_cost'] + results['Grid > Battery']['hp_cost']
    total_imported_hc_cost = results['Grid > House']['hc_cost'] + results['Grid > Battery']['hc_cost']

    all_savings_hp_cost = results['Solar Saving']['hp_cost'] + results['Battery Saving']['hp_cost']
    all_savings_hc_cost = results['Solar Saving']['hc_cost'] + results['Battery Saving']['hc_cost']

    total_exported_hp_wh = results['Solar > Grid']['hp_wh']
    total_exported_hc_wh = results['Solar > Grid']['hc_wh']
    total_exported_hp_cost = results['Solar > Grid']['hp_cost']
    total_exported_hc_cost = results['Solar > Grid']['hc_cost']

    total_cost_hp_cost = (total_imported_hp_cost +
                          results['Subscription Fee']['hp_cost'] +
                          total_exported_hp_cost)
    total_cost_hc_cost = (total_imported_hc_cost +
                          results['Subscription Fee']['hc_cost'] +
                          total_exported_hc_cost)

    total_cost_naked_hp_cost = total_consumed_naked_hp_cost + results['Subscription Fee']['hp_cost']
    total_cost_naked_hc_cost = total_consumed_naked_hc_cost + results['Subscription Fee']['hc_cost']

    results.update({
        'Total Consumed (Naked)': {
            'hp_cost': total_consumed_naked_hp_cost, 'hp_wh': total_consumed_naked_hp_wh,
            'hc_cost': total_consumed_naked_hc_cost, 'hc_wh': total_consumed_naked_hc_wh
        },
        'Total Consumed (Any > House)': {
            'hp_cost': total_consumed_hp_cost, 'hp_wh': total_consumed_hp_wh,
            'hc_cost': total_consumed_hc_cost, 'hc_wh': total_consumed_hc_wh
        },
        'Total Stored (Any > Battery)': {
            'hp_cost': total_stored_hp_cost, 'hp_wh': total_stored_hp_wh,
            'hc_cost': total_stored_hc_cost, 'hc_wh': total_stored_hc_wh
        },
        'Total Produced (Solar > Any)': {
            'hp_cost': total_produced_hp_cost, 'hp_wh': total_produced_hp_wh,
            'hc_cost': total_produced_hc_cost, 'hc_wh': total_produced_hc_wh
        },
        'Total Imported (Grid > Any)': {
            'hp_cost': total_imported_hp_cost, 'hp_wh': total_imported_hp_wh,
            'hc_cost': total_imported_hc_cost, 'hc_wh': total_imported_hc_wh
        },
        'Total Exported (Any > Grid)': {
            'hp_cost': total_exported_hp_cost, 'hp_wh': total_exported_hp_wh,
            'hc_cost': total_exported_hc_cost, 'hc_wh': total_exported_hc_wh
        },
        'Total Cost': {
            'hp_cost': total_cost_hp_cost, 'hp_wh': None,
            'hc_cost': total_cost_hc_cost, 'hc_wh': None
        },
        'Total Cost (Naked)': {
            'hp_cost': total_cost_naked_hp_cost, 'hp_wh': None,
            'hc_cost': total_cost_naked_hc_cost, 'hc_wh': None
        },
        'Total Saving': {
            'hp_cost': all_savings_hp_cost, 'hp_wh': None,
            'hc_cost': all_savings_hc_cost, 'hc_wh': None
        }
    })

    # Build output DataFrame
    data = []

    metric_order = [
        'Grid > House', 'Grid > Battery', 'Solar > House',
        'Battery > House', 'Solar > Battery', 'Solar > Grid',
        'Subscription Fee'
    ]
    for name in metric_order:
        if name in results:
            item = results[name]
            data.append({
                'Category': 'Metric', 'Type': name,
                'HP Cost': round(item['hp_cost'], 2),
                'HP kWh': format_wh(item['hp_wh']),
                'HC Cost': round(item['hc_cost'], 2),
                'HC kWh': format_wh(item['hc_wh']),
                'Total Cost': round(item['hp_cost'] + item['hc_cost'], 2),
                'Total kWh': format_wh(item['hp_wh'], item['hc_wh'])
            })

    totals_order = [
        'Total Imported (Grid > Any)', 'Total Exported (Any > Grid)',
        'Total Stored (Any > Battery)', 'Total Produced (Solar > Any)',
        'Total Consumed (Any > House)', 'Total Consumed (Naked)',
        'Total Cost', 'Total Cost (Naked)'
    ]
    for name in totals_order:
        if name in results:
            item = results[name]
            data.append({
                'Category': 'Total', 'Type': name,
                'HP Cost': round(item['hp_cost'], 2),
                'HP kWh': format_wh(item['hp_wh']),
                'HC Cost': round(item['hc_cost'], 2),
                'HC kWh': format_wh(item['hc_wh']),
                'Total Cost': round(item['hp_cost'] + item['hc_cost'], 2),
                'Total kWh': format_wh(item['hp_wh'], item['hc_wh'])
            })

    savings_order = ['Solar Saving', 'Battery Saving', 'Total Saving']
    for name in savings_order:
        if name in results:
            item = results[name]
            data.append({
                'Category': 'Saving', 'Type': name,
                'HP Cost': round(item['hp_cost'], 2),
                'HP kWh': format_wh(item['hp_wh']),
                'HC Cost': round(item['hc_cost'], 2),
                'HC kWh': format_wh(item['hc_wh']),
                'Total Cost': round(item['hp_cost'] + item['hc_cost'], 2),
                'Total kWh': format_wh(item['hp_wh'], item['hc_wh'])
            })

    results_df = pd.DataFrame(data)
    results_df = results_df.set_index(['Category', 'Type'])
    results_df = results_df.sort_index(level=0, sort_remaining=False)

    return results_df
