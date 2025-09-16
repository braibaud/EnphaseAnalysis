# EnphaseAnalysis
Analysis for Enphase reports

Here’s the structured documentation for the three functions, covering both **functional** (purpose, logic, business rules) and **technical** (data flow, schemas, transformations) perspectives.

---

## **1. `load_and_prepare_data`**

### **Functional Documentation**
**Purpose**:
Loads raw energy data from a CSV file, cleans it, and prepares it for simulation by:
- Renaming columns for consistency (using `columns_map`).
- Converting timestamps to a datetime index.
- Calculating derived metrics (e.g., net energy, self-consumption).
- Applying energy pricing rules (peak/off-peak tariffs) to compute cost-related columns.

**Key Business Rules**:
- **Time handling**: Data is resampled to **15-minute intervals** (aligned with grid metering standards).
- **Pricing**:
  - Off-peak hours (`wh_price_low_eur`): 23:00–07:00.
  - Peak hours (`wh_price_high_eur`): 07:00–23:00.
- **Derived metrics**:
  - `net_energy_wh`: `produced_wh - consumed_wh` (positive = surplus, negative = deficit).
  - `self_consumption_wh`: Minimum of produced or consumed energy (energy used directly from solar).
  - Cost columns (`consumed_price_eur`, `imported_price_eur`, etc.) are calculated based on tariffs and energy flows.

**Dependencies**:
- Requires `columns_map` (dict) for column renaming.
- Assumes CSV has columns: `time_stamp`, `produced_wh`, `consumed_wh`, `exported_wh`, `imported_wh`.

---

### **Technical Documentation (ETL Perspective)**
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
| `consumed_price_eur`       | `float`   | Cost of consumed energy (€)                  | `imported_wh * wh_price_high_eur`            |
| `imported_price_eur`       | `float`   | Cost of grid imports (€)                     | `1000.0 * 0.20`                              |
| `exported_price_eur`       | `float`   | Revenue from exports (€)                     | `500.0 * 0.10`                               |
| `is_off_peak`              | `bool`    | `True` if timestamp is 23:00–07:00           | `True`                                       |

**Transformations**:
1. **Column Renaming**: Maps raw CSV columns to standardized names via `columns_map`.
2. **Datetime Index**: Converts `time_stamp` to `pd.DatetimeIndex` with 15-minute frequency.
3. **Derived Columns**:
   - `net_energy_wh`: Arithmetic operation.
   - `self_consumption_wh`: Element-wise `min()`.
   - Cost columns: Conditional multiplication by `wh_price_low_eur`/`wh_price_high_eur` based on `is_off_peak`.
4. **Data Validation**: Drops rows with `NaN` in critical columns (`produced_wh`, `consumed_wh`).

**Edge Cases**:
- Missing timestamps → Dropped.
- Negative energy values → Assumed invalid (dropped).
- Non-15-minute intervals → Resampled (forward-filled).

**Output**:
- **`pd.DataFrame`**: Indexed by `time_stamp`, with all output schema columns.

---

## **2. `simulate_battery`**

### **Functional Documentation**
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
  - Off-peak grid energy (`is_off_peak = True`) → Charge if battery isn’t full.
- **Discharging**:
  - Energy deficit (`net_energy_wh < 0`) → Discharge battery first, import remainder.
- **Rate Limits**:
  - Charge/discharge capped at `(max_rate_w * 15/60)` Wh per interval (e.g., 3kW → 750 Wh/15-min).

**Dependencies**:
- Input DataFrame must include columns from `load_and_prepare_data`.
- Requires `max_battery_capacity_wh`, `max_charge_rate_w`, `max_discharge_rate_w`.

---

### **Technical Documentation (ETL Perspective)**
**Input Schema**:
Inherits all columns from `load_and_prepare_data` **plus**:
| Column            | Type      | Description                          |
|-------------------|-----------|--------------------------------------|
| `battery_level_wh`| `float`   | Initial battery state (Wh)           |

**Output Schema**:


| Column                     | Type      | Description                                  | Calculation Example                          |
|----------------------------|-----------|----------------------------------------------|----------------------------------------------|
| `battery_charge_wh`        | `float`   | Energy added to battery (Wh)                 | `min(surplus, spare_capacity, charge_rate)`  |
| `battery_discharge_wh`     | `float`   | Energy taken from battery (Wh)               | `min(deficit, battery_level, discharge_rate)`|
| `battery_level_wh`         | `float`   | Cumulative battery state (Wh)                | `prev_level + charge - discharge`            |
| `adjusted_imported_wh`     | `float`   | Grid imports **after** battery use           | `max(0, deficit - battery_discharge)`        |
| `adjusted_exported_wh`     | `float`   | Grid exports **after** battery charging      | `max(0, surplus - battery_charge)`           |

**Transformations**:
1. **Stateful Calculation**: `battery_level_wh` carries over between rows (requires sorted index).
2. **Conditional Logic**:
   - **Charge**: `min(net_energy_wh, spare_capacity, charge_rate_wh)` if `net_energy_wh > 0` or `is_off_peak`.
   - **Discharge**: `min(abs(net_energy_wh), battery_level, discharge_rate_wh)` if `net_energy_wh < 0`.
3. **Rate Conversions**:
   - `max_charge_rate_w` → `max_charge_rate_wh = (max_charge_rate_w * 15) / 60`.
4. **Grid Interaction Adjustments**:
   - `adjusted_imported_wh`: Reduces grid imports by battery discharge.
   - `adjusted_exported_wh`: Reduces grid exports by battery charging.

**Edge Cases**:
- Battery full (`battery_level = capacity`) → No charging.
- Battery empty → No discharging.
- Simultaneous charge/discharge → Not allowed (net operation per interval).

**Output**:
- **`pd.DataFrame`**: Input columns + battery-specific columns (above).

---

## **`process_battery_data`**

### **Functional Documentation**
**Purpose**:
Transforms the battery simulation results into a **human-readable breakdown** of energy flows, costs, and savings, categorized by:
1. **Source → Destination** (e.g., `Grid > House`, `Solar > Battery`).
2. **Tariff Period** (HP/HC).
3. **Savings Impact** (e.g., avoided grid costs due to solar/battery).

**Key Business Rules**:
- **Energy Flows**:
  - Tracks **6 distinct paths** (e.g., `Grid > House`, `Solar > Battery`).
  - Separates **high-price (HP, 7:00–23:00)** and **low-price (HC, 23:00–7:00)** periods.
- **Cost/Savings Calculations**:
  - **Grid > House**: Cost of direct grid consumption (`imported_wh * tariff`).
  - **Solar > House**: "Savings" from self-consumption (negative cost, as it offsets grid imports).
  - **Battery > House**: Savings from using stored energy instead of grid imports.
  - **Solar > Grid**: Revenue from exporting excess solar (`exported_wh * wh_price_sale_eur`).
  - **Solar > Battery**: "Cost" of storing solar energy (opportunity cost of not exporting).
  - **Grid > Battery**: Cost of charging from the grid (only during HC in your case, since HP is avoided).
- **Savings Metrics**:
  - `Solar Savings`: Sum of `Solar > House` and `Solar > Grid` (avoided grid costs + export revenue).
  - `Battery Savings`: Savings from `Battery > House` (avoided grid imports).
  - `All Savings`: Sum of `Solar Savings` and `Battery Savings`.
- **Subscription Fee**: Prorated over the period (e.g., monthly fee divided by intervals).
- **Efficiency**: Battery losses (`battery_efficiency_pc = 96%`) are accounted for in stored/released energy.

**Dependencies**:
- Input DataFrame must include:
  - `adjusted_imported_wh`, `adjusted_exported_wh` (from `simulate_battery`).
  - `battery_charge_wh`, `battery_discharge_wh`.
  - `is_off_peak` (to split HP/HC).
- Requires tariffs (`wh_price_high_eur`, `wh_price_low_eur`, `wh_price_sale_eur`) and `subscription_monthly_fee_eur`.

---

### **Technical Documentation (ETL Perspective)**

#### **Input Schema**

Inherits all columns from `simulate_battery`, plus:
| Column                  | Type      | Description                                  |
|-------------------------|-----------|----------------------------------------------|
| `is_off_peak`           | `bool`    | `True` if timestamp is 23:00–07:00 (HC).     |

#### **Output Schema**


| Category       | Type       | Metric                     | Description                                  | Calculation Example                          |
|----------------|------------|----------------------------|----------------------------------------------|----------------------------------------------|
| **Metric**     | `str`      | `Grid > House`             | Cost of direct grid consumption              | `sum(adjusted_imported_wh * HP/HC tariff)`  |
|                |            | `Grid > Battery`           | Cost of charging battery from grid           | `sum(grid_charge_wh * HC tariff)`            |
|                |            | `Solar > House`            | Savings from self-consumption                | `sum(min(produced_wh, consumed_wh) * tariff)`|
|                |            | `Battery > House`          | Savings from battery discharge               | `sum(battery_discharge_wh * HP/HC tariff)`  |
|                |            | `Solar > Battery`          | "Cost" of storing solar (opportunity cost)   | `sum(solar_to_battery_wh * wh_price_sale_eur)`|
|                |            | `Solar > Grid`             | Revenue from exporting solar                 | `sum(adjusted_exported_wh * wh_price_sale_eur)`|
|                |            | `Subscription Fee`         | Prorated fixed fee                           | `(fee / intervals_per_month) * total_intervals`|
| **Savings**    | `str`      | `Solar Savings`            | Sum of `Solar > House` and `Solar > Grid`    | `-785.39 + (-423.68) = -947.8`               |
|                |            | `Battery Savings`          | Savings from `Battery > House`               | `-416.76 + (-66.89) = -483.65`               |
|                |            | `All Savings`              | Sum of all savings                           | `-947.8 + (-483.65) = -1692.72`              |
| **Total**      | `str`      | `Total Imported`           | Total grid imports (HP + HC)                 | `1058.25 + 698.89 = 1757.14`                 |
|                |            | `Total Exported`           | Total grid exports                           | `-423.68`                                    |
|                |            | `Total Stored`             | Energy stored in battery                     | `261.28` (cost of storing solar)             |
|                |            | `Total Produced`           | Total solar production                       | `-947.8` (value of produced energy)          |
|                |            | `Total Consumed`           | Total household consumption                  | `488.1` (net cost after savings)             |
|                |            | `Total Consumed (Naked)`   | Consumption cost **without PV/battery**      | `2633.47 + 767.85 = 3026.18`                 |
|                |            | `Total Cost`               | Net cost with PV+battery                     | `1009.7 + 886.47 = 1896.17`                  |
|                |            | `Total Cost (Naked)`       | Cost without PV/battery                      | `3588.89`                                    |

#### **Transformations**

1. **Flow Categorization**:
   - For each 15-minute interval:
     - **Grid > House**: `adjusted_imported_wh * (HP/HC tariff)`.
     - **Grid > Battery**: `grid_charge_wh * HC tariff` (only if `is_off_peak`).
     - **Solar > House**: `self_consumption_wh * (HP/HC tariff)` (negative, as it offsets grid).
     - **Battery > House**: `battery_discharge_wh * (HP/HC tariff)` (negative).
     - **Solar > Battery**: `solar_to_battery_wh * wh_price_sale_eur` (opportunity cost).
     - **Solar > Grid**: `adjusted_exported_wh * wh_price_sale_eur` (negative).
   - **Note**: `solar_to_battery_wh` is derived from `net_energy_wh` and battery logic.

2. **Tariff Splitting**:
   - HP/HC splits are applied to all metrics (e.g., `Grid > House` is split into `HP Cost`/`HC Cost`).

3. **Savings Calculations**:
   - `Solar Savings` = `Solar > House` + `Solar > Grid`.
   - `Battery Savings` = `Battery > House` (avoided grid costs).
   - `All Savings` = `Solar Savings` + `Battery Savings`.

4. **Subscription Fee**:
   - Prorated per interval (e.g., `47.02 / (30*96)` per 15-min for monthly fee).

5. **Efficiency Adjustment**:
   - Battery charge/discharge is scaled by `battery_efficiency_pc` (e.g., `battery_discharge_wh *= 0.96`).

6. **Aggregation**:
   - Sums all metrics across the entire period (e.g., yearly).
   - Converts Wh to kWh (divide by 1000) and costs to €.

#### **Edge Cases**

- **Battery Limits**:
  - `battery_discharge_lower_limit_pc = 5`: Never discharge below 5% capacity.
  - `battery_charge_upper_limit_pc = 100`: Never overcharge.
- **Negative Costs**: Valid (indicates savings/revenue).
- **Zero Flows**: Metrics like `Grid > Battery` may be zero if battery is only charged by solar.

#### **Output**

- **`pd.DataFrame`**: Pivot table with `Category`, `Type`, `HP Cost`, `HP kWh`, etc.
- **Key Insight**: The "Naked" totals (`Total Consumed (Naked)`, `Total Cost (Naked)`) represent the baseline **without PV/battery**, while other rows show the **optimized scenario**.

---
