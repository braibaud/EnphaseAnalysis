# Solar Energy Analysis and Optimization Notebook

## Functional Documentation

### Description
This notebook is designed to help homeowners and energy enthusiasts analyze and optimize their solar energy systems. It allows you to simulate different configurations of solar panels and batteries to find the most cost-effective setup based on your energy consumption patterns and local energy prices.

### Use Cases
- **Home Energy Optimization**: Determine the optimal size for your solar panel and battery system to minimize energy costs and maximize self-consumption.
- **Financial Planning**: Evaluate the financial benefits of adding or expanding a solar panel and battery system.
- **Energy Independence**: Assess how different configurations can reduce your reliance on the grid and lower your energy bills.
- **Environmental Impact**: Understand how increasing your solar capacity can reduce your carbon footprint.

### What It Does
1. **Data Analysis**: Load and analyze your historical energy consumption and production data.
2. **System Simulation**: Simulate the performance of different solar panel and battery configurations.
3. **Cost Calculation**: Calculate the costs and savings associated with each configuration, taking into account variable energy prices.
4. **Optimization**: Identify the best configuration for your specific needs and budget.

### Benefits
- **Cost Savings**: Find the configuration that minimizes your energy costs.
- **Informed Decisions**: Make data-driven decisions about investing in solar panels and batteries.
- **Customization**: Tailor the analysis to your specific energy consumption patterns and local energy prices.
- **Visualization**: Generate visual reports to help you understand the impact of different configurations.

## Expected Input Data Format

The notebook expects input data in a CSV file with the following columns:
- `time_stamp`: The timestamp of the energy data.
- `produced_wh`: The amount of energy produced by the solar panels in watt-hours.
- `consumed_wh`: The amount of energy consumed by the house in watt-hours.
- `imported_wh`: The amount of energy imported from the grid in watt-hours.
- `exported_wh`: The amount of energy exported to the grid in watt-hours.

The data should be formatted as follows:
```
time_stamp,produced_wh,consumed_wh,imported_wh,exported_wh
2024-09-01 00:00:00,1000,500,500,0
2024-09-01 00:15:00,1200,600,600,0
...
```

## Technical Documentation

### Functions

#### `load_and_prepare_data`
**Purpose**:
Loads raw energy data from a CSV file, cleans it, and prepares it for simulation by:
- Renaming columns for consistency (using `columns_map`).
- Converting timestamps to a datetime index.
- Calculating derived metrics (e.g., net energy, self-consumption).

**Input Schema**:
| Column            | Type      | Description                          | Example Value       |
|-------------------|-----------|--------------------------------------|---------------------|
| `time_stamp`      | `str`     | ISO-format timestamp                 | `"2024-09-01 12:00"`|
| `produced_wh`     | `float`   | Solar energy produced (Wh)           | `1500.0`            |
| `consumed_wh`     | `float`   | Household consumption (Wh)           | `2000.0`            |
| `exported_wh`     | `float`   | Energy exported to grid (Wh)         | `500.0`             |
| `imported_wh`     | `float`   | Energy imported from grid (Wh)       | `1000.0`            |

**Output Schema**:
| Column                     | Type      | Description                                  | Calculation Example                          |
|----------------------------|-----------|----------------------------------------------|----------------------------------------------|
| `time_stamp` (index)       | `datetime`| 15-minute interval timestamp                 | `2024-09-01 12:00:00`                        |
| `produced_wh`              | `float`   | Solar production (Wh)                        | `1500.0`                                     |
| `consumed_wh`              | `float`   | Consumption (Wh)                             | `2000.0`                                     |
| `exported_wh`              | `float`   | Exported to grid (Wh)                        | `500.0`                                      |
| `imported_wh`              | `float`   | Imported from grid (Wh)                      | `1000.0`                                     |
| `net_energy_wh`            | `float`   | `produced_wh - consumed_wh`                  | `-500.0` (deficit)                           |
| `self_consumption_wh`      | `float`   | `min(produced_wh, consumed_wh)`              | `1500.0`                                     |

#### `simulate_battery`
**Purpose**:
Simulates battery behavior over time by:
- Charging from **solar surplus** or **cheap grid energy** (off-peak).
- Discharging to **cover deficits** during peak hours.
- Respecting constraints:
  - `max_battery_capacity_wh`: Total storage capacity.
  - `max_charge_rate_w`/`max_discharge_rate_w`: Power limits (converted to Wh/15-min).
  - **Priority**: Use solar surplus before grid charging.

**Key Business Rules**:
- **Charging**:
  - Solar surplus (`net_energy_wh > 0`) → Charge battery first, export remainder.
- **Discharging**:
  - Energy deficit (`net_energy_wh < 0`) → Discharge battery first, import remainder.
- **Rate Limits**:
  - Charge/discharge capped at `(max_rate_w * 15/60)` Wh per interval (e.g., 3kW → 750 Wh/15-min).

**Input Schema**:
Inherits all columns from `load_and_prepare_data`.

**Output Schema**:
| Column                     | Type      | Description                                  | Calculation Example                          |
|----------------------------|-----------|----------------------------------------------|----------------------------------------------|
| `battery_charge_wh`        | `float`   | Energy added to battery (Wh)                 | `min(surplus, spare_capacity, charge_rate)`  |
| `battery_discharge_wh`     | `float`   | Energy taken from battery (Wh)               | `min(deficit, battery_level, discharge_rate)`|
| `battery_level_wh`         | `float`   | Cumulative battery state (Wh)                | `prev_level + charge - discharge`            |
| `adjusted_imported_wh`     | `float`   | Grid imports **after** battery use           | `max(0, deficit - battery_discharge)`        |
| `adjusted_exported_wh`     | `float`   | Grid exports **after** battery charging      | `max(0, surplus - battery_charge)`           |

#### `optimize_capacity`
**Purpose**:
Evaluates different solar and battery capacities to determine the optimal configuration for minimizing energy costs.

**Key Business Rules**:
- Evaluates combinations of solar and battery capacities.
- Uses pricing information to calculate costs and savings.

**Input Schema**:
Inherits all columns from `simulate_battery`.

**Output Schema**:
| Category       | Type       | Metric                     | Description                                  | Calculation Example                          |
|----------------|------------|----------------------------|----------------------------------------------|----------------------------------------------|
| **Metric**     | `str`      | `Grid > House`             | Cost of direct grid consumption              | `sum(adjusted_imported_wh * HP/HC tariff)`  |
|                |            | `Grid > Battery`           | Cost of charging battery from grid           | `sum(grid_charge_wh * HC tariff)`            |
|                |            | `Solar > House`            | Savings from self-consumption                | `sum(min(produced_wh, consumed_wh) * tariff)`|
|                |            | `Battery > House`          | Savings from battery discharge               | `sum(battery_discharge_wh * HP/HC tariff)`  |
|                |            | `Solar > Grid`             | Revenue from exporting solar                 | `sum(adjusted_exported_wh * wh_price_sale_eur)`|
| **Savings**    | `str`      | `Solar Savings`            | Sum of `Solar > House` and `Solar > Grid`    | `-785.39 + (-423.68) = -947.8`               |
|                |            | `Battery Savings`          | Savings from `Battery > House`               | `-416.76 + (-66.89) = -483.65`               |
|                |            | `All Savings`              | Sum of all savings                           | `-947.8 + (-483.65) = -1692.72`              |
| **Total**      | `str`      | `Total Imported`           | Total grid imports (HP + HC)                 | `1058.25 + 698.89 = 1757.14`                 |
|                |            | `Total Exported`           | Total grid exports                           | `-423.68`                                    |
|                |            | `Total Produced`           | Total solar production                       | `-947.8` (value of produced energy)          |
|                |            | `Total Consumed`           | Total household consumption                  | `488.1` (net cost after savings)             |
|                |            | `Total Cost`               | Net cost with PV+battery                     | `1009.7 + 886.47 = 1896.17`                  |
