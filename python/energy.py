'''
Module containing functions to calculate energy consumption of bus route
based on speed profiles.

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


Module containing functions to calculate energy consumption of bus route
based on speed profiles.
'''

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
    grade_col: None = None,            # optional: sin(θ) or %/100
    a_accel_mps2: float = 2.1,         # assumed acceleration [m/s²]
    a_decel_mps2: float = 2.8          # assumed deceleration magnitude [m/s²]
) -> float:
    """
    Estimate traction-battery energy (kWh) for one run.

    The DataFrame should already be sorted chronologically
    (e.g. by 'entry_time'); each row represents one link with
    (approximately) constant speed.

    Speed changes between links are treated as finite acceleration /
    deceleration phases with fixed rates:
      - +a_accel_mps2 when speed increases
      - -a_decel_mps2 when speed decreases

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

        # 1. Constant-speed resistive forces along the link
        F_aero  = 0.5 * rho_air * C_d * frontal_area_m2 * v**2
        F_roll  = mass_kg * g * C_rr
        F_grade = 0.0
        if grade_col is not None:
            # grade_col should contain sin(θ) or gradient/100
            F_grade = mass_kg * g * float(row[grade_col])

        F_total_resist = F_aero + F_roll + F_grade

        # Electrical work to overcome resistances at (approximately) constant speed
        E_resist = F_total_resist * v * dt / eta_traction
        E_J += E_resist

        # 2. Speed-change event between previous and current link
        dv = v - v_prev
        if abs(dv) > 1e-6:  # ignore tiny numerical noise
            # Kinetic energy change (always correct, independent of acceleration rate)
            delta_E_kin = 0.5 * mass_kg * (v**2 - v_prev**2)

            # We approximate the acceleration / deceleration as a phase
            # with constant |a| and linearly changing speed from v_prev to v.
            v_mean = 0.5 * (v + v_prev)

            # Resistive forces during the accel/decel phase, evaluated at mean speed
            F_aero_phase  = 0.5 * rho_air * C_d * frontal_area_m2 * v_mean**2
            F_roll_phase  = mass_kg * g * C_rr
            F_grade_phase = 0.0
            if grade_col is not None:
                F_grade_phase = mass_kg * g * float(row[grade_col])

            F_resist_phase = F_aero_phase + F_roll_phase + F_grade_phase

            if dv > 0:
                # --- Acceleration phase ---
                # a > 0, dv > 0 => t_acc > 0
                t_acc = dv / a_accel_mps2
                # Work that traction must do:
                #   = increase in kinetic energy + resistive work during accel
                W_resist_acc = F_resist_phase * v_mean * t_acc
                E_trac_acc = (delta_E_kin + W_resist_acc) / eta_traction
                E_J += E_trac_acc

            else:
                # --- Deceleration phase ---
                # dv < 0, deceleration magnitude a_decel_mps2 > 0
                # t_dec > 0
                t_dec = -dv / a_decel_mps2

                # Energy lost from kinetic energy (positive scalar)
                E_dissipated = -delta_E_kin

                # Part of this loss is due to resistive forces while decelerating
                W_resist_dec = F_resist_phase * v_mean * t_dec

                # Remaining part must be removed by brakes (which may be regen)
                # If resistive forces alone are enough, no braking/regen is needed.
                W_brake = max(E_dissipated - W_resist_dec, 0.0)

                # Regen recovers a fraction of braking energy
                E_regen = W_brake * eta_regen

                # Regen reduces net energy drawn from battery
                E_J -= E_regen

        v_prev = v

    energy_consumption = E_J / 3.6e6  # Convert joules to kWh (1 kWh = 3.6 MJ)
    return energy_consumption
