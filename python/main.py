"""Main"""

import gzip
import xml.etree.ElementTree as ET

import pandas as pd
import line_profiler

from speed_access import (
    parse_events,
    compute_speeds,
    compute_travel_time,
    route_distances,
)
from xmldf import network_to_df
from transit.schedule import (
    get_bus_ids,
    parse_transit_departures,
    parse_scheduled_travel_time,
)
from energy import calculate_energy_consumption



gzip_event_xml_path = "python/output_events.xml.gz"
gzip_network_xml_path = "python/network/output_network.xml.gz"
gzip_schedule_xml_path = "python/transit/output_TransitSchedule.xml.gz"

# Extract the compressed XML network file and get it in a df.
with gzip.open(gzip_network_xml_path, "rt", encoding="utf-8") as f:
    network_df = network_to_df(f)

# Extract link lengths and freespeeds into dict.
link_lengths = network_df["length"].to_dict()
freespeeds = network_df["freespeed"].to_dict()
print("Link loaded")

# Parse events.
csv_events = False
if csv_events:
    events = pd.read_csv('python/output_events.csv', dtype={'link':str, 'actType':str})
    print("Events loaded")
else:
    with gzip.open(gzip_event_xml_path, "rt", encoding="utf-8") as f:
        events = parse_events(f)
    print("Events loaded")


# Iterate through the transit schedule.
departure_path = "python/transit_departures.csv"  # adjust path as needed
dep_df = pd.read_csv(departure_path)
departure_shape_dict = parse_transit_departures(dep_df)

travel_time_output_cols = {
    "Line ID": pd.Series(dtype='str'),
    "Shape ID": pd.Series(dtype='str'),
    "Departure Time": pd.Series(dtype='str'),
    "Vehicle ID": pd.Series(dtype='str'),
    "Scheduled Travel Time (min)": pd.Series(dtype='float'),
    "Travel Time (min)": pd.Series(dtype='float'),
    "Distance (m)": pd.Series(dtype='float'),
    "Energy Consumption (KJ)": pd.Series(dtype='float'),
}

TT_output_df = pd.DataFrame(travel_time_output_cols)

travel_time_tuple = ({}, {})

with gzip.open(gzip_schedule_xml_path, "rt", encoding="utf-8") as f:
    schedule_tree = ET.parse(f)


#@profile
#def loop(TT_output_df):
try:
    total_lines = len(departure_shape_dict)
    completed_lines = 0
    for line, shapes in departure_shape_dict.items():
        print(f"line: {line}")
        bus_id_tuple = get_bus_ids(schedule_tree, line, shapes)
        schedule_time_tuple = parse_scheduled_travel_time(schedule_tree, line, shapes)

        for i, shape in enumerate(shapes):
            distance = route_distances(line, shape, schedule_tree, network_df)
            for time, bus in bus_id_tuple[i].items():
                speed_results = compute_speeds(events, network_df, id_filter=bus, v_s=1.0)
                if speed_results.empty:
                    travel_time_tuple[i][time] = "no_events"
                    energy_consumption = 0
                else:
                    travel_time_tuple[i][time] = compute_travel_time(speed_results)
                    energy_consumption = calculate_energy_consumption(speed_results)

                output_row = {
                    "Line ID": line,
                    "Shape ID": shape,
                    "Departure Time": time,
                    "Vehicle ID": bus_id_tuple[i][time],
                    "Scheduled Travel Time (min)": schedule_time_tuple[i][time],
                    "Travel Time (min)": travel_time_tuple[i][time],
                    "Distance (m)": distance,
                    "Energy Consumption (KJ)": energy_consumption,
                }
                TT_output_df = pd.concat(
                    [TT_output_df, pd.DataFrame([output_row])], ignore_index=True
                )
        completed_lines +=1
        print(f"{(completed_lines/total_lines)*100:.2f}% of lines completed")



except KeyboardInterrupt:
    TT_output_df.to_csv("python/transit_departure_new_format.csv")
    print("saved partial departures ")
    raise


#loop(TT_output_df)
# Compute speeds.

TT_output_df.to_csv("python/transit_departure_new_format.csv")
print("saved departure ")
