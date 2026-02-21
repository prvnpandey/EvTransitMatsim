"""used to generate speed profile figures"""
import gzip
import pandas as pd

from speed_access import plot_speeds, parse_events, compute_speeds
from xmldf import network_to_df

gzip_event_xml_path = "python/xml/output_events.xml.gz"
gzip_network_xml_path = "python/xml/output_network.xml.gz"
do_json = False
use_json = False
json_path = "python/events.json"

## CHANGE THESE VARIABLES
vehicle_ref_id = "veh_2871_bus"
start = 0
end = None

with gzip.open(gzip_network_xml_path, "rt", encoding="utf-8") as f:
    network_df = network_to_df(f)
print("Link loaded")

if use_json:
    events = pd.read_json(json_path, orient="records", lines=True)
else:
    with gzip.open(gzip_event_xml_path, "rt", encoding="utf-8") as f:
        events = parse_events(f)
if do_json:
    events.to_json(json_path, orient="records", lines=True, force_ascii=False)

print("Events loaded")

speed_results = compute_speeds(
    events, network_df, id_filter=vehicle_ref_id, v_s=1.0
)
plot_speeds(speed_results,vehicle_ref_id,start_time=start, end_time=end)
