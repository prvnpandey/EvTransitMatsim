import gzip
import xml.etree.ElementTree as ET
from collections import defaultdict
from dbfread import DBF
import matplotlib.pyplot as plt
import pandas as pd
from speed_access import *
from networkxml import network_to_csv
xml_filename = 'python/output_events.xml'        # path to your MATSim events XML file
dbf_filename = 'python/links.dbf'         # path to your links DBF file
gzipped_xml_path = "python/network/output_network.xml.gz"

# Extract the compressed XML network file and get it in a df.
with gzip.open(gzipped_xml_path, "rt", encoding="utf-8") as f:
    network_df = network_to_csv(f)

# Extract link lengths and freespeeds into dict.
link_lengths = network_df.set_index('link_id')['length'].to_dict()
freespeeds = network_df.set_index('link_id')['freespeed'].to_dict()
print('Link loaded')

# Parse events.
events = parse_events(xml_filename)
print('Events loaded')

# Compute speeds.
speed_results = compute_speeds(events, link_lengths, freespeeds, v_s=1.0)

# Print all results.
for rec in speed_results[:10]:  # Print first 10 records for brevity
    free_speed = freespeeds.get(rec['link'], None)
    print(f"Vehicle {rec['vehicle']} on link {rec['link']} (length: {rec['length']:.2f}m, free speed: {rec['freespeed']:.2f} m/s): "
          f"Entered at {rec['entry_time']} sec, left at {rec['exit_time']} sec, "
          f"travel time = {rec['travel_time']} sec, speed = {rec['speed']:.2f} m/s, "
          f"freespeed distance = {rec['freespeed_distance']:.2f}m, stop-and-go distance = {rec['stop_and_go_distance']:.2f}m, "
          f"freespeed time = {rec['freespeed_time']:.2f}s, stop-and-go time = {rec['stop_and_go_time']:.2f}s")
    
# Print results for a specific vehicle ID.
specific_vehicle_id = '44227'
specific_vehicle_results = [r for r in speed_results if r['vehicle'] == specific_vehicle_id]
for rec in specific_vehicle_results[:10]:
    print(f"Specific Vehicle {rec['vehicle']} on link {rec['link']} (length: {rec['length']:.2f}m, free speed: {rec['freespeed']:.2f} m/s): "
          f"Entered at {rec['entry_time']} sec, left at {rec['exit_time']} sec, "
          f"travel time = {rec['travel_time']} sec, speed = {rec['speed']:.2f} m/s, "
          f"freespeed distance = {rec['freespeed_distance']:.2f}m, stop-and-go distance = {rec['stop_and_go_distance']:.2f}m, "
          f"freespeed time = {rec['freespeed_time']:.2f}s, stop-and-go time = {rec['stop_and_go_time']:.2f}s")
    
plot_speeds(speed_results, '44227', 14400, 15450)