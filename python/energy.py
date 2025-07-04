"""
Module containing functions to calculate energy consumption of bus route
based on speed profiles.
"""

import pandas as pd


def calculate_energy_consumption(speed_profile: pd.DataFrame):
    """
    Takes a Dataframe containing the speed profile of a given bus route
    and outputs the energy consumed along the route.

    Parameters:
        speed_profile (DataFrame): Output of speed_access.compute_speeds()
        which is a DataFrame with a row for every link in the route,
        along with the ff_velocity, s&g_velocity, and the FF/s&g ratio.

    Returns:
        energy_consumption (Float): Energy in Kilojoules used from the
        given speed profile.
    """

    # Calculate energy consumption here
    energy_consumption = 5
    return energy_consumption
