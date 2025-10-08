import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import matplotlib.pyplot as plt
import pyomo.environ as pyo
import math
import numpy as np
import seaborn as sns

def optimization(
        trip_start: list[int],          # timestep index  (len = I)
        trip_end:   list[int],          # timestep index  (len = I)
        alpha:      list[float],        # charger rates   (len = N)
        gamma:       list[float],        # km · h⁻¹         (len = I)
        C_bat:      list[float],        # kWh capacity    (len = K)
        P:          list[float],        # €/kWh spot price (len = T)
        E_0:      float = 0.20,       # initial SOC (p.u.)
        E_min:      float = 0.20,       # min SOC (p.u.)
        E_max:      float = 1.00,       # max SOC (p.u.)
        E_end:      float = 0.20,       # end SOC (p.u)
        delta_t:    float = 0.25,      # h (15-min step)
        relaxed_binary: bool = False   # if True, use continuous [0,1] instead of binary variables
):

    # ── 1. basic sets ─────────────────────────────────────────────────────────
    I, T, K, N = len(trip_start), (len(P) if len(P) > max(trip_end) else max(trip_end)), len(C_bat), len(alpha)

    m = pyo.ConcreteModel()
    m.I = pyo.RangeSet(1, I)
    m.T = pyo.RangeSet(1, T)
    m.K = pyo.RangeSet(1, K)
    m.N = pyo.RangeSet(1, N)
    
    print(f"Number of trips: {I}, Time steps: {T}, Buses: {K}, Chargers: {N}")
    
    # ── 2. parameters ─────────────────────────────────────────────────────────
        
    m.T_start = pyo.Param(m.I, initialize=lambda _, i: trip_start[i-1])
    m.T_end   = pyo.Param(m.I, initialize=lambda _, i: trip_end[i-1])
    m.alpha   = pyo.Param(m.N, initialize=lambda _, n: alpha[n-1])
    m.gamma   = pyo.Param(m.I, initialize=lambda _, i: gamma[i-1])

    m.P       = pyo.Param(m.T, initialize=lambda _, t: P[t-1])
    m.C_bat   = pyo.Param(m.K, initialize=lambda _, k: C_bat[k-1])

    m.ch_eff  = pyo.Param(initialize=0.90)       # charging efficiency
    m.E_0     = pyo.Param(initialize=E_0)       # initial SOC (p.u.)
    m.E_min   = pyo.Param(initialize=E_min)       # min SOC (p.u.)
    m.E_max   = pyo.Param(initialize=E_max)       # max SOC (p.u.)
    m.E_end   = pyo.Param(initialize=E_end)       # end SOC (p.u.)
    m.delta_t = pyo.Param(initialize=delta_t)
    
    print('Parameters initialized')
    
    # ── 3. decision variables ────────────────────────────────────────────────
    # Use either Binary or NonNegativeReals constrained to [0,1] based on relaxed_binary parameter
    var_domain = pyo.UnitInterval if relaxed_binary else pyo.Binary
    m.b     = pyo.Var(m.K, m.I, m.T, within=var_domain)   # bus k drives trip i at t
    m.x     = pyo.Var(m.K, m.N, m.T, within=var_domain)   # bus k charges on charger n
    m.e     = pyo.Var(m.K, m.T,     within=pyo.NonNegativeReals)
    m.w_buy = pyo.Var(m.T,          within=pyo.NonNegativeReals)

    print('Variables initialized')
    
    # ── 4. objective – minimise energy cost ──────────────────────────────────
    m.obj = pyo.Objective(
        expr=sum(m.P[t] * m.w_buy[t] for t in m.T),
        sense=pyo.minimize
    )

    print('Objective function defined')
    
    # ── 5. constraints ───────────────────────────────────────────────────────
    cons = m.constraints = pyo.ConstraintList()

    # 5.1 ≤ 1 activity (drive or charge) per bus & timestep
    for k in m.K:
        for t in m.T:
            drive  = sum(m.b[k, i, t]      for i in m.I)
            charge = sum(m.x[k, n, t]      for n in m.N)
            cons.add(drive + charge <= 1)

    # 5.2 each bus can only charge at one charger at a time
    for n in m.N:
        for t in m.T:
            cons.add(sum(m.x[k, n, t] for k in m.K) <= 1)

    # 5.3 each trip must be fully covered by exactly one bus
    for i in m.I:
        for t in range(m.T_start[i], m.T_end[i]):
            cons.add(sum(m.b[k, i, t] for k in m.K) == 1)
            
        for t in range(1,m.T_start[i]):
            cons.add(sum(m.b[k,i,t] for k in m.K) == 0)

        for t in range(m.T_end[i],T+1):
            cons.add(sum(m.b[k,i,t] for k in m.K) == 0)

    # 5.4 continuity of assignment: once a bus starts trip i it stays on it
    for i in m.I:
        for k in m.K:
            for t in range(m.T_start[i], m.T_end[i] - 1):
                cons.add(m.b[k, i, t+1] >= m.b[k, i, t])

    # 5.5 battery state-of-charge (SOC) evolution
    for k in m.K:
        cons.add(m.e[k, 1] == m.E_0 * m.C_bat[k])        # initialise
        for t in range(2, T+1):
            charge_in  = sum(m.delta_t * m.ch_eff * m.alpha[n] * m.x[k, n, t] for n in m.N)
            drive_out  = sum(m.gamma[i] * m.b[k, i, t]                    for i in m.I)
            cons.add(m.e[k, t] == m.e[k, t-1] + charge_in - drive_out)

    # 5.6 depot energy balance (total charging equals market purchase)
    for t in m.T:
        total_ch = sum(m.delta_t * m.ch_eff * m.alpha[n] * m.x[k, n, t]
                       for k in m.K for n in m.N)
        cons.add(total_ch == m.w_buy[t])

    # 5.7 SOC bounds
    for k in m.K:
        for t in m.T:
            cons.add(m.e[k, t] >= m.C_bat[k] * m.E_min)
            cons.add(m.e[k, t] <= m.C_bat[k] * m.E_max)
            
    # 5.8 final SOC must be at least E_end
    for k in m.K:
        cons.add(m.e[k, T] >= m.C_bat[k] * m.E_end)

    print('Constraints defined')
    
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