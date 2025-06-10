"""contains functions that manipulate transitSchedule.xml"""

import pandas as pd


def get_bus_ids(schedule, line):
    """
    Finds vehicle id for each route direction for a given line

    inputs:
        schedule (xml tree): transit schedule
        line (string): name of the line to be analyzed

    Returns:
        set: 2 vehicle IDs representing each route direction
    """
    root = schedule.getroot()
    # Finds correct transit line element.
    veh_id = set()
    for transit_line in root.findall(".//transitLine"):
        if transit_line.get("name") == line:
            # Iterate over transit routes to get 2 routes in different directions.
            route_descs = set()
            for transitRoute in transit_line.findall("transitRoute"):
                # Current theory is routeIDs ending in '20233010multint' are valid
                if "20233010multint" in transitRoute.get("id"):
                    description = transitRoute.find("description").text
                    if description not in route_descs:
                        route_descs.add(description)
                        veh_id.add(
                            transitRoute.find("departures")
                            .find("departure")
                            .get("vehicleRefId")
                        )
                if len(veh_id) >= 2:
                    break
            break
    return veh_id


def parse_transit_departures(departures: pd.DataFrame, line_filter=None):  # WIP input
    """
    reads transit departures files and outputs the shapes and lines to be used for busid

    input:
        transit departure file.
        optional: list containing line_ids to filter. Any line IDs not in list will be
        dropped.
    output:
        line_dict - line_id:(route_shape_id1, route_shapeid2).
    """
    # Parse departure file, for each line_id extract the shape_id with the most
    # departure times for inbound and outbound.
    # Create set containing shape_ids, assign set to dict with key= line_id.
    line_dict = {}
    if line_filter:
        lines = line_filter
    else:
        lines = departures["Line ID"].unique().tolist
    for line in lines:
        line_departures = departures.loc[departures["Line ID"] == line].copy()
        line_departures["Departure List"] = line_departures[
            "Unique Departure Times (HH:mm)"
        ].apply(
            lambda x: [time.strip() for time in x.split(",")] if pd.notna(x) else []
        )
        line_departures['Num Departures'] = line_departures['Departure List'].apply(len)
        outbound_df = line_departures[line_departures['Direction'] == 'Outbound']
        inbound_df = line_departures[line_departures['Direction'] == 'Inbound']
        outbound_shape_id = outbound_df.loc[outbound_df['Num Departures'].idxmax(), 'Shape ID']
        inbound_shape_id = inbound_df.loc[inbound_df['Num Departures'].idxmax(), 'Shape ID']
        line_dict[line] = (inbound_shape_id, outbound_shape_id)
    return line_dict
