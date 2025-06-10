"""
Collection of functions for calculating speed profile of vehicles
"""

import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import pandas as pd

# Load link lengths from the links.dbf.
# Assumes that each record has at least a 'link_id' and a 'length' field.


def parse_events(xml_filename):
    """Reads MATSim events file and returns a pandas df containing events"""
    events = []
    # Use 'end' event so that the element is fully built.
    context = ET.iterparse(xml_filename, events=("end",))
    for _, elem in context:
        if elem.tag == "event":
            # Check that both vehicle and link exist
            vehicle = elem.attrib.get("vehicle")
            link = elem.attrib.get("link")
            if vehicle and link:
                time = float(elem.attrib.get("time", 0))
                event_type = elem.attrib.get("type", "")
                events.append(
                    {"time": time, "type": event_type, "vehicle": vehicle, "link": link}
                )
            # Clear the element to free memory.
            elem.clear()
    df = pd.DataFrame(events)
    df = df.sort_values(by="time").reset_index(drop=True)
    return df


def compute_speeds(events_df, network, id_filter: str, v_s=1):
    """calculates speed profile of given id and returns a df"""
    # For a given vehicle (id_filter) and link, store the time when the vehicle entered.
    entered_times = {}
    # Results: a list of records with vehicle, link, start time,
    # end time, travel time, link length, speed, freespeed,
    # and aggregated link statistics.
    results = []
    link_statistics = {}

    filtered_events_df = events_df[events_df["vehicle"] == id_filter]
    for _, event in filtered_events_df.iterrows():
        vehicle = event["vehicle"]
        link = event["link"]
        time = event["time"]
        key = (vehicle, link)
        if event["type"] == "entered link":
            # Record the time of entry for the vehicle on the link.
            entered_times[key] = time
        elif event["type"] == "left link":
            # Check if we have a matching entered event.
            if key in entered_times:
                entry_time = entered_times.pop(key)
                travel_time = time - entry_time
                if travel_time > 0:
                    # Get the link length and freespeed; default to None if missing.
                    length = float(network.loc[link, "length"])
                    freespeed = float(network.loc[link, "freespeed"])
                    if length is not None:
                        speed = (
                            length / travel_time
                        )  # speed units depend on the length and time units
                        # Initialize link statistics if not already present.
                        if link not in link_statistics:
                            link_statistics[link] = {
                                "freespeed_distance": 0,
                                "stop_and_go_distance": 0,
                                "freespeed_time": 0,
                                "stop_and_go_time": 0,
                            }

                        # Update link statistics based on speed and freespeed.
                        if speed > 0:
                            if speed >= freespeed:
                                # Entire length is traveled at freespeed
                                link_statistics[link]['freespeed_distance'] += length
                                link_statistics[link]['freespeed_time'] += travel_time
                            elif freespeed > v_s:
                                # Calculate stop-and-go distance using the provided formula
                                stop_and_go_distance = (length * v_s * (freespeed - speed)) / (speed * (freespeed - v_s))
                                stop_and_go_time = stop_and_go_distance / v_s
                                freespeed_time = travel_time - stop_and_go_time ### !!!!
                                link_statistics[link]['stop_and_go_distance'] += stop_and_go_distance
                                link_statistics[link]['stop_and_go_time'] += stop_and_go_time
                                # Remaining distance and time are considered as freespeed
                                link_statistics[link]['freespeed_distance'] += (length - stop_and_go_distance)
                                link_statistics[link]['freespeed_time'] += freespeed_time
                            else:
                                # If freespeed <= v_s, consider the entire length as stop-and-go
                                link_statistics[link]['stop_and_go_distance'] += length
                                link_statistics[link]['stop_and_go_time'] += travel_time

                        # Append detailed record to results.
                        results.append(
                            {
                                "vehicle": vehicle,
                                "link": link,
                                "entry_time": entry_time,
                                "exit_time": time,
                                "travel_time": travel_time,
                                "length": length,
                                "speed": speed,
                                "freespeed": freespeed,
                                "freespeed_distance": link_statistics[link][
                                    "freespeed_distance"
                                ],
                                "stop_and_go_distance": link_statistics[link][
                                    "stop_and_go_distance"
                                ],
                                "freespeed_time": link_statistics[link][
                                    "freespeed_time"
                                ],
                                "stop_and_go_time": link_statistics[link][
                                    "stop_and_go_time"
                                ],
                            }
                        )
                    else:
                        print(f"Warning: No length found for link {link}")
                else:
                    print(
                        f"Warning: Non-positive travel time for vehicle {vehicle} on link {link}"
                    )
    df = pd.DataFrame(results)
    return df


def compute_travel_time(df):
    """
    Takes output of compute speeds and determines how long the total trip took
    """
    ini_time = df["entry_time"].iloc[0]
    fin_time = df["exit_time"].iloc[-1]
    return float(fin_time - ini_time) / 60


def plot_speeds(results, vehicle_id, start_time=None, end_time=None):
    """Plot speed profile of given vehicle id"""
    # Ensure the vehicle_id is a string (depending on how they are stored)
    vehicle_id = str(vehicle_id)

    # Filter the results for the specified vehicle.
    vehicle_data = [r for r in results if r["vehicle"] == vehicle_id]

    if not vehicle_data:
        print(f"No speed data found for vehicle {vehicle_id}.")
        return

    # Sort vehicle data by entry time
    vehicle_data.sort(key=lambda x: x["entry_time"])

    # Filter data based on the time window
    filtered_data = [
        r
        for r in vehicle_data
        if (start_time is None or r["entry_time"] >= start_time)
        and (end_time is None or r["exit_time"] <= end_time)
    ]

    if not filtered_data:
        print(f"No data found for vehicle {vehicle_id} in the specified time range.")
        return

    # Calculate speed for each time interval,
    # keeping the speed constant until the status changes.
    times = []
    speeds = []
    current_speed = None
    current_time = None

    for r in filtered_data:
        if current_speed is None or r["speed"] != current_speed:
            # If speed changes, record the previous speed and time
            if current_speed is not None:
                times.append(current_time)
                speeds.append(current_speed)
            current_speed = r["speed"]
            current_time = r["entry_time"]
        # Extend the time interval for the current speed
        current_time = r["exit_time"]

    # Append the last speed and time
    if current_speed is not None:
        times.append(current_time)
        speeds.append(current_speed)

    # Create the plot
    plt.figure(figsize=(10, 6))
    plt.step(times, speeds, where="post", label="Speed")

    plt.xlabel("Time (s)")
    plt.ylabel("Speed (m/s)")
    plt.title(f"Speed Profile for Vehicle ID: {vehicle_id}")
    plt.legend()
    plt.grid(True)
    plt.show()
