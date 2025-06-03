"""contains functions that manipulate transitSchedule.xml"""


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
                if len(veh_id)>=2:
                    break
            break
    return veh_id