import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import matplotlib.pyplot as plt
import pyomo.environ as pyo
import math
import numpy as np
import seaborn as sns

def optimization(
    trip_start: list[int],          # timestep index when each trip begins  (len = I)
    trip_end:   list[int],          # timestep index when each trip ends    (len = I)
    alpha:      list[float],        # maximum power rating of each charger  (len = N)
    gamma:      list[float],        # energy consumption rate per trip      (len = I)
    C_bat:      list[float],        # battery capacity of each vehicle      (len = K)
    P:          list[float],        # electricity price at each timestep    (len = T)
    E_0:        float = 0.20,       # initial state of charge as fraction   [0,1]
    E_min:      float = 0.20,       # minimum allowed SOC as fraction       [0,1]
    E_max:      float = 1.00,       # maximum allowed SOC as fraction       [0,1]
    E_end:      float = 0.20,       # required final SOC as fraction        [0,1]
    delta_t:    float = 0.25,       # timestep duration in hours           (e.g. 0.25 = 15min)
    relaxed_binary: bool = False,   # if True, use continuous relaxation for binary vars
    variable_power: bool = False    # if True, allow variable charging power
):
    """
    Solves the electric bus fleet charging optimization problem.
    
    Creates and returns a Pyomo model that minimizes charging costs while satisfying
    operational constraints for an electric bus fleet. The model determines:
    - Which bus serves which trip
    - When and where each bus charges
    - How much power to draw at each charging event (if variable_power=True)
    
    The optimization ensures sufficient battery levels are maintained while minimizing
    the total cost of electricity purchased from the grid.
    """

    # ── 1. Define the fundamental sets of the problem ──────────────────────────
    I, T, K, N = len(trip_start), (len(P) if len(P) > max(trip_end) else max(trip_end)), len(C_bat), len(alpha)

    m = pyo.ConcreteModel()
    m.I = pyo.RangeSet(1, I)  # Set of trips
    m.T = pyo.RangeSet(1, T)  # Set of timesteps
    m.K = pyo.RangeSet(1, K)  # Set of buses
    m.N = pyo.RangeSet(1, N)  # Set of chargers
    
    print(f"Problem size: {I} trips, {T} timesteps, {K} buses, {N} chargers")
    
    # ── 2. Define all model parameters ────────────────────────────────────────
    # Trip timing and energy parameters    
    m.T_start = pyo.Param(m.I, initialize=lambda _, i: trip_start[i-1])  
    m.T_end   = pyo.Param(m.I, initialize=lambda _, i: trip_end[i-1])    
    m.alpha   = pyo.Param(m.N, initialize=lambda _, n: alpha[n-1])       
    m.gamma   = pyo.Param(m.I, initialize=lambda _, i: gamma[i-1])       

    # Grid and battery parameters
    m.P       = pyo.Param(m.T, initialize=lambda _, t: P[t-1])          
    m.C_bat   = pyo.Param(m.K, initialize=lambda _, k: C_bat[k-1])      

    # System parameters
    m.ch_eff  = pyo.Param(initialize=0.90)    
    m.E_0     = pyo.Param(initialize=E_0)     
    m.E_min   = pyo.Param(initialize=E_min)   
    m.E_max   = pyo.Param(initialize=E_max)   
    m.E_end   = pyo.Param(initialize=E_end)   
    m.delta_t = pyo.Param(initialize=delta_t)  
    
    # ── 3. Define decision variables ──────────────────────────────────────────
    var_domain = pyo.UnitInterval if relaxed_binary else pyo.Binary
    
    # Primary decision variables
    m.b = pyo.Var(m.K, m.I, m.T, within=var_domain)   # Bus assignment to trips
    m.x = pyo.Var(m.K, m.N, m.T, within=var_domain)   # Bus assignment to chargers
    
    if variable_power:
        m.p = pyo.Var(m.K, m.N, m.T, within=pyo.NonNegativeReals)  # Variable charging power
    
    # State and auxiliary variables
    m.e = pyo.Var(m.K, m.T, within=pyo.NonNegativeReals)      # Battery energy levels
    m.w_buy = pyo.Var(m.T, within=pyo.NonNegativeReals)       # Grid power purchase
    
    # ── 4. Define objective function ─────────────────────────────────────────
    m.obj = pyo.Objective(
        expr=sum(m.P[t] * m.w_buy[t] for t in m.T),  
        sense=pyo.minimize
    )
    
    # ── 5. Define operational constraints ───────────────────────────────────
    cons = m.constraints = pyo.ConstraintList()

    # 5.1-5.4 remain unchanged...
    for k in m.K:
        for t in m.T:
            drive  = sum(m.b[k, i, t] for i in m.I)   
            charge = sum(m.x[k, n, t] for n in m.N)   
            cons.add(drive + charge <= 1)             

    for n in m.N:
        for t in m.T:
            cons.add(sum(m.x[k, n, t] for k in m.K) <= 1)

    for i in m.I:
        for t in range(m.T_start[i], m.T_end[i]):
            cons.add(sum(m.b[k, i, t] for k in m.K) == 1)
        
        for t in range(1,m.T_start[i]):
            cons.add(sum(m.b[k,i,t] for k in m.K) == 0)

        for t in range(m.T_end[i],T+1):
            cons.add(sum(m.b[k,i,t] for k in m.K) == 0)

    for i in m.I:
        for k in m.K:
            for t in range(m.T_start[i], m.T_end[i] - 1):
                cons.add(m.b[k, i, t+1] >= m.b[k, i, t])

    # 5.5 Charging power constraints - modified based on variable_power
    for k in m.K:
        for n in m.N:
            for t in m.T:
                if variable_power:
                    cons.add(m.p[k,n,t] <= m.x[k,n,t] * m.alpha[n])  
                    cons.add(m.p[k,n,t] >= 0)  

    # 5.6 Battery energy evolution - modified based on variable_power
    for k in m.K:
        cons.add(m.e[k, 1] == m.E_0 * m.C_bat[k])
    
        for t in range(2, T+1):
            if variable_power:
                charge_in = sum(m.delta_t * m.ch_eff * m.p[k,n,t] for n in m.N)
            else:
                charge_in = sum(m.delta_t * m.ch_eff * m.alpha[n] * m.x[k,n,t] for n in m.N)
            drive_out = sum(m.gamma[i] * m.b[k,i,t] for i in m.I)
            cons.add(m.e[k,t] == m.e[k,t-1] + charge_in - drive_out)

    # 5.7 Grid power balance - modified based on variable_power
    for t in m.T:
        if variable_power:
            total_ch = sum(m.delta_t * m.ch_eff * m.p[k,n,t] for k in m.K for n in m.N)
        else:
            total_ch = sum(m.delta_t * m.ch_eff * m.alpha[n] * m.x[k,n,t] for k in m.K for n in m.N)
        cons.add(total_ch == m.w_buy[t])

    # 5.8, 5.9 remain unchanged...
    for k in m.K:
        for t in m.T:
            cons.add(m.e[k, t] >= m.C_bat[k] * m.E_min)
            cons.add(m.e[k, t] <= m.C_bat[k] * m.E_max)
        
    for k in m.K:
        cons.add(m.e[k, T] >= m.C_bat[k] * m.E_end)
    
    return m

