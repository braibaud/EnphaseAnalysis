import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as pldt
import matplotlib.patches as ptc

from .data_loader import filter_data


def get_tab_color(color_index, shade_index):
    """
    Get a color from the combined 'tab20b' and 'tab20c' colormaps.

    Parameters:
    - color_index: Index of the color group, 0 to 9.
    - shade_index: Index of the shade within the color group, 0 to 3.

    Returns:
    - RGBA color tuple.
    """
    color_index = color_index % 10
    shade_index = shade_index % 4

    cmap_name = 'tab20b' if color_index < 5 else 'tab20c'
    cmap = plt.get_cmap(cmap_name)
    pos_in_map = (color_index % 5) * 4 + shade_index

    return cmap(np.arange(20, dtype=int))[pos_in_map]


def _compute_hc_ranges(filtered_df):
    """Compute HC (off-peak) time ranges from filtered data."""
    if 'is_hc' not in filtered_df.columns:
        return None

    timestamps = filtered_df.index.to_pydatetime()
    is_hc = filtered_df['is_hc'].tolist()
    hc_ranges = []
    current_range_start = None

    for i in range(len(timestamps)):
        if is_hc[i]:
            if current_range_start is None:
                current_range_start = timestamps[i]
        else:
            if current_range_start is not None:
                hc_ranges.append((current_range_start, timestamps[i - 1]))
                current_range_start = None

    if current_range_start is not None:
        hc_ranges.append((current_range_start, timestamps[-1]))

    return hc_ranges


def plot_battery_soc_chart(
    df, start_date, end_date,
    y_min=None, y_max=None,
    hp_start_hour=7, hp_end_hour=23):
    """
    Plot the battery SOC and charging/discharging activities over a specified time period.
    """
    filtered_df = filter_data(df, start_date, end_date,
                              hp_start_hour=hp_start_hour, hp_end_hour=hp_end_hour)

    fig, ax = plt.subplots(figsize=(16, 10))

    ax.plot(filtered_df.index, filtered_df['Battery SOC'],
            label='Battery SOC', color=get_tab_color(9, 1),
            linestyle=':', linewidth=1.5)

    ax.plot(filtered_df.index, filtered_df['consumed_wh'] * 4,
            label='Consumed', color=get_tab_color(9, 1), linewidth=1.5)

    ax.set_xlabel('Time')
    ax.set_ylabel('Energy (Wh)')
    ax.set_title('Energy Flows and Battery SOC')
    ax.grid(True)

    hc_ranges = _compute_hc_ranges(filtered_df)
    if hc_ranges:
        for start, end in hc_ranges:
            ax.axvspan(start, end, color=get_tab_color(9, 3), alpha=0.3, linewidth=0)

    width = 0.01

    ax.bar(filtered_df.index, filtered_df['Grid > House'] * 4,
           width=width, color=get_tab_color(5, 2), label='Grid > House', alpha=0.7)
    bottom = filtered_df['Grid > House'] * 4

    ax.bar(filtered_df.index, filtered_df['Grid > Battery'] * 4,
           width=width, color=get_tab_color(5, 1), label='Grid > Battery', alpha=0.7, bottom=bottom)
    bottom += filtered_df['Grid > Battery'] * 4

    ax.bar(filtered_df.index, filtered_df['Solar > House'] * 4,
           width=width, color=get_tab_color(7, 3), label='Solar > House', alpha=0.7, bottom=bottom)
    bottom += filtered_df['Solar > House'] * 4

    ax.bar(filtered_df.index, filtered_df['Battery > House'] * 4,
           width=width, color=get_tab_color(6, 2), label='Battery > House', alpha=0.7, bottom=bottom)

    solar_excess = filtered_df['Solar > Battery'] + filtered_df['Solar > Grid']
    ax.plot(filtered_df.index, -solar_excess * 4,
            label='Solar Excess', color=get_tab_color(9, 1), linewidth=1.5, linestyle='-')

    ax.bar(filtered_df.index, -filtered_df['Solar > Battery'] * 4,
           width=width, color=get_tab_color(7, 2), label='Solar > Battery', alpha=0.7)

    ax.bar(filtered_df.index, -filtered_df['Solar > Grid'] * 4,
           width=width, color=get_tab_color(8, 2), label='Solar > Grid', alpha=0.7,
           bottom=-filtered_df['Solar > Battery'] * 4)

    ax.xaxis.set_major_locator(pldt.DayLocator())
    ax.xaxis.set_major_formatter(pldt.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_minor_locator(pldt.HourLocator(interval=3))
    ax.xaxis.set_minor_formatter(pldt.DateFormatter("%H:%M"))
    plt.xticks(rotation=45, ha='right')
    ax.tick_params(which='major', length=8, labelsize=10)
    ax.tick_params(which='minor', length=4, labelsize=8, color='gray')

    if y_min is not None and y_max is not None:
        ax.set_ylim(y_min, y_max)

    handles, labels = ax.get_legend_handles_labels()
    handles.append(ptc.Patch(facecolor='lightgrey', alpha=0.3, linewidth=0))
    labels.append('HC Periods')
    ax.legend(handles, labels, loc='upper right')

    plt.tight_layout()
    plt.show()


def plot_battery_soc_chart_v2(
    df, start_date, end_date,
    y_min=None, y_max=None,
    cumulative_metrics=None, reset_freq=None,
    hp_start_hour=7, hp_end_hour=23):
    """
    Enhanced battery SOC chart with optional cumulative metric sub-plots.
    """
    filtered_df = filter_data(df, start_date, end_date,
                              hp_start_hour=hp_start_hour, hp_end_hour=hp_end_hour)
    hc_ranges = _compute_hc_ranges(filtered_df)

    all_metrics = [
        "Grid > House", "Grid > Battery", "Solar > House",
        "Battery > House", "Solar > Battery", "Solar > Grid"
    ]
    metric_colors = {
        "Grid > House": (5, 2), "Grid > Battery": (5, 1),
        "Solar > House": (7, 3), "Battery > House": (6, 2),
        "Solar > Battery": (7, 2), "Solar > Grid": (8, 2)
    }

    if cumulative_metrics is None:
        cumulative_metrics = all_metrics
    elif not cumulative_metrics:
        cumulative_metrics = []
    else:
        cumulative_metrics = [m for m in cumulative_metrics if m in all_metrics]

    if len(filtered_df.index) > 1:
        time_diff = np.diff(pldt.date2num(filtered_df.index))
        width = np.min(time_diff) * 0.8
    else:
        width = 0.01

    # Identify metrics with data and compute cumulative values
    metrics_with_data = []
    all_cumulative_values = []
    all_reset_points = []

    for metric in cumulative_metrics:
        if metric not in filtered_df.columns:
            continue

        if reset_freq is None:
            cumulative_values = filtered_df[metric].cumsum() * 4
            reset_points = [len(filtered_df) - 1]
        else:
            if reset_freq == "day":
                groupby_col = filtered_df.index.date
            elif reset_freq == "HC/HP":
                if 'is_hc' not in filtered_df.columns:
                    continue
                groupby_col = (filtered_df['is_hc'] != filtered_df['is_hc'].shift(1)).cumsum()
            elif reset_freq == "week":
                groupby_col = filtered_df.index.isocalendar().week + filtered_df.index.isocalendar().year * 100
            elif reset_freq == "month":
                groupby_col = filtered_df.index.year * 12 + filtered_df.index.month
            else:
                raise ValueError(f"Unknown reset_freq: {reset_freq}")

            cumulative_values = filtered_df.groupby(groupby_col)[metric].cumsum() * 4
            reset_points = []
            for group in groupby_col.unique():
                group_mask = (groupby_col == group)
                group_positions = np.where(group_mask)[0]
                if len(group_positions) > 0:
                    reset_points.append(group_positions[-1])
            if (len(filtered_df) - 1) not in reset_points:
                reset_points.append(len(filtered_df) - 1)

        has_data = (not cumulative_values.isna().all()) and (np.abs(cumulative_values) > 1e-6).any()
        if has_data:
            metrics_with_data.append(metric)
            all_cumulative_values.append(cumulative_values)
            all_reset_points.append(reset_points)

    num_cumulative_plots = len(metrics_with_data)

    # Global min/max for cumulative plots
    if num_cumulative_plots > 0:
        all_values = []
        for cv in all_cumulative_values:
            vals = cv.dropna().values
            if len(vals) > 0:
                all_values.extend(vals)
        if len(all_values) > 0:
            global_min = np.min(all_values) / 1000
            global_max = np.max(all_values) / 1000
            y_padding = max(0.1, (global_max - global_min) * 0.1)
            global_min -= y_padding
            global_max += y_padding
        else:
            global_min, global_max = 0, 1
    else:
        global_min, global_max = 0, 1

    fig_height = 10 if num_cumulative_plots == 0 else 10 + num_cumulative_plots * 2.5
    fig = plt.figure(figsize=(16, fig_height), constrained_layout=True)

    if num_cumulative_plots == 0:
        gs = fig.add_gridspec(1, 1)
        ax = fig.add_subplot(gs[0, 0])
    else:
        gs = fig.add_gridspec(
            nrows=1 + num_cumulative_plots, ncols=1,
            height_ratios=[10] + [2.5] * num_cumulative_plots,
            hspace=0.3)
        ax = fig.add_subplot(gs[0, 0])

    # Main chart
    if 'Battery SOC' in filtered_df.columns:
        ax.plot(filtered_df.index, filtered_df['Battery SOC'] / 1000,
                label='Battery SOC', color=get_tab_color(9, 1),
                linestyle=':', linewidth=1.5)

    if 'consumed_wh' in filtered_df.columns:
        ax.plot(filtered_df.index, filtered_df['consumed_wh'] * 4 / 1000,
                label='Consumed', color=get_tab_color(9, 1), linewidth=1.5)

    ax.set_ylabel('Energy (kWh)')
    ax.set_title('Energy Flows & Battery SOC')
    ax.grid(True)

    if hc_ranges is not None:
        for start, end in hc_ranges:
            ax.axvspan(start, end, color=get_tab_color(9, 3), alpha=0.3, linewidth=0)

    # Positive bars
    bottom_pos = np.zeros(len(filtered_df))
    if 'Grid > House' in filtered_df.columns:
        ax.bar(filtered_df.index, filtered_df['Grid > House'] * 4 / 1000,
               width=width, color=get_tab_color(5, 2), label='Grid > House', alpha=0.7)
        bottom_pos = filtered_df['Grid > House'].values * 4 / 1000

    if 'Grid > Battery' in filtered_df.columns and 'Grid > House' in filtered_df.columns:
        ax.bar(filtered_df.index, filtered_df['Grid > Battery'] * 4 / 1000,
               width=width, color=get_tab_color(5, 1), label='Grid > Battery',
               alpha=0.7, bottom=bottom_pos)
        bottom_pos = bottom_pos + filtered_df['Grid > Battery'].values * 4 / 1000
    elif 'Grid > Battery' in filtered_df.columns:
        bottom_pos = filtered_df['Grid > Battery'].values * 4 / 1000

    if 'Solar > House' in filtered_df.columns:
        ax.bar(filtered_df.index, filtered_df['Solar > House'] * 4 / 1000,
               width=width, color=get_tab_color(7, 3), label='Solar > House',
               alpha=0.7, bottom=bottom_pos)
        bottom_pos = bottom_pos + filtered_df['Solar > House'].values * 4 / 1000

    if 'Battery > House' in filtered_df.columns:
        ax.bar(filtered_df.index, filtered_df['Battery > House'] * 4 / 1000,
               width=width, color=get_tab_color(6, 2), label='Battery > House',
               alpha=0.7, bottom=bottom_pos)

    if 'Solar > Battery' in filtered_df.columns and 'Solar > Grid' in filtered_df.columns:
        solar_excess = filtered_df['Solar > Battery'] + filtered_df['Solar > Grid']
        ax.plot(filtered_df.index, -solar_excess * 4 / 1000,
                label='Solar Excess', color=get_tab_color(9, 1),
                linewidth=1.5, linestyle='-')

    # Negative bars
    if 'Solar > Battery' in filtered_df.columns:
        ax.bar(filtered_df.index, -filtered_df['Solar > Battery'] * 4 / 1000,
               width=width, color=get_tab_color(7, 2), label='Solar > Battery', alpha=0.7)
        bottom_neg = -filtered_df['Solar > Battery'].values * 4 / 1000
    else:
        bottom_neg = np.zeros(len(filtered_df))

    if 'Solar > Grid' in filtered_df.columns:
        ax.bar(filtered_df.index, -filtered_df['Solar > Grid'] * 4 / 1000,
               width=width, color=get_tab_color(8, 2), label='Solar > Grid',
               alpha=0.7, bottom=bottom_neg)

    # X-axis formatting
    ax.xaxis.set_major_locator(pldt.DayLocator())
    ax.xaxis.set_major_formatter(pldt.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_minor_locator(pldt.HourLocator(interval=3))
    ax.xaxis.set_minor_formatter(pldt.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    plt.setp(ax.xaxis.get_minorticklabels(), rotation=45, ha='right')
    ax.tick_params(which='major', length=8, labelsize=8, color='gray')
    ax.tick_params(which='minor', length=4, labelsize=8, color='gray')

    if y_min is not None and y_max is not None:
        ax.set_ylim(y_min / 1000, y_max / 1000)

    # Legend
    if ax.has_data():
        handles, labels = ax.get_legend_handles_labels()
        seen = set()
        unique_handles, unique_labels = [], []
        for handle, label in zip(handles, labels):
            if label not in seen:
                seen.add(label)
                unique_handles.append(handle)
                unique_labels.append(label)
        if 'is_hc' in filtered_df.columns and hc_ranges:
            unique_handles.append(ptc.Patch(facecolor='lightgrey', alpha=0.3, linewidth=0))
            unique_labels.append('HC Periods')
        if unique_handles:
            ax.legend(unique_handles, unique_labels, loc='upper left')

    # Cumulative sub-plots
    if num_cumulative_plots > 0:
        for i, (metric, cumulative_values, reset_points) in enumerate(
                zip(metrics_with_data, all_cumulative_values, all_reset_points)):
            ax_cum = fig.add_subplot(gs[i + 1, 0], sharex=ax)

            if hc_ranges is not None:
                for start, end in hc_ranges:
                    ax_cum.axvspan(start, end, color=get_tab_color(9, 3), alpha=0.3, linewidth=0)

            cumulative_values_kwh = cumulative_values / 1000
            ax_cum.bar(filtered_df.index, cumulative_values_kwh,
                       width=width, color=get_tab_color(*metric_colors[metric]),
                       label=metric, alpha=0.7)
            ax_cum.set_ylabel('Energy (kWh)')
            ax_cum.set_title(f'{metric} (Cumulative)')
            ax_cum.grid(True)

            for idx in reset_points:
                if idx < len(cumulative_values_kwh):
                    value_kwh = cumulative_values_kwh.iloc[idx]
                    x_pos = filtered_df.index[idx]
                    height = cumulative_values_kwh.iloc[idx]
                    if height >= 0:
                        va = 'bottom'
                        text_y = height + (global_max - global_min) * 0.05
                    else:
                        va = 'top'
                        text_y = height - (global_max - global_min) * 0.05
                    ax_cum.text(x_pos, text_y, f"{abs(value_kwh):.1f} kWh",
                                ha='center', va=va, fontsize=8, color='black')

            ax_cum.legend(loc='upper left')
            ax_cum.set_ylim(global_min, global_max)

            ax_cum.xaxis.set_major_locator(pldt.DayLocator())
            ax_cum.xaxis.set_major_formatter(pldt.DateFormatter("%Y-%m-%d"))
            ax_cum.xaxis.set_minor_locator(pldt.HourLocator(interval=3))
            ax_cum.xaxis.set_minor_formatter(pldt.DateFormatter("%H:%M"))
            plt.setp(ax_cum.xaxis.get_majorticklabels(), rotation=45, ha='right')
            plt.setp(ax_cum.xaxis.get_minorticklabels(), rotation=45, ha='right')
            ax_cum.tick_params(which='major', length=8, labelsize=8, color='gray')
            ax_cum.tick_params(which='minor', length=4, labelsize=8, color='gray')

    plt.tight_layout()
    plt.show()
