import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import pprint
import matplotlib.pyplot as plt
import pyomo.environ as pyo

def optimization(
        trip_start: list[int],          # timestep index  (len = I)
        trip_end:   list[int],          # timestep index  (len = I)
        alpha:      list[float],        # charger rates   (len = N)
        velocity:   list[float],        # km · h⁻¹         (len = I)
        C_bat:      list[float],        # kWh capacity    (len = K)
        P:          list[float],        # €/kWh spot price (len = T)
        delta_t:    float = 0.25        # h (15-min step)
):

    # ── 1. fixed per-trip energy draw factor (γᵢ) ────────────────────────────
    #     here treated as:  η_drive · vᵢ · Δt   (η_drive ≈ 0.9)
    drive_eff = 0.9
    gamma_list = [drive_eff * v * delta_t for v in velocity]

    # ── 2. basic sets ─────────────────────────────────────────────────────────
    I, T, K, N = len(trip_start), max(trip_end), len(C_bat), len(alpha)

    m = pyo.ConcreteModel()
    m.I = pyo.RangeSet(1, I)
    m.T = pyo.RangeSet(1, T)
    m.K = pyo.RangeSet(1, K)
    m.N = pyo.RangeSet(1, N)
    
    print(f"Number of trips: {I}, Time steps: {T}, Buses: {K}, Chargers: {N}")
    
    # ── 3. parameters ─────────────────────────────────────────────────────────
    m.T_start = pyo.Param(m.I, initialize=lambda _, i: trip_start[i-1])
    m.T_end   = pyo.Param(m.I, initialize=lambda _, i: trip_end[i-1])
    m.alpha   = pyo.Param(m.N, initialize=lambda _, n: alpha[n-1])
    m.gamma   = pyo.Param(m.I, initialize=lambda _, i: gamma_list[i-1])

    m.P       = pyo.Param(m.T, initialize=lambda _, t: P[t-1])
    m.C_bat   = pyo.Param(m.K, initialize=lambda _, k: C_bat[k-1])

    m.ch_eff  = pyo.Param(initialize=0.90)       # charging efficiency
    m.E_0     = pyo.Param(initialize=1.00)       # initial SOC (p.u.)
    m.E_min   = pyo.Param(initialize=0.20)       # min SOC (p.u.)
    m.E_max   = pyo.Param(initialize=1.00)       # max SOC (p.u.)
    m.E_end   = pyo.Param(initialize=0.9)       # end SOC (p.u.)
    m.delta_t = pyo.Param(initialize=delta_t)
    
    print('Parameters initialized')
    
    # ── 4. decision variables ────────────────────────────────────────────────
    m.b     = pyo.Var(m.K, m.I, m.T, within=pyo.Binary)   # bus k drives trip i at t
    m.x     = pyo.Var(m.K, m.N, m.T, within=pyo.Binary)   # bus k charges on charger n
    m.e     = pyo.Var(m.K, m.T,     within=pyo.NonNegativeReals)
    m.w_buy = pyo.Var(m.T,          within=pyo.NonNegativeReals)

    print('Variables initialized')
    
    # ── 5. objective – minimise energy cost ──────────────────────────────────
    m.obj = pyo.Objective(
        expr=sum(m.P[t] * m.w_buy[t] for t in m.T),
        sense=pyo.minimize
    )

    print('Objective function defined')
    
    # ── 6. constraints ───────────────────────────────────────────────────────
    cons = m.constraints = pyo.ConstraintList()

    # 6.1 ≤ 1 activity (drive or charge) per bus & timestep
    for k in m.K:
        for t in m.T:
            drive  = sum(m.b[k, i, t]      for i in m.I)
            charge = sum(m.x[k, n, t]      for n in m.N)
            cons.add(drive + charge <= 1)

    # 6.2 each bus can only charge at one charger at a time
    for n in m.N:
        for t in m.T:
            cons.add(sum(m.x[k, n, t] for k in m.K) <= 1)

    # 6.3 each trip must be fully covered by exactly one bus
    for i in m.I:
        for t in range(m.T_start[i], m.T_end[i]):
            cons.add(sum(m.b[k, i, t] for k in m.K) == 1)
            
        for t in range(1,m.T_start[i]):
            cons.add(sum(m.b[k,i,t] for k in m.K) == 0)

        for t in range(m.T_end[i],T+1):
            cons.add(sum(m.b[k,i,t] for k in m.K) == 0)

    # 6.4 continuity of assignment: once a bus starts trip i it stays on it
    for i in m.I:
        for k in m.K:
            for t in range(m.T_start[i], m.T_end[i] - 1):
                cons.add(m.b[k, i, t+1] >= m.b[k, i, t])

    # 6.5 battery state-of-charge (SOC) evolution
    for k in m.K:
        cons.add(m.e[k, 1] == m.E_0 * m.C_bat[k])        # initialise
        for t in range(2, T+1):
            charge_in  = sum(m.delta_t * m.ch_eff * m.alpha[n] * m.x[k, n, t] for n in m.N)
            drive_out  = sum(m.gamma[i] * m.b[k, i, t]                    for i in m.I)
            cons.add(m.e[k, t] == m.e[k, t-1] + charge_in - drive_out)

    # 6.6 depot energy balance (total charging equals market purchase)
    for t in m.T:
        total_ch = sum(m.delta_t * m.ch_eff * m.alpha[n] * m.x[k, n, t]
                       for k in m.K for n in m.N)
        cons.add(total_ch == m.w_buy[t])

    # 6.7 SOC bounds
    for k in m.K:
        for t in m.T:
            cons.add(m.e[k, t] >= m.C_bat[k] * m.E_min)
            cons.add(m.e[k, t] <= m.C_bat[k] * m.E_max)
            
    # 6.8 final SOC must be at least E_end
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

def plot_energy_and_power(model):
    # build time axis in hours
    delta_t = model.delta_t.value
    time_axis = [(t-1)*delta_t for t in model.T]

    # Energy curves
    plt.figure(figsize=(12, 6))
    for k in model.K:
        soc = [model.e[k, t].value for t in model.T]
        plt.plot(time_axis, soc, label=f'Bus {k}')
    plt.title('State of Charge')
    plt.xlabel('Time (hours)')
    plt.ylabel('Energy (kWh)')
    plt.legend()
    plt.show()

    # Power purchase curve
    plt.figure(figsize=(12, 6))
    power = [model.w_buy[t].value * (4/0.9) for t in model.T]  # Convert to kW (assuming delta_t in hours)
    plt.plot(time_axis, power)
    plt.title('Charging Power')
    plt.xlabel('Time (hours)')
    plt.ylabel('Power (kW)')
    plt.show()
    
# Main execution starts here
# Load the trips data
df = pd.read_excel('python/trips_15_min.xlsx')
target_lines = ["1-803"] # Example: "1-803", "1-807", "1-800", "1-801", "1-802", "1-804"
df = df[df["Line ID"].isin(target_lines)].copy()
data = pd.read_excel('python/input.xlsx', sheet_name=None)

# ── 1. data preparation ────────────────────────────────────────────────
bus_counts     = [11] # 249 buses, each with 350 kWh battery
battery_sizes  = [350]
charger_counts = [5] # 50 chargers, each with 150 kW
charger_powers = [150]

C_bat, alpha = build_fleet_and_chargers(
    bus_counts, battery_sizes,
    charger_counts, charger_powers
)

# ── 2. extract data sets ───────────────────────────────────────────────
# Extract the necessary data from the DataFrame
energy_price = data['Energy Price']['Buy'].to_list()
start = df['Start Step'].astype(int).to_list()
end   = df['End Step'].astype(int).to_list()
speed_col = 'Average Speed (km/h)' if 'Average Speed (km/h)' in df.columns else 'Average Speed'
speed = df[speed_col].astype(float).round(2).to_list()

# ── 3. optimization model ────────────────────────────────────────────────
# Run the optimization model
model = optimization(start, end, alpha, speed, C_bat, energy_price)
SolverFactory('gurobi').solve(model, tee=True, options={'TimeLimit': 60, 'MIPGAP': 0.01})

# ── 4. post-processing ─────────────────────────────────────────────────────
# Print the results
pprint.pprint(pyo.value(model.obj))
plot_energy_and_power(model)