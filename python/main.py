"""Main"""

import gzip
import xml.etree.ElementTree as ET
import pandas as pd
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
    parse_departure_travel_time,
)

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
with gzip.open(gzip_event_xml_path, "rt", encoding="utf-8") as f:
    events = parse_events(f)
print("Events loaded")


# Iterate through the transit schedule.
departure_path = "python/transit_departures.xlsx"  # adjust path as needed
dep_df = pd.read_excel(departure_path)
departure_shape_dict = parse_transit_departures(dep_df)
dep_df_copy = dep_df.copy()

busline_list = ["1"]

inbound_travel_time = {}
outbound_travel_time = {}
dep_df["Travel Time (min)"] = None


with gzip.open(gzip_schedule_xml_path, "rt", encoding="utf-8") as f:
    schedule_tree = ET.parse(f)

for line, shapes in departure_shape_dict.items():
    inbound_travel_time, outbound_travel_time = parse_departure_travel_time(
        schedule_tree, line, shapes
    )
    in_route_dist = route_distances(line, shapes[0], schedule_tree, network_df)
    dep_df.loc[
        dep_df["Shape ID"] == shapes[0], ["Travel Time (min)", "distance (m)"]
    ] = (f"{inbound_travel_time}", f"{in_route_dist}")
    out_route_dist = route_distances(line, shapes[1], schedule_tree, network_df)
    dep_df.loc[
        dep_df["Shape ID"] == shapes[1], ["Travel Time (min)", "distance (m)"]
    ] = (f"{outbound_travel_time}", f"{in_route_dist}")
# Compute speeds.

dep_df.to_csv("python/transit_departure_with_travel_time.csv")
print("saved departure ")


# Using events to determine travel times
while False:
    inbound_id_dict = {}
    outbound_id_dict = {}
    for line, shapes in departure_shape_dict.items():
        inbound_ids, outbound_ids = get_bus_ids(schedule_tree, line, shapes)
        for time, bus in inbound_ids.items():
            speed_results = compute_speeds(events, network_df, id_filter=bus, v_s=1.0)
            inbound_id_dict[time] = bus
            if speed_results.empty:
                inbound_travel_time[time] = "no_events"
            else:
                inbound_travel_time[time] = compute_travel_time(speed_results)
        for time, bus in outbound_ids.items():
            speed_results = compute_speeds(events, network_df, id_filter=bus, v_s=1.0)
            outbound_id_dict[time] = bus
            if speed_results.empty:
                outbound_travel_time[time] = "no_events"
            else:
                outbound_travel_time[time] = compute_travel_time(speed_results)
        dep_df_copy.loc[dep_df["Shape ID"] == shapes[0], ["Travel Time", "bus_id"]] = (
            f"{inbound_travel_time}",
            f"{inbound_id_dict}",
        )
        dep_df_copy.loc[dep_df["Shape ID"] == shapes[1], ["Travel Time", "bus_id"]] = (
            f"{outbound_travel_time}",
            f"{outbound_id_dict}",
        )
        break
    dep_df_copy.to_csv("python/travel_time_from_events.csv")
