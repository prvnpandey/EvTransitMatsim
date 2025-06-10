import pandas as pd
from datetime import datetime, timedelta
import heapq
import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import numpy as np
import pprint
from trips_routes_functions import *
import matplotlib.pyplot as plt

def flatten_stats_trips(stats):
    rows = []
    for route, info in stats.items():
        for bus_idx, bus in enumerate(info['buses']):
            for trip_idx, (dep, arr) in enumerate(bus['trips']):
                rows.append({
                    'route':    route,
                    'bus_idx':  bus_idx+1,
                    'trip_idx': trip_idx+1,
                    'dep_time': dep,
                    'arr_time': arr
                })
    return pd.DataFrame(rows)

def time_to_step(t_str: str, delta_t: float=0.25) -> int:
    h, m = map(int, t_str.split(':'))
    minutes = h*60 + m
    return int(minutes / (delta_t*60)) + 1

def optimize_from_trips_df(
    trips_df: pd.DataFrame,
    alpha:   list[float],
    gama0:    dict[str, float],
    C_bat:   list[float],
    P:       list[float],
    delta_t: float = 0.25
):
    # ─── 1. Build T_start, T_end and route lists from trips_df ────────────────
    T_start = trips_df['dep_time'].apply(lambda t: time_to_step(t, delta_t)).tolist()
    T_end   = trips_df['arr_time'].apply(lambda t: time_to_step(t, delta_t)).tolist()
    route_keys = trips_df['route'].tolist()

    # unique routes + index mapping
    unique_routes = sorted(set(route_keys))
    route_map     = {rid:i+1 for i,rid in enumerate(unique_routes)}
    route_idx     = [route_map[r] for r in route_keys]

    # convert gama0 dict into a list aligned with model.R
    velocity = 12
    gamma_list = [
        gama0[rid] * velocity * delta_t
        for rid in unique_routes
    ]

    # ─── 2. Determine index sizes ───────────────────────────────────────────────
    I = len(T_start)
    T = len(P)
    K = len(C_bat)
    N = len(alpha)
    R = len(unique_routes)

    # ─── 3. Build the Pyomo model ───────────────────────────────────────────────
    m = pyo.ConcreteModel()
    m.I = pyo.RangeSet(I)
    m.T = pyo.RangeSet(T)
    m.K = pyo.RangeSet(K)
    m.N = pyo.RangeSet(N)
    m.R = pyo.RangeSet(R)

    # Parameters
    m.route   = pyo.Param(m.I, initialize=lambda _,i: route_idx[i-1])
    m.T_start = pyo.Param(m.I, initialize=lambda _,i: T_start[i-1])
    m.T_end   = pyo.Param(m.I, initialize=lambda _,i: T_end[i-1])
    m.alpha   = pyo.Param(m.N, initialize=lambda _,n: alpha[n-1])
    m.ch_eff  = pyo.Param(initialize=0.9)
    m.gama    = pyo.Param(m.R, initialize=lambda _,r: gamma_list[r-1])
    m.P       = pyo.Param(m.T, initialize=lambda _,t: P[t-1])
    m.E_0     = pyo.Param(initialize=0.2)
    m.E_min   = pyo.Param(initialize=0.2)
    m.E_max   = pyo.Param(initialize=1.0)
    m.C_bat   = pyo.Param(m.K, initialize=lambda _,k: C_bat[k-1])
    m.delta_t = pyo.Param(initialize=delta_t)

    # Decision vars
    m.b     = pyo.Var(m.K, m.R, m.I, m.T, within=pyo.UnitInterval)
    m.x     = pyo.Var(m.K, m.N, m.T,     within=pyo.UnitInterval)
    m.e     = pyo.Var(m.K, m.T,           within=pyo.NonNegativeReals)
    m.w_buy = pyo.Var(m.T,                within=pyo.NonNegativeReals)

    # Objective
    m.obj = pyo.Objective(
        expr = sum(m.P[t]*m.w_buy[t] for t in m.T),
        sense= pyo.minimize
    )

    cons = m.constraints = pyo.ConstraintList()

    # 1. ≤1 activity per bus/time‐step
    for k in m.K:
        for t in m.T:
            drive  = sum(m.b[k, m.route[i], i, t] for i in m.I)
            charge = sum(m.x[k, n, t] for n in m.N)
            cons.add(drive + charge <= 1)

    # 2. each trip must be served over its full window
    for i in m.I:
        r = m.route[i]
        for t in range(m.T_start[i], m.T_end[i]):
            cons.add(sum(m.b[k, r, i, t] for k in m.K) == 1)

    # 3. continuity of assignment within each trip
    for i in m.I:
        r = m.route[i]
        for k in m.K:
            for t in range(m.T_start[i], m.T_end[i]-1):
                cons.add(m.b[k, r, i, t+1] >= m.b[k, r, i, t])

    # 4. battery evolution (uses route‐specific γ)
    for k in m.K:
        for t in range(2, T+1):
            cons.add(
                m.e[k, t] == m.e[k, t-1]
                  + sum(m.delta_t*m.ch_eff*m.alpha[n]*m.x[k,n,t] for n in m.N)
                  - sum(m.gama[m.route[i]] * m.b[k, m.route[i], i, t] for i in m.I)
            )

    # 5. energy purchase balance
    for t in m.T:
        cons.add(
            sum(m.delta_t*m.ch_eff*m.alpha[n]*m.x[k,n,t]
                for k in m.K for n in m.N)
            == m.w_buy[t]
        )

    # 6–7. SOC bounds + initial SOC
    for k in m.K:
        for t in m.T:
            cons.add(m.e[k,t] >= m.C_bat[k]*m.E_min)
            cons.add(m.e[k,t] <= m.C_bat[k]*m.E_max)
        cons.add(m.e[k,1] == m.E_0*m.C_bat[k])

    return m

def generate_buses_and_chargers(stats: dict, battery_capacity, charger_rate):
    C_bat_list = []
    alpha_list = []

    for route_id, info in stats.items():
        n_buses = info.get('buses_required', 0)

        # Determine battery capacity for this route
        if isinstance(battery_capacity, dict):
            if route_id not in battery_capacity:
                raise KeyError(f"No battery_capacity for route '{route_id}'")
            cap = battery_capacity[route_id]
        else:
            cap = battery_capacity

        # Determine charger rate (alpha) for this route
        if isinstance(charger_rate, dict):
            if route_id not in charger_rate:
                raise KeyError(f"No charger_rate for route '{route_id}'")
            rate = charger_rate[route_id]
        else:
            rate = charger_rate

        # Append entries for each bus
        for _ in range(n_buses):
            C_bat_list.append(cap)
            alpha_list.append(rate)

    return C_bat_list, alpha_list[:len(alpha_list)//2]

def generate_gama0(stats: dict, 
                   min_gamma: float = 0.9, 
                   max_gamma: float = 2.2, 
                   method: str = 'linear') -> dict:
    
    routes = sorted(stats.keys())
    n = len(routes)
    if method == 'linear':
        values = np.linspace(min_gamma, max_gamma, n)
    elif method == 'random':
        values = np.random.uniform(min_gamma, max_gamma, n)
    else:
        raise ValueError("method must be 'linear' or 'random'")
    
    # map each route to its gamma0
    gama0 = {route: float(v) for route, v in zip(routes, values)}
    return gama0

def plot_energy_and_power(model):
    # build time axis in hours
    delta_t = model.delta_t.value
    time_axis = [(t-1)*delta_t for t in model.T]

    # Energy curves
    plt.figure(figsize=(12, 6))
    for k in model.K:
        soc = [model.e[k, t].value for t in model.T]
        plt.plot(time_axis, soc, label=f'Bus {k}')
    plt.title('State of Charge of All Buses')
    plt.xlabel('Time (hours)')
    plt.ylabel('Energy (kWh)')
    plt.legend()
    plt.show()

    # Power purchase curve
    plt.figure(figsize=(12, 6))
    power = [model.w_buy[t].value * 4 for t in model.T]  # Convert to kW (assuming delta_t in hours)
    plt.plot(time_axis, power)
    plt.title('Power Purchase over Time')
    plt.xlabel('Time (hours)')
    plt.ylabel('Power (kW)')
    plt.show()
    
'''
#######################
#######################
#######################
#######################
#######################
#######################
OPTMIZATION STARTS HERE
#######################
#######################
#######################
#######################
#######################
#######################
'''

# 1. Load the data
df = pd.read_excel('python/transit_departures.xlsx')

# 2. Clean the DataFrame to keep only one inbound and one outbound trip per line
df = clean_inbound_outbound(df)

# 3. Calculate bus requirements for interlined trips
trip_times = {'1-1': 30,'1-107': 45,'1-82': 35} # NEED TO BE UPDATED!!! SHOULD BE IN THE TRANSIT DEPARTURE DATAFRAME
stats = calculate_bus_requirements_interlined(df, trip_times, default_trip_time=30)
#pprint.pprint(stats)  # Print the statistics for each route

# 4. Build a dict with only the selected routes
route_keys = ['1-1', '1-107', '1-82']
selected_routes = {k: stats[k] for k in route_keys if k in stats}

# 5. Prepare the data for the optimizer
data = pd.read_excel('python/input.xlsx', sheet_name=None)
trips_df = flatten_stats_trips(selected_routes)
gama0 = generate_gama0(selected_routes, min_gamma=2, max_gamma=2)
C_bat, alpha = generate_buses_and_chargers(selected_routes, battery_capacity=350, charger_rate=100)
P = data['Energy Price']['Buy'].tolist()

# 6. Call the optimizer
model = optimize_from_trips_df(trips_df, alpha, gama0, C_bat, P)

# 7. Solve the model
SolverFactory('gurobi').solve(model, tee=True)

# 8. Print the results
pprint.pprint(pyo.value(model.obj))
plot_energy_and_power(model)