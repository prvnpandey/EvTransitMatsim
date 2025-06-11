"""Main"""

import gzip
import xml.etree.ElementTree as ET
import pandas as pd
from speed_access import parse_events, compute_speeds, compute_travel_time
from xmldf import network_to_df
from transit.schedule import get_bus_ids, parse_transit_departures

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

busline_list = ["1"]

inbound_travel_time = {}
outbound_travel_time = {}
dep_df["Travel Time"] = None
with gzip.open(gzip_schedule_xml_path, "rt", encoding="utf-8") as f:
    schedule_tree = ET.parse(f)
for line, shapes in departure_shape_dict.items():
    inbound_ids, outbound_ids = get_bus_ids(schedule_tree, line, shapes)
    for time, bus in inbound_ids.items():
        speed_results = compute_speeds(events, network_df, id_filter=bus, v_s=1.0)
        if speed_results.empty:
            inbound_travel_time[time] = "no_events"
        else:
            inbound_travel_time[time] = compute_travel_time(speed_results)
    for time, bus in outbound_ids.items():
        speed_results = compute_speeds(events, network_df, id_filter=bus, v_s=1.0)
        if speed_results.empty:
            outbound_travel_time[time] = "no_events"
        else:
            outbound_travel_time[time] = compute_travel_time(speed_results)
    dep_df.loc[dep_df["Shape ID"] == shapes[0], "Travel Time"] = (
        f"{inbound_travel_time}"
    )
    dep_df.loc[dep_df["Shape ID"] == shapes[1], "Travel Time"] = (
        f"{outbound_travel_time}"
    )
# Compute speeds.

dep_df.to_csv("test/travel_time_test.csv")
