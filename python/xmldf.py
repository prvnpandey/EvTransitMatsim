'''contains function for reading a network.xml.gz file and outputing a pandas df'''

import gzip
import xml.etree.ElementTree as ET

import pandas as pd


def network_to_df(network_file: gzip.GzipFile):
    """reads network xml file and returns a df containing the links of the network"""
    tree = ET.parse(network_file)
    root = tree.getroot()

    # Create a list to store the link data
    links_data = []

    # Iterate over the <link> elements in the XML
    for link in root.findall(".//link"):
        link_id = link.get("id")
        from_node = link.get("from")
        to_node = link.get("to")
        length = link.get("length")
        freespeed = link.get("freespeed")
        capacity = link.get("capacity")
        permlanes = link.get("permlanes")
        oneway = link.get("oneway")
        modes = link.get("modes")

        link_type = None

        # <attribute name="osm:way:highway"> contains link type
        for attr in link.findall("./attributes/attribute"):
            if attr.get("name") == "osm:way:highway":
                link_type = attr.text
                break

        # Add the link data to the list
        links_data.append(
            {
                "link_id": link_id,
                "from": from_node,
                "to": to_node,
                "length": length,
                "freespeed": freespeed,
                "capacity": capacity,
                "permlanes": permlanes,
                "oneway": oneway,
                "modes": modes,
                "link_type":link_type,
            }
        )

    # Create a pandas DataFrame with the data
    df = pd.DataFrame(links_data)

    # Split the 'modes' column into binary columns
    modes_dummies = df["modes"].str.get_dummies(sep=",")

    # Combine the binary columns with the original DataFrame
    df = pd.concat([df, modes_dummies], axis=1)
    df.set_index('link_id', inplace=True)
    return df

def transit_schedule_to_df():
    '''reads the output_TransitSchedule.xml and outputs a df'''
    # Current theory is routeIDs ending in '20233010multint' are valid
    

