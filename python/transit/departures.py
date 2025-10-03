"""
This module takes the 'output_TransitSchedule.xml.gz' and creates a csv file containing
the unique departure times for every line which will then be used in the main.py file.
"""
import xml.etree.ElementTree as ET

import pandas as pd

def create_transit_departures(tree: ET.ElementTree, save=False):
    """
    Creates a transit_departure.csv file based on output_TransitSchedule.xml.gz.

    
    inputs: xml_file - xml file inside of output_TransitSchedule.xml.gz.

    returns: transit_departures: dataframe of transit departures that can be saved as 
        a csv.
    """
    
    root = tree.getroot()

    # Use a dictionary to group by (line_id, shape_id, direction)
    grouped = {}

    for line in root.findall(".//transitLine"):
        line_id = line.attrib.get("id")
        for route in line.findall("transitRoute"):
            # Extract shape id and direction from description
            desc_elem = route.find("description")
            if desc_elem is not None and desc_elem.text:
                shape_id = desc_elem.text[8:]
            else:
                shape_id = ""
            direction = ""
            if "-R-" in shape_id:
                direction = "Outbound"
            elif "-A-" in shape_id:
                direction = "Inbound"
            else:
                direction = "Unknown"

            key = (line_id, shape_id, direction)
            if key not in grouped:
                grouped[key] = set()
            for dep in route.findall(".//departure"):
                dep_time = dep.attrib.get("departureTime")
                if dep_time:
                    h, m, s = map(int, dep_time.split(":"))
                    if h >= 24:
                        h = h % 24
                    grouped[key].add(f"{h:02d}:{m:02d}")

    # Prepare data for DataFrame
    data = []
    for (line_id, shape_id, direction), times in grouped.items():
        times = sorted(times)
        data.append({
            "Line ID": line_id,
            "Shape ID": shape_id,
            "Direction": direction,
            "Unique Departure Times (HH:mm)": ", ".join(times)
        })

    df = pd.DataFrame(data)
    # Optionally, save the df to a csv to avoid having to always run
    if save:
        df.to_csv("python/transit_departures.csv", index=False)
        print("transit_departures.csv overwritten")
    return df
