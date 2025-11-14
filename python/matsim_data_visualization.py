import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Set global font and style
plt.rcParams.update({
    "font.size": 14,
    "axes.titlesize": 18,
    "axes.labelsize": 16,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "legend.fontsize": 13
})
sns.set_style("whitegrid")

# Load dataset
df = pd.read_excel('python/optimization_dataset.xlsx')

# Parse departure/arrival times
df['Departure DT'] = pd.to_datetime(df['Departure Time'], format='%H:%M:%S', errors='coerce')
df['Arrival DT']   = pd.to_datetime(df['Arrival Time'],   format='%H:%M:%S', errors='coerce')

# Create hourly bins (0–23)
df['Dep Hour'] = df['Departure DT'].dt.hour
df['Arr Hour'] = df['Arrival DT'].dt.hour

# 1. Histogram of departures and arrivals by hour
dep_counts = df['Dep Hour'].value_counts().reindex(range(24), fill_value=0)
arr_counts = df['Arr Hour'].value_counts().reindex(range(24), fill_value=0)
hours = pd.date_range('2023-01-01', periods=24, freq='H')

plt.figure(figsize=(12, 6))
plt.bar(np.arange(24) - 0.2, dep_counts, width=0.4, label='Departures', color='#4C72B0')
plt.bar(np.arange(24) + 0.2, arr_counts, width=0.4, label='Arrivals', color='#55A868')
plt.xlabel('Hour of Day')
plt.ylabel('Number of Trips')
plt.xticks(np.arange(24), [h.strftime('%H:00') for h in hours], rotation=45)
plt.legend()
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.show()

# 2. Scheduled vs Actual Travel Time scatter + 1:1 line
plt.figure(figsize=(8, 8))
plt.scatter(df['Scheduled Travel Time (min)'], df['Travel Time (min)'], alpha=0.6, color='#4C72B0', edgecolor='k')
lims = [min(df['Scheduled Travel Time (min)'].min(), df['Travel Time (min)'].min()),
        max(df['Scheduled Travel Time (min)'].max(), df['Travel Time (min)'].max())]
plt.plot(lims, lims, 'r--', linewidth=2, label='1:1 Line')
plt.xlabel('Timetable (min)')
plt.ylabel('Simulated Travel Time (min)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.7)
plt.tight_layout()
plt.show()

# 3. Boxplot of Avg Energy by Line ID
plt.figure(figsize=(14, 6))
sns.boxplot(x='Line ID', y='Avg Energy (kWh/km)', data=df, palette='Set3')

# Add mean line
mean_energy = df['Avg Energy (kWh/km)'].mean()
plt.axhline(y=mean_energy, color='r', linestyle='--', label=f'Fleet Average: {mean_energy:.2f} kWh/km')

plt.xlabel('Line ID')
plt.ylabel('Average Energy Consumption (kWh/km)')
plt.xticks(rotation=90, ha='right', fontsize=8)
plt.legend()
plt.tight_layout()
plt.show()

# 4. Heatmap of Trips per Interval by Line

# Floor times to 15-minute intervals
df['Dep Interval'] = df['Departure DT'].dt.floor('15min')
df['Arr Interval'] = df['Arrival DT'].dt.floor('15min')

# Combine departures and arrivals
df_dep = df[['Line ID','Dep Interval']].rename(columns={'Dep Interval':'Interval'})
df_arr = df[['Line ID','Arr Interval']].rename(columns={'Arr Interval':'Interval'})
df_int = pd.concat([df_dep, df_arr], ignore_index=True)

# Pivot to get counts per line × interval
heat_df = df_int.pivot_table(index='Line ID', columns='Interval', aggfunc='size', fill_value=0)

# 1. Count total trips per line
line_trip_counts = df_int['Line ID'].value_counts()
# 2. Get the top 10 lines
top10_lines = line_trip_counts.head(10).index
# 3. Filter heat_df to only those lines
heat_df_top10 = heat_df.loc[heat_df.index.isin(top10_lines)]

# 4. Plot heatmap for top 10 lines
plt.figure(figsize=(18, 6))
sns.heatmap(
    heat_df_top10,
    cmap='YlGnBu',
    linewidths=0.5,
    linecolor='gray',
    cbar_kws={'label': 'Number of Trips'},
    annot=False,
    fmt='d'
)
plt.xlabel('Time of Day')
plt.ylabel('Line ID')

# X-axis: label only on the hour marks
intervals = heat_df_top10.columns.to_numpy()
intervals_ts = pd.to_datetime(intervals)
hour_locs = [i for i, t in enumerate(intervals_ts) if t.minute == 0]
hour_labels = [t.strftime('%H:%M') for t in intervals_ts[hour_locs]]
plt.xticks(hour_locs, hour_labels, rotation=45)

plt.tight_layout()
plt.show()

# 5. Number of simultaneous trips per timestep
timestep = '15min'  # change to '15min' or other pandas offset alias if desired

# Build +1/-1 events at departures/arrivals and compute running sum (active trips)
events_dep = pd.Series(1, index=df['Departure DT'])
events_arr = pd.Series(-1, index=df['Arrival DT'])
events = pd.concat([events_dep, events_arr]).groupby(level=0).sum().sort_index()
active = events.cumsum()

# Create regular time index and forward-fill the active count to each timestep
start = df['Departure DT'].min().floor(timestep)
end = df['Arrival DT'].max().ceil(timestep)
time_index = pd.date_range(start, end, freq=timestep)
active_ts = active.reindex(time_index, method='ffill').fillna(0).astype(int)

# Plot time series (step plot with filled area)
plt.figure(figsize=(14, 5))
plt.plot(active_ts.index, active_ts.values, drawstyle='steps-post', color='#4C72B0', linewidth=1.5)
plt.fill_between(active_ts.index, active_ts.values, step='post', alpha=0.25, color='#4C72B0')
plt.xlabel('Time of Day')
plt.ylabel('Number of Simultaneous Trips')
#plt.title(f'Number of Simultaneous Trips per {timestep}')
plt.grid(True, linestyle='--', alpha=0.6)

# Set x-axis ticks to show only hours
hours = pd.date_range(start.floor('H'), end.ceil('H'), freq='H')
plt.xticks(hours, [h.strftime('%H:00') for h in hours], rotation=45)

plt.tight_layout()
plt.show()