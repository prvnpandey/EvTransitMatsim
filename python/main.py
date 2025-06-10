import gzip
import xml.etree.ElementTree as ET
from collections import defaultdict
from dbfread import DBF
import matplotlib.pyplot as plt
import pandas as pd
from speed_access import *
from xmldf import network_to_df
from analyze_results import analysis
from transit.schedule import get_bus_ids
gzip_event_xml_path = 'python/output_events.xml.gz' 
gzip_network_xml_path = "python/network/output_network.xml.gz"
gzip_schedule_xml_path = "python/transit/output_TransitSchedule.xml.gz"

# Extract the compressed XML network file and get it in a df.
with gzip.open(gzip_network_xml_path, "rt", encoding="utf-8") as f:
    network_df = network_to_df(f)

# Extract link lengths and freespeeds into dict.
link_lengths = network_df['length'].to_dict()
freespeeds = network_df['freespeed'].to_dict()
print('Link loaded')

# Parse events.

with gzip.open(gzip_event_xml_path, "rt", encoding="utf-8") as f:
    events = parse_events(f)
print('Events loaded')


# Iterate through the transit schedule.
busline_list = ['1']
reference_trip_dict = {}
with gzip.open(gzip_schedule_xml_path, "rt", encoding="utf-8") as f:
    schedule_tree = ET.parse(f)
for line in busline_list:
    reference_trip_dict[line] = get_bus_ids(schedule_tree, line)
    for bus in reference_trip_dict[line]:
        speed_results = compute_speeds(events, network_df, id_filter=bus, v_s=1.0)
        break
# Compute speeds.

analysis(speed_results, freespeeds)