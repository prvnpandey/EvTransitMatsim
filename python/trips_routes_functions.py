import pandas as pd
from datetime import datetime, timedelta
import heapq
import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import numpy as np
import pprint

def clean_inbound_outbound(df, time_col='Unique Departure Times (HH:mm)') -> pd.DataFrame:
    """
    From a raw timetable DataFrame, keep only one inbound and one outbound Shape per Line:
      • We count how many departure times each row has,
      • then for each (Line ID, Direction) we pick the row with the maximum trips,
      • finally we return a smaller df with exactly those rows.
    """
    df = df.copy()
    # count trips: (#commas + 1) in the time string
    df['num_trips'] = df[time_col].str.count(',') + 1

    # collect the “best” shape for each line+direction
    best_rows = []
    for (line, direction), group in df.groupby(['Line ID', 'Direction']):
        # find the index of the row with the maximum num_trips
        best_idx = group['num_trips'].idxmax()
        best_rows.append(df.loc[best_idx])

    # assemble cleaned DataFrame
    clean_df = pd.DataFrame(best_rows).reset_index(drop=True)
    # drop auxiliary column
    clean_df = clean_df.drop(columns=['num_trips'])
    return clean_df

def parse_times(times_str: str) -> list[datetime]:
    """
    Convert a comma-separated ‘HH:mm’ string into a list of datetime objects (same arbitrary date).
    If hour >= 24, roll over to next day(s) as needed.
    """
    times = []
    for t in times_str.split(','):
        t = t.strip()
        if not t:
            continue
        h, m = map(int, t.split(':'))
        if h >= 24:
            dt = datetime.strptime('%02d:%02d' % (h % 24, m), '%H:%M') + timedelta(days=h // 24)
        elif 0 <= h < 24:
            dt = datetime.strptime('%02d:%02d' % (h, m), '%H:%M')
        else:
            print(f"Warning: Skipping invalid time '{t}'")
            continue
        times.append(dt)
    return times

def calculate_bus_requirements_interlined(df, trip_times: dict[str, int], default_trip_time: int = 30, time_col: str = 'Unique Departure Times (HH:mm)') -> dict:
    """
    For each Line ID, compute per-route (variable) trip_time_min:
      - total number of trips
      - first departure & last arrival (HH:MM)
      - total span of operation (minutes)
      - minimal buses required when interlining inbound↔outbound
      - per-bus info: first departure, last arrival, trips

    Args:
      df: DataFrame with columns ['Line ID','Direction',time_col]
      trip_times: dict mapping Line ID -> trip_time_min (in minutes)
      default_trip_time: fallback if a route not in trip_times
    """
    results = {}
    df = df.rename(columns=lambda c: c.strip())

    for line, grp in df.groupby('Line ID'):
        trip_time_min = trip_times.get(line, default_trip_time)
        dep = {'Inbound': [], 'Outbound': []}
        for _, row in grp.iterrows():
            direction = str(row['Direction']).strip().capitalize()
            if direction in dep:
                dep[direction].extend(parse_times(row[time_col]))
        for d in dep:
            dep[d].sort()

        events = [(t, d) for d in dep for t in dep[d]]
        if not events:
            continue
        events.sort()

        avail = {'Inbound': [], 'Outbound': []}
        buses_needed = 0
        bus_history = []
        first_dep = events[0][0]
        last_arr  = first_dep

        for dep_time, direction in events:
            heap = avail[direction]
            if heap and heap[0][0] <= dep_time:
                # Reuse a bus
                _, bus_id = heapq.heappop(heap)
                bus_history[bus_id].append((dep_time, dep_time + timedelta(minutes=trip_time_min)))
            else:
                # New bus
                bus_id = len(bus_history)
                buses_needed += 1
                bus_history.append([(dep_time, dep_time + timedelta(minutes=trip_time_min))])

            arrival = dep_time + timedelta(minutes=trip_time_min)
            other = 'Outbound' if direction=='Inbound' else 'Inbound'
            heapq.heappush(avail[other], (arrival, bus_id))
            if arrival > last_arr:
                last_arr = arrival

        total_trips = sum(len(dep[d]) for d in dep)
        total_span_min = (last_arr - first_dep).total_seconds() / 60

        buses_info = []
        for trips in bus_history:
            first_trip, _ = trips[0]
            _, last_trip = trips[-1]
            buses_info.append({
                'first_departure': first_trip.strftime('%H:%M'),
                'last_arrival':    last_trip.strftime('%H:%M'),
                'num_trips':       len(trips),
                'trips':           [(d.strftime('%H:%M'), a.strftime('%H:%M')) for d, a in trips]
            })

        results[line] = {
            'num_trips':                 total_trips,
            'first_departure':           first_dep.strftime('%H:%M'),
            'last_arrival':              last_arr.strftime('%H:%M'),
            'total_operational_time_min': round(total_span_min,1),
            'trip_time_min':             trip_time_min,
            'buses_required':            buses_needed,
            'buses':                     buses_info
        }

    return results