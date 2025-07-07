"""
Module containing functions to calculate energy consumption of bus route
based on speed profiles.
"""

import pandas as pd

def calculate_energy_consumption(
    speed_profile: pd.DataFrame,
    *,
    speed_col: str = "speed",          # m s-¹
    time_col: str = "travel_time",     # s
    mass_kg: float = 15_500,           # vehicle + pax
    C_d: float = 0.70,                 # drag coefficient
    frontal_area_m2: float = 9.0,      # m²
    C_rr: float = 0.008,               # rolling-resistance coeff.
    rho_air: float = 1.225,            # kg m-³
    eta_traction: float = 0.90,        # drivetrain efficiency (motoring)
    eta_regen: float = 0.40,           # regen efficiency (braking)
    g: float = 9.81,                   # m s-²
    grade_col: None = None       # optional: sin(θ) or %/100
) -> float:
    """
    Estimate traction-battery energy (kWh) for one run.

    The DataFrame should already be sorted chronologically
    (e.g. by 'entry_time'); each row represents one link.

    Returns
    -------
    float
        Net electrical energy drawn from the battery [kWh].
    """
    # Cumulative work in joules
    E_J = 0.0
    v_prev = 0.0   # speed leaving the previous link (m s-¹)

    for _, row in speed_profile.iterrows():
        v = float(row[speed_col])           # m s-¹
        dt = float(row[time_col])           # s

        # 1. Constant-speed resistive forces
        F_aero  = 0.5 * rho_air * C_d * frontal_area_m2 * v**2
        F_roll  = mass_kg * g * C_rr
        F_grade = 0.0
        if grade_col is not None:
            # grade_col should contain sin(θ) or gradient/100
            F_grade = mass_kg * g * float(row[grade_col])

        F_total_resist = F_aero + F_roll + F_grade

        # Electrical work to overcome resistances
        E_resist = F_total_resist * v * dt / eta_traction
        E_J += E_resist

        # 2. Kinetic-energy change between links
        ΔE_kin = 0.5 * mass_kg * (v**2 - v_prev**2)
        if ΔE_kin >= 0:                      # acceleration (traction)
            E_J += ΔE_kin / eta_traction
        else:                               # deceleration (regen)
            E_J += ΔE_kin * eta_regen       # note ΔE_kin is negative

        v_prev = v

    energy_consumption = E_J / 3.6e6  # Convert joules to kWh (1 kWh = 3.6 MJ)
    #energy_consumption = 5
    return  energy_consumption