def build_fleet_and_chargers(
        bus_counts:     list[int],     
        battery_sizes:  list[float],   
        charger_counts: list[int],     
        charger_powers: list[float]
) -> tuple[list[float], list[float]]:

    # sanity checks
    if len(bus_counts) != len(battery_sizes):
        raise ValueError("bus_counts and battery_sizes must be the same length.")
    if len(charger_counts) != len(charger_powers):
        raise ValueError("charger_counts and charger_powers must be the same length.")
    if any(n < 0 for n in bus_counts + charger_counts):
        raise ValueError("All counts must be non-negative integers.")

    # expand buses
    C_bat = [
        cap
        for n, cap in zip(bus_counts, battery_sizes)
        for _ in range(n)
    ]

    # expand chargers
    alpha = [
        p
        for n, p in zip(charger_counts, charger_powers)
        for _ in range(n)
    ]

    return C_bat, alpha

def process_transit_data(
    df,
    scheduled_col='Scheduled Travel Time (min)',
    actual_col='Travel Time (min)',
    tolerance=0.15,
    energy_col='Energy Consumption (kWh)',
    dist_col='Distance (m)',
    departure_col='Departure Time',
    timestep_min=15
):
    """
    Runs the full cleaning and feature-engineering pipeline:
    0. Replaces 'no_events' in Travel Time with Scheduled Travel Time.
    1. Filters rows where actual travel time deviates more than ±tolerance from scheduled.
    2. Drops trips with zero energy consumption.
    3. Adds average energy consumption per km.
    4. Computes arrival time from departure + actual travel time.
    5. Discards trips that roll over past midnight.
    6. Maps departure/arrival times to discrete steps of length timestep_min (minutes).
    7. Computes energy per time step.
    
    Returns the processed DataFrame.
    """
    # Step 0: replace 'no_events' entries
    mask_no = df[actual_col] == 'no_events'
    df.loc[mask_no, actual_col] = df.loc[mask_no, scheduled_col]

    # Convert scheduled and actual travel times to numeric
    df[scheduled_col] = pd.to_numeric(df[scheduled_col], errors='coerce')
    df[actual_col]    = pd.to_numeric(df[actual_col], errors='coerce')

    # Step 1: filter by travel-time tolerance
    df = df.dropna(subset=[scheduled_col, actual_col])
    ratio = (df[actual_col] - df[scheduled_col]) / df[scheduled_col]
    df = df[ratio.abs() <= tolerance]

    # Convert energy and distance to numeric, drop NA
    df[energy_col] = pd.to_numeric(df[energy_col], errors='coerce')
    df[dist_col]   = pd.to_numeric(df[dist_col], errors='coerce')
    df = df.dropna(subset=[energy_col, dist_col])

    # Step 2: drop zero-energy trips
    df = df[df[energy_col] != 0]

    # Step 3: average energy consumption (kWh/km)
    df['Avg Energy (kWh/km)'] = df[energy_col] / (df[dist_col] / 1000)

    # Step 4: compute arrival time
    df['Travel Time (min)'] = df[actual_col]  # already numeric
    df['__dep_dt'] = pd.to_datetime(df[departure_col], format='%H:%M:%S', errors='coerce')
    df['Arrival Time'] = (
        df['__dep_dt'] + pd.to_timedelta(df['Travel Time (min)'], unit='m')
    ).dt.strftime('%H:%M:%S')
    df.drop(columns='__dep_dt', inplace=True)

    # Step 5: drop trips ending after midnight
    df['__dep_dt'] = pd.to_datetime(df[departure_col], format='%H:%M:%S', errors='coerce')
    df['__arr_dt'] = pd.to_datetime(df['Arrival Time'], format='%H:%M:%S', errors='coerce')
    df = df[df['__arr_dt'] >= df['__dep_dt']]

    # Step 6: map to timesteps
    max_steps = int(24 * 60 / timestep_min)
    df['__dep_min'] = df['__dep_dt'].dt.hour * 60 + df['__dep_dt'].dt.minute + df['__dep_dt'].dt.second / 60
    df['__arr_min'] = df['__arr_dt'].dt.hour * 60 + df['__arr_dt'].dt.minute + df['__arr_dt'].dt.second / 60
    df['Departure Step'] = df['__dep_min'].apply(lambda m: max(1, min(max_steps, math.floor(m / timestep_min))))
    df['Arrival Step']   = df['__arr_min'].apply(lambda m: max(1, min(max_steps, math.ceil(m / timestep_min))))
    df.drop(columns=['__dep_dt','__arr_dt','__dep_min','__arr_min'], inplace=True)

    # Step 7: energy per time step
    df['Energy per timestep'] = (
        df['Avg Energy (kWh/km)'] * (df[dist_col] / 1000) * (timestep_min / df['Travel Time (min)'])
    )

    return df

def resample_time_series(data, original_delta, target_delta, method='average'):
    """
    Resample a time series by changing its timestep.
    
    Parameters:
    - data: list of numeric values
    - original_delta: float, original timestep in hours (e.g. 1 for 1 h, 0.25 for 15 min)
    - target_delta: float, desired timestep in hours
    - method: 'average' or 'sum' for aggregation on down-sampling
    
    Returns:
    - list of floats at the new timestep resolution
    """
    if target_delta == original_delta:
        return list(data)  # no change
    
    # DOWN-SAMPLING: target coarser than original
    if target_delta > original_delta:
        factor = target_delta / original_delta
        if not factor.is_integer():
            raise ValueError("For down‑sampling, target_delta/original_delta must be integer")
        factor = int(factor)
        
        res = []
        for i in range(0, len(data), factor):
            block = data[i:i+factor]
            if method == 'sum':
                res.append(sum(block))
            elif method == 'average':
                res.append(sum(block) / len(block))
            else:
                raise ValueError("method must be 'average' or 'sum'")
        return res
    
    # UP-SAMPLING: target finer than original
    else:  # target_delta < original_delta
        factor = original_delta / target_delta
        if not factor.is_integer():
            raise ValueError("For up‑sampling, original_delta/target_delta must be integer")
        factor = int(factor)
        
        res = []
        for val in data:
            if method == 'sum':
                # distribute the original sum evenly
                distributed = val * (target_delta / original_delta)
                res.extend([distributed] * factor)
            else:  # 'average'
                # just repeat the same value
                res.extend([val] * factor)
        return res

def plot_optimization_results(
    m,
    vehicle_cost,
    charger_cost,
    implementation_cost,
    peak_power_price,
    years=10,
):
    # Set improved style and font
    plt.rcParams.update({
        "font.size": 12,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10
    })
    sns.set_style("whitegrid")

    K = list(m.K)
    N = list(m.N)
    I = list(m.I)
    T = list(m.T)
    delta_t = float(m.delta_t)

    b     = {(k,i,t): pyo.value(m.b[k,i,t])     for k in K for i in I for t in T}
    x     = {(k,n,t): pyo.value(m.x[k,n,t])     for k in K for n in N for t in T}
    e     = {(k,t):   pyo.value(m.e[k,t])       for k in K for t in T}
    w_buy = {t:       pyo.value(m.w_buy[t])     for t in T}
    price = {t:       pyo.value(m.P[t])         for t in T}

    C_bat_dict = {k: pyo.value(m.C_bat[k])     for k in K}
    alpha_dict = {n: pyo.value(m.alpha[n])     for n in N}

    hours = [t*delta_t for t in T]

    # 1. Charger activity Gantt chart
    fig, ax = plt.subplots(figsize=(12, 5), dpi=300)
    for idx, n in enumerate(N):
        active = [t for t in T if any(x[k, n, t] > 0.5 for k in K)]
        groups = np.split(active, np.where(np.diff(active) != 1)[0] + 1)
        for g in groups:
            if len(g):
                ax.broken_barh(
                    [(g[0]*delta_t, len(g)*delta_t)],
                    (idx-0.4, 0.8),
                    facecolors='tab:orange',
                    edgecolor='black'
                )
    ax.set_yticks(range(len(N)))
    ax.set_yticklabels([f'Charger {n}' for n in N])
    ax.set_xlabel('Hour of day [h]')
    ax.set_xlim(0, 24)
    ax.set_xticks(range(25))
    ax.grid(axis='x', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.show()

    # 2. Fleet & charger utilisation pies
    bus_stats = []
    for k in K:
        active_ts = [t for t in T if any(b[k, i, t] > 0.5 for i in I) or any(x[k, n, t] > 0.5 for n in N)]
        if not active_ts:
            continue
        t0, t1 = min(active_ts), max(active_ts)
        window = [t for t in T if t0 <= t <= t1]
        run_t = sum(delta_t for t in window if any(b[k, i, t] > 0.5 for i in I) and not any(x[k, n, t] > 0.5 for n in N))
        chg_t = sum(delta_t for t in window if any(x[k, n, t] > 0.5 for n in N))
        idle_t = sum(delta_t for t in window if not any(b[k, i, t] > 0.5 for i in I) and not any(x[k, n, t] > 0.5 for n in N))
        total_t = len(window) * delta_t
        bus_stats.append({
            'Driving_pct': 100 * run_t / total_t,
            'Charging_pct': 100 * chg_t / total_t,
            'Idle_pct': 100 * idle_t / total_t
        })
    df_bus = pd.DataFrame(bus_stats)
    fleet_avg = df_bus.mean()

    no_trip = [t for t in T if not any(b[k, i, t] > 0.5 for k in K for i in I)]
    used = sum(1 for t in no_trip if any(x[k, n, t] > 0.5 for k in K for n in N))
    charger_pct = 100 * used / len(no_trip) if no_trip else 0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6), dpi=300)
    # Fleet pie
    ax1.pie(
        [fleet_avg['Driving_pct'], fleet_avg['Charging_pct'], fleet_avg['Idle_pct']],
        labels=['Driving', 'Charging', 'Idle'],
        autopct='%1.1f%%',
        colors=['#4C72B0', '#FFA726', '#BDBDBD'],
        startangle=90,
        wedgeprops={'edgecolor': 'black'}
    )
    # Charger pie
    ax2.pie(
        [charger_pct, 100 - charger_pct],
        labels=['In use', 'Idle'],
        autopct='%1.1f%%',
        colors=['#1976D2', '#BDBDBD'],
        startangle=90,
        wedgeprops={'edgecolor': 'black'}
    )
    plt.tight_layout()
    plt.show()

    # 3. Fleet average SOC over time (continuous line)
    avg_soc = [
        sum(e[k, t] / C_bat_dict[k] for k in K) / len(K)
        for t in T
    ]
    plt.figure(figsize=(10, 4), dpi=300)
    plt.plot(hours, avg_soc, color='#388E3C', linewidth=2, label='Average SOC')
    plt.fill_between(hours, avg_soc, color='#388E3C', alpha=0.15)
    plt.xlabel('Hour of day [h]', fontsize=10)
    plt.ylabel('Average SOC (fraction)', fontsize=10)
    plt.xlim(0, 24)
    plt.ylim(0, 1)
    plt.xticks(range(25))
    plt.yticks(np.linspace(0, 1, 11))
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend(loc='upper right', frameon=True)
    plt.tight_layout()
    plt.show()

    # 4. Charging power vs. energy price (improved)
    power_curve = [
        sum(alpha_dict[n] * x[k, n, t] for k in K for n in N)
        for t in T
    ]
    price_curve = [price[t] for t in T]

    fig, ax1 = plt.subplots(figsize=(12, 5), dpi=300)

    # Charging power area plot
    ax1.fill_between(hours, power_curve, color="#1D86D6", alpha=0.25, label='Charging Power (kW)')
    ax1.plot(hours, power_curve, color="#0574C8", linewidth=2)
    ax1.set_xlabel('Hour of day [h]', fontsize=10)
    ax1.set_ylabel('Charging Power (kW)', color="#000000", fontsize=10)
    ax1.tick_params(axis='y', labelcolor="#000000")
    ax1.set_xlim(0, 24)
    ax1.set_xticks(range(25))
    ax1.grid(axis='x', linestyle='--', alpha=0.5)

    # Energy price line plot
    ax2 = ax1.twinx()
    ax2.plot(hours, price_curve, color="#E46161", linestyle='--', linewidth=2, label='Energy Price (CAD$/kWh)')
    ax2.set_ylabel('Energy Price (CAD$/kWh)', color="#000000", fontsize=1)
    ax2.tick_params(axis='y', labelcolor="#000000")

    # Legends
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax2.legend(lines_1 + lines_2, labels_1 + labels_2, loc='best', frameon=True)

    plt.tight_layout()
    plt.show()

    #combining SOC and Power
    # Compute average SOC (unchanged)
    avg_soc = [
        sum(e[k, t] / C_bat_dict[k] for k in K) / len(K)
        for t in T
    ]

    # Compute charging power curve
    power_curve = [
        sum(alpha_dict[n] * x[k, n, t] for k in K for n in N)
        for t in T
    ]
    price_curve = [price[t] for t in T]   # not used in this plot now

    # --- Combined figure: SOC + Charging Power ---
    fig, ax1 = plt.subplots(figsize=(12, 5), dpi=300)

    # ---- Left axis: Average SOC ----
    ax1.plot(hours, avg_soc, color='#388E3C', linewidth=2, label='Average SOC')
    ax1.fill_between(hours, avg_soc, color='#388E3C', alpha=0.15)

    ax1.set_xlabel('Hour of day [h]', fontsize=10)
    ax1.set_ylabel('Average SOC (fraction)', fontsize=10)
    ax1.set_xlim(0, 24)
    ax1.set_ylim(0, 1)
    ax1.set_xticks(range(25))
    ax1.set_yticks(np.linspace(0, 1, 11))
    ax1.grid(axis='y', linestyle='--', alpha=0.7)

    # ---- Right axis: Charging Power ----
    ax2 = ax1.twinx()
    ax2.plot(hours, power_curve, linestyle='--', linewidth=2,
            color='tab:blue', label='Charging Power')
    ax2.set_ylabel('Charging Power [kW]', fontsize=10)

    # ---- Combined legend ----
    lines = ax1.get_lines() + ax2.get_lines()
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper right', frameon=True)

    plt.tight_layout()
    plt.show()

    # ── 5. Total cost of ownership ────────────────────────────────────────────
    # Compute CAPEX breakdown
    fleet_capex   = len(K) * vehicle_cost
    charger_capex = len(N) * charger_cost
    implementation_capex = len(N) * implementation_cost 
    capex_total   = fleet_capex + charger_capex + implementation_capex

    # OPEX breakdown (objective is daily cost)
    daily_op_cost   = pyo.value(m.obj)
    energy_10yr     = daily_op_cost * 365 * years
    peak_power      = max(power_curve)                # reuse power_curve
    peak_10yr       = peak_power * peak_power_price * 365 * years
    opex_total_10yr = energy_10yr + peak_10yr

    # Total TCO
    tco_total = capex_total + opex_total_10yr

    # Prepare labels and values
    labels = [
        'Fleet costs',
        'Charger costs',
        'Charger implementation costs',
        'Energy costs',
        'Power peak costs',
        'TCO'
    ]
    parts = [fleet_capex, charger_capex, implementation_capex, energy_10yr, peak_10yr]
    colors = ['#4C72B0', "#1DBA41", "#ABABAB",'#C44E52', '#8172B2']

    # Plot individual bars and stacked TCO
    fig, ax = plt.subplots(figsize=(10,5), dpi=300)
    for lbl, val, col in zip(labels[:-1], parts, colors):
        ax.bar(lbl, val, color=col, edgecolor='black')

    # Stacked TCO bar
    ax.bar('TCO', capex_total,      color="#6E3E86", edgecolor='black')
    ax.bar('TCO', opex_total_10yr,  bottom=capex_total,
           color='#BA901D', edgecolor='black')

    # Centralize brackets and move annotations further left to avoid covering bars
    x_pos = labels.index('TCO')
    bracket_x = x_pos - 0.05  # closer to center of bar
    text_x = x_pos - 0.6      # further left for annotation

    # Annotate CAPEX segment on TCO bar (centralized, smaller font, thinner bracket)
    ax.annotate(
        '',
        xy=(bracket_x,   capex_total),
        xytext=(bracket_x, 0),
        arrowprops=dict(arrowstyle='|-|', lw=1, color='black'),
        annotation_clip=False
    )
    ax.text(
        text_x, capex_total/2,
        f'CAPEX\n{capex_total:,.0f} CAD$\n({capex_total/tco_total*100:.1f} %)',
        va='center', ha='right', fontsize=12, fontweight='bold'
    )

    # Annotate OPEX segment on TCO bar (centralized, smaller font, thinner bracket)
    ax.annotate(
        '',
        xy=(bracket_x,   capex_total + opex_total_10yr),
        xytext=(bracket_x, capex_total),
        arrowprops=dict(arrowstyle='|-|', lw=1, color='black'),
        annotation_clip=False
    )
    ax.text(
        text_x, capex_total + opex_total_10yr/2,
        f'OPEX\n{opex_total_10yr:,.0f} CAD$\n({opex_total_10yr/tco_total*100:.1f} %)',
        va='center', ha='right', fontsize=12, fontweight='bold'
    )

    ax.set_ylabel('Cost (CAD$)', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.show()

    # ── 6. Heatmap of SOC (energy level) for each bus ─────────────────────────────
    soc_matrix = np.array([
        [pyo.value(m.e[k, t]) / pyo.value(m.C_bat[k]) for t in m.T]
        for k in m.K
    ])
    fig, ax = plt.subplots(figsize=(14, max(4, len(m.K)*0.4)), dpi=300)
    im = ax.imshow(soc_matrix, aspect='auto', cmap='viridis', vmin=0, vmax=1)
    ax.set_xlabel('Time step')
    ax.set_ylabel('Bus')
    ax.set_yticks(np.arange(len(m.K)))
    ax.set_yticklabels([f'Bus {k}' for k in m.K])
    ax.set_xticks(np.linspace(0, len(m.T)-1, 9, dtype=int))
    ax.set_xticklabels([f'{int(t*pyo.value(m.delta_t)):02d}:00' for t in np.linspace(0, len(m.T)-1, 9, dtype=int)])
    cbar = fig.colorbar(im, ax=ax, label='SOC (fraction)')
    plt.tight_layout()
    plt.show()

def export_optimization_summary(
    m,
    vehicle_cost,
    charger_cost,
    implementation_cost,
    peak_power_price,
    years=10,
    filename='optimization_results_summary.xlsx'
):
    """
    Export summary tables from the optimization model to an Excel workbook with multiple sheets:
      - ChargerActivity: number of active timesteps per hour per charger
      - FleetUtilisation: total hours and percentages for Driving/Charging/Idle
      - ChargerUtilisation: total timesteps and percentages for In Use/Idle
      - FleetEnergy: total fleet energy (kWh) per hour
      - TCO: CAPEX, OPEX and Total Cost
      - EnergyHeatmap: SOC (fraction) for each vehicle and timestep
    """
    import pandas as pd
    import numpy as np

    # Extract sets and parameters
    K = list(m.K)
    N = list(m.N)
    I = list(m.I)
    T = list(m.T)
    delta_t = float(m.delta_t)

    # Extract variable values
    x = {(k, n, t): pyo.value(m.x[k, n, t]) for k in K for n in N for t in T}
    b = {(k, i, t): pyo.value(m.b[k, i, t]) for k in K for i in I for t in T}
    e = {(k, t): pyo.value(m.e[k, t]) for k in K for t in T}
    w_buy = {t: pyo.value(m.w_buy[t]) for t in T}
    price = {t: pyo.value(m.P[t]) for t in T}
    C_bat_dict = {k: pyo.value(m.C_bat[k]) for k in K}
    alpha_dict = {n: pyo.value(m.alpha[n]) for n in N}

    hours = list(range(24))

    # 1. ChargerActivity: count of active timesteps per hour per charger
    charger_activity = pd.DataFrame(0, index=[f'Charger {n}' for n in N], columns=hours)
    for n in N:
        for t in T:
            hour = int((t-1) * delta_t)
            if any(x[k, n, t] > 0.5 for k in K):
                charger_activity.at[f'Charger {n}', hour] += 1

    # 2. FleetUtilisation
    drive_time = charge_time = idle_time = 0
    for k in K:
        for t in T:
            if any(x[k, n, t] > 0.5 for n in N):
                charge_time += delta_t
            else:
                # detect driving by SOC drop
                if t < T[-1] and e[k, t+1] < e[k, t]:
                    drive_time += delta_t
                else:
                    idle_time += delta_t
    total_time = drive_time + charge_time + idle_time
    fleet_util = pd.DataFrame({
        'Activity': ['Driving', 'Charging', 'Idle'],
        'Hours': [drive_time, charge_time, idle_time],
    })
    fleet_util['Percentage'] = fleet_util['Hours'] / total_time * 100

    # 3. ChargerUtilisation
    total_slots = len(N) * len(T)
    used_slots = sum(1 for n in N for t in T if any(x[k, n, t] > 0.5 for k in K))
    idle_slots = total_slots - used_slots
    charger_util = pd.DataFrame({
        'State': ['In Use', 'Idle'],
        'Slots': [used_slots, idle_slots],
    })
    charger_util['Percentage'] = charger_util['Slots'] / total_slots * 100

    # 4. FleetEnergy per hour
    total_e = []
    for h in hours:
        e_sum = sum(e[k, t] for k in K for t in T if int((t-1) * delta_t) == h)
        total_e.append(e_sum)
    fleet_energy = pd.DataFrame({'Hour': hours, 'TotalEnergy_kWh': total_e})

    # 5. TCO
    fleet_capex   = len(K) * vehicle_cost
    charger_capex = len(N) * charger_cost
    implementation_capex = len(N) * implementation_cost
    capex_total   = fleet_capex + charger_capex + implementation_capex
    daily_op_cost = pyo.value(m.obj)
    power_curve = [
        sum(alpha_dict[n] * x[k, n, t] for k in K for n in N)
        for t in T
    ]
    peak_power = max(power_curve)
    peak_10yr = peak_power * peak_power_price * 365 * years
    energy_10yr = daily_op_cost * 365 * years
    opex_total_10yr = energy_10yr + peak_10yr
    tco_total = capex_total + opex_total_10yr
    df_tco = pd.DataFrame({
        'Component': ['Fleet CAPEX', 'Charger CAPEX', 'Implementation', 'Energy (10yr)', 'Peak (10yr)', 'Total TCO'],
        'Cost_EUR': [fleet_capex, charger_capex, implementation_capex, energy_10yr, peak_10yr, tco_total]
    })

    # 6. EnergyHeatmap: SOC (fraction) for each vehicle and timestep
    soc_matrix = pd.DataFrame(
        [[e[k, t] / C_bat_dict[k] for t in T] for k in K],
        index=[f'Bus {k}' for k in K],
        columns=[f'TS {t}' for t in T]
    )

    # Write to Excel
    with pd.ExcelWriter(filename) as writer:
        charger_activity.to_excel(writer, sheet_name='ChargerActivity')
        fleet_util.to_excel(writer, sheet_name='FleetUtilisation', index=False)
        charger_util.to_excel(writer, sheet_name='ChargerUtilisation', index=False)
        fleet_energy.to_excel(writer, sheet_name='FleetEnergy', index=False)
        df_tco.to_excel(writer, sheet_name='TCO', index=False)
        soc_matrix.to_excel(writer, sheet_name='EnergyHeatmap')

    print(f"Summary exported to {filename}")

def analyze_fleet_metrics(model):
    """Return a dict of key operational metrics from a solved Pyomo model."""
    T = list(model.T)
    dt = float(pyo.value(model.delta_t))

    # Fleet & infra sizes
    num_buses    = len(model.K)
    num_chargers = len(model.N)

    # Energy (kWh) and power (kW)
    w_buy = {t: float(pyo.value(model.w_buy[t])) for t in T}
    total_energy_kwh = sum(w_buy[t] * dt for t in T)
    avg_energy_per_vehicle_kwh = total_energy_kwh / num_buses if num_buses else 0.0

    power_by_timestep = [w_buy[t] for t in T]
    peak_power_kw = float(np.max(power_by_timestep)) if power_by_timestep else 0.0
    avg_power_kw  = float(np.mean(power_by_timestep)) if power_by_timestep else 0.0

    # Charger utilization
    chargers_used_ts = []
    for t in T:
        used = sum(1 for k in model.K for n in model.N if pyo.value(model.x[k, n, t]) > 0.5)
        chargers_used_ts.append(used)
    max_sim_chargers = int(np.max(chargers_used_ts)) if chargers_used_ts else 0
    avg_chargers_used = float(np.mean(chargers_used_ts)) if chargers_used_ts else 0.0

    # Costs (daily energy only; demand charge handled in exporter)
    price = {t: float(pyo.value(model.P[t])) for t in T}
    daily_energy_cost = sum(w_buy[t] * price[t] * dt for t in T)
    energy_cost_per_vehicle = daily_energy_cost / num_buses if num_buses else 0.0

    # Trips per vehicle (optional)
    trips_by_vehicle = []
    for k in model.K:
        num_trips = sum(1 for i in model.I for t in model.T if pyo.value(model.b[k, i, t]) > 0.5)
        trips_by_vehicle.append(num_trips)
    avg_trips_per_vehicle = float(np.mean(trips_by_vehicle)) if trips_by_vehicle else 0.0
    max_trips_per_vehicle = int(np.max(trips_by_vehicle)) if trips_by_vehicle else 0

    return {
        "Total Fleet Size [buses]": num_buses,
        "Number of Chargers [-]": num_chargers,
        "Total Energy [kWh]": total_energy_kwh,
        "Avg Energy / Vehicle [kWh]": avg_energy_per_vehicle_kwh,
        "Peak Power [kW]": peak_power_kw,
        "Average Power [kW]": avg_power_kw,
        "Max Simultaneous Chargers [-]": max_sim_chargers,
        "Avg Chargers Used [-]": avg_chargers_used,
        "Daily Energy Cost [€]": daily_energy_cost,
        "Energy Cost / Vehicle [€]": energy_cost_per_vehicle,
        "Avg Trips / Vehicle [-]": avg_trips_per_vehicle,
        "Max Trips / Vehicle [-]": max_trips_per_vehicle,
    }

def export_all_to_excel(
    m,
    *,
    vehicle_unit_cost,            # € per bus
    charger_unit_cost,            # € per charger
    implementation_unit_cost,     # € per charger (installation/site)
    peak_power_price_per_kw_day,  # € per kW per day (demand charge)
    years_for_reference=10,       # used to compute 10-yr energy/peak if needed
    filename="optimization_full_summary.xlsx"
):
    """
    One-stop export:
      Sheets:
        - Metrics
        - Costs_CAPEX
        - Costs_OPEX_Daily
        - AvgSOC
        - PowerAndPrice
        - ChargerActivity
        - ChargerGantt
        - FleetUtilisationByBus
        - FleetUtilisationFleetAvg
        - ChargerUtilisation
        - FleetEnergy
        - EnergyHeatmap
    """
    # ---------- Extract sets/params ----------
    K = list(m.K); N = list(m.N); I = list(m.I); T = list(m.T)
    delta_t = float(pyo.value(m.delta_t))

    # ---------- Extract variable values ----------
    b = {(k,i,t): pyo.value(m.b[k,i,t]) for k in K for i in I for t in T}
    x = {(k,n,t): pyo.value(m.x[k,n,t]) for k in K for n in N for t in T}
    e = {(k,t):   pyo.value(m.e[k,t])   for k in K for t in T}
    w_buy = {t:   pyo.value(m.w_buy[t]) for t in T}
    price = {t:   pyo.value(m.P[t])     for t in T}
    C_bat = {k:   pyo.value(m.C_bat[k]) for k in K}
    alpha  = {n:  pyo.value(m.alpha[n]) for n in N}

    hours = [int(round((t-1)*delta_t)) for t in T]  # 0..24 mapping

    # ---------- (A) Plot datasets ----------
    # A1) ChargerActivity
    charger_activity = pd.DataFrame(0, index=[f'Charger {n}' for n in N], columns=range(24))
    for n in N:
        for t in T:
            h = int(round((t-1)*delta_t))
            if any(x[k,n,t] > 0.5 for k in K):
                charger_activity.at[f'Charger {n}', h] += 1

    # A2) ChargerGantt
    gantt_rows = []
    for n in N:
        active_ts = [t for t in T if any(x[k,n,t] > 0.5 for k in K)]
        if not active_ts:
            continue
        splits = np.split(active_ts, np.where(np.diff(active_ts) != 1)[0] + 1)
        for seg in splits:
            if len(seg) == 0: continue
            start_h = (seg[0]-1)*delta_t
            end_h   = (seg[-1])*delta_t
            gantt_rows.append({
                "Charger": n, "StartHour": float(start_h),
                "EndHour": float(end_h), "Duration_h": float(end_h - start_h)
            })
    charger_gantt = pd.DataFrame(gantt_rows).sort_values(["Charger","StartHour"])

    # A3) Fleet utilisation by bus + fleet average
    rows_bus = []
    for k in K:
        active_ts = [t for t in T if (any(b[k,i,t] > 0.5 for i in I) or any(x[k,n,t] > 0.5 for n in N))]
        if not active_ts:
            continue
        t0, t1 = min(active_ts), max(active_ts)
        window = [t for t in T if t0 <= t <= t1]
        run_t = sum(delta_t for t in window if any(b[k,i,t] > 0.5 for i in I) and not any(x[k,n,t] > 0.5 for n in N))
        chg_t = sum(delta_t for t in window if any(x[k,n,t] > 0.5 for n in N))
        idle_t = sum(delta_t for t in window if not any(b[k,i,t] > 0.5 for i in I) and not any(x[k,n,t] > 0.5 for n in N))
        total_t = len(window) * delta_t
        rows_bus.append({
            "Bus": k,
            "Driving_h": run_t, "Charging_h": chg_t, "Idle_h": idle_t, "Total_h": total_t,
            "Driving_pct": 100*run_t/total_t if total_t>0 else 0.0,
            "Charging_pct": 100*chg_t/total_t if total_t>0 else 0.0,
            "Idle_pct": 100*idle_t/total_t if total_t>0 else 0.0
        })
    fleet_by_bus = pd.DataFrame(rows_bus).sort_values("Bus")
    if not fleet_by_bus.empty:
        fleet_avg = (fleet_by_bus[["Driving_pct","Charging_pct","Idle_pct"]]
                     .mean().to_frame(name="FleetAvg_pct")
                     .rename_axis("Activity").reset_index())
    else:
        fleet_avg = pd.DataFrame({"Activity":["Driving_pct","Charging_pct","Idle_pct"], "FleetAvg_pct":[0,0,0]})

    # A4) ChargerUtilisation
    total_slots = len(N)*len(T)
    used_slots = sum(1 for n in N for t in T if any(x[k,n,t] > 0.5 for k in K))
    idle_slots = total_slots - used_slots
    charger_util = pd.DataFrame({
        "State":["In Use","Idle"],
        "Slots":[used_slots, idle_slots]
    })
    charger_util["Percentage"] = charger_util["Slots"]/total_slots*100 if total_slots>0 else 0.0

    # A5) AvgSOC
    avg_soc = []
    for t in T:
        val = sum(e[k,t]/C_bat[k] for k in K)/len(K) if len(K)>0 else 0.0
        avg_soc.append(val)
    df_avg_soc = pd.DataFrame({"TimeStep": T, "Hour": hours, "AvgSOC": avg_soc})

    # A6) PowerAndPrice
    power_curve = [sum(alpha[n]*x[k,n,t] for k in K for n in N) for t in T]
    price_curve = [price[t] for t in T]
    df_power_price = pd.DataFrame({
        "TimeStep": T,
        "Hour": hours,
        "ChargingPower_kW": power_curve,
        "Price_per_kWh": price_curve
    })

    # A7) FleetEnergy (hourly bin)
    fleet_energy = (pd.DataFrame({"Hour": hours,
                                  "TotalEnergy_kWh": [sum(e[k,t] for k in K) for t in T]})
                    .groupby("Hour", as_index=False)["TotalEnergy_kWh"].sum()
                    .sort_values("Hour"))

    # A8) EnergyHeatmap (SOC matrix)
    soc_matrix = pd.DataFrame(
        [[e[k,t]/C_bat[k] for t in T] for k in K],
        index=[f"Bus {k}" for k in K],
        columns=[f"TS {t}" for t in T]
    )

    # ---------- (B) Metrics & Costs ----------
    metrics = analyze_fleet_metrics(m)
    df_metrics = pd.DataFrame([metrics])

    num_buses    = len(m.K)
    num_chargers = len(m.N)

    # CAPEX
    fleet_capex          = num_buses    * float(vehicle_unit_cost)
    charger_capex        = num_chargers * float(charger_unit_cost)
    implementation_capex = num_chargers * float(implementation_unit_cost)
    capex_total          = fleet_capex + charger_capex + implementation_capex

    # Daily OPEX: energy + demand (peak kW * €/kW/day)
    daily_energy_cost = metrics["Daily Energy Cost [€]"]
    peak_power_kw     = metrics["Peak Power [kW]"]
    daily_peak_cost   = float(peak_power_kw) * float(peak_power_price_per_kw_day)
    daily_opex_total  = daily_energy_cost + daily_peak_cost

    df_costs_capex = pd.DataFrame({
        "Category": ["Fleet CAPEX", "Charger CAPEX", "Implementation", "CAPEX Total"],
        "Quantity": [num_buses,      num_chargers,     num_chargers,     None],
        "Unit Cost [€]": [vehicle_unit_cost, charger_unit_cost, implementation_unit_cost, None],
        "Total [€]": [fleet_capex, charger_capex, implementation_capex, capex_total],
    })

    df_costs_opex_daily = pd.DataFrame({
        "Category": ["Energy (daily)", "Peak (daily)", "OPEX Total (daily)"],
        "Value [€]": [daily_energy_cost, daily_peak_cost, daily_opex_total],
    })

    # (Optional) 10-yr reference numbers if useful downstream
    daily_op_total = float(pyo.value(m.obj))         # your model’s daily energy cost objective
    energy_10yr    = daily_op_total * 365 * years_for_reference
    peak_10yr      = peak_power_kw * peak_power_price_per_kw_day * 365 * years_for_reference
    df_costs_10yr = pd.DataFrame({
        "Component": ["Energy (10yr)", "Peak (10yr)", "Total (10yr OPEX)"],
        "Value [€]": [energy_10yr, peak_10yr, energy_10yr + peak_10yr]
    })

    # ---------- Write everything ----------
    with pd.ExcelWriter(filename, engine="xlsxwriter") as writer:
        # Plot-ready datasets
        df_avg_soc.to_excel(writer,       sheet_name="AvgSOC", index=False)
        df_power_price.to_excel(writer,   sheet_name="PowerAndPrice", index=False)
        charger_activity.to_excel(writer, sheet_name="ChargerActivity")
        charger_gantt.to_excel(writer,    sheet_name="ChargerGantt", index=False)
        fleet_by_bus.to_excel(writer,     sheet_name="FleetUtilisationByBus", index=False)
        fleet_avg.to_excel(writer,        sheet_name="FleetUtilisationFleetAvg", index=False)
        charger_util.to_excel(writer,     sheet_name="ChargerUtilisation", index=False)
        fleet_energy.to_excel(writer,     sheet_name="FleetEnergy", index=False)
        soc_matrix.to_excel(writer,       sheet_name="EnergyHeatmap")

        # Metrics & Costs
        df_metrics.to_excel(writer,       sheet_name="Metrics", index=False)
        df_costs_capex.to_excel(writer,   sheet_name="Costs_CAPEX", index=False)
        df_costs_opex_daily.to_excel(writer, sheet_name="Costs_OPEX_Daily", index=False)
        df_costs_10yr.to_excel(writer,    sheet_name="Costs_OPEX_10yr", index=False)

    print(f"All data exported to: {filename}")