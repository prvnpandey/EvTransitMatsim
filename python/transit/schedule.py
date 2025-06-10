"""contains functions that manipulate transitSchedule.xml"""

import pandas as pd


def get_bus_ids(schedule, line, shape):
    """
    Finds vehicle id for each departure for a given line and shape id set

    inputs:
        schedule (xml tree): transit schedule
        line (string): name of the line to be analyzed
        shape (set): contains inbound and outbound direction shape
    Returns:
        set of dict:
            vehicle time and id for each departure for inbound and outbound direction
    """
    root = schedule.getroot()
    # Finds correct transit line element.
    inbound_dict = {}
    outbound_dict = {}
    for transit_line in root.findall(".//transitLine"):
        line_name = transit_line.get("id")
        if line_name == line:
            # Iterate over transit routes to get 2 routes in different directions.
            for transitRoute in transit_line.findall("transitRoute"):
                # Current theory is routeIDs ending in '20233010multint' are valid
                if transitRoute.find("description").text[8:] == shape[0]:
                    for departure in transitRoute.find("departures").findall(
                        "departure"
                    ):
                        veh_id = departure.get("vehicleRefId")
                        veh_time = departure.get("departureTime")
                        inbound_dict[veh_time] = veh_id
                elif transitRoute.find("description").text[8:] == shape[1]:
                    for departure in transitRoute.find("departures").findall(
                        "departure"
                    ):
                        veh_id = departure.get("vehicleRefId")
                        veh_time = departure.get("departureTime")
                        outbound_dict[veh_time] = veh_id
            break
    return (inbound_dict, outbound_dict)


def parse_transit_departures(departures: pd.DataFrame, line_filter=None):  # WIP input
    """
    reads transit departures files and outputs the shapes and lines to be used for busid

    input:
        transit departure file.
        optional: list containing line_ids to filter. Any line IDs not in list will be
        dropped.
    output:
        line_dict - line_id:(inbound_route_shape_id, outbound_route_shape_id).
    """

    line_dict = {}
    departures = departures[departures["Direction"] != "Unknown"]
    if line_filter:
        lines = line_filter
    else:
        lines = departures["Line ID"].unique().tolist()
    for line in lines:
        line_departures = departures.loc[departures["Line ID"] == line].copy()
        line_departures["Departure List"] = line_departures[
            "Unique Departure Times (HH:mm)"
        ].apply(
            lambda x: [time.strip() for time in x.split(",")] if pd.notna(x) else []
        )
        line_departures["Num Departures"] = line_departures["Departure List"].apply(len)
        outbound_df = line_departures[line_departures["Direction"] == "Outbound"]
        inbound_df = line_departures[line_departures["Direction"] == "Inbound"]
        if outbound_df.empty or inbound_df.empty:
            break
        outbound_shape_id = outbound_df.loc[
            outbound_df["Num Departures"].idxmax(), "Shape ID"
        ]
        inbound_shape_id = inbound_df.loc[
            inbound_df["Num Departures"].idxmax(), "Shape ID"
        ]
        line_dict[line] = (inbound_shape_id, outbound_shape_id)
    return line_dict
