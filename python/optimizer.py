import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict

def optimize(data):
    # Load data from the Excel file
    T_start = [int(x) for x in data['Dataset']['Trip Begin'].tolist()]
    duration = [int(x) for x in data['Dataset']['Trip Duration'].tolist()]  # NEW: duration instead of T_end
    alpha = data['Dataset']['Charger'].tolist()
    gama = data['Dataset']['Energy consumption'].tolist()
    C_bat = data['Dataset']['Buses'].tolist()
    P = data['Energy Price']['Buy']

    # Constants
    ch_eff = 0.9
    E_0 = 0.2
    E_max = 1
    E_min = 0.2
    delta_t = 0.25
    velocity = 12
    gama = np.array(gama) * velocity * delta_t

    T = 96  # total number of time steps
    t = len(P)
    k = len(C_bat)
    n = len(alpha)
    i = len(T_start)

    model = pyo.ConcreteModel()

    # Sets
    model.I = pyo.RangeSet(i)
    model.T = pyo.RangeSet(t)
    model.K = pyo.RangeSet(k)
    model.N = pyo.RangeSet(n)

    # Parameters
    model.T_start = pyo.Param(model.I, initialize=lambda model, i: T_start[i - 1])
    model.duration = pyo.Param(model.I, initialize=lambda model, i: duration[i - 1])
    model.alpha = pyo.Param(model.N, initialize=lambda model, n: alpha[n - 1])
    model.ch_eff = pyo.Param(initialize=ch_eff)
    model.gama = pyo.Param(model.I, initialize=lambda model, i: gama[i - 1])
    model.P = pyo.Param(model.T, initialize=lambda model, t: P[t - 1])
    model.E_0 = pyo.Param(initialize=E_0)
    model.E_min = pyo.Param(initialize=E_min)
    model.E_max = pyo.Param(initialize=E_max)
    model.C_bat = pyo.Param(model.K, initialize=lambda model, k: C_bat[k - 1])
    model.delta_t = pyo.Param(initialize=delta_t)

    # Variables
    model.b = pyo.Var(model.K, model.I, model.T, within=pyo.UnitInterval)
    model.x = pyo.Var(model.K, model.N, model.T, within=pyo.UnitInterval)
    model.e = pyo.Var(model.K, model.T, within=pyo.NonNegativeReals)
    model.w_buy = pyo.Var(model.T, within=pyo.NonNegativeReals)

    # Objective function
    def rule_obj(mod):
        return sum(mod.P[t] * mod.w_buy[t] for t in mod.T)
    model.obj = pyo.Objective(rule=rule_obj, sense=pyo.minimize)

    # Constraints
    model.constraints = pyo.ConstraintList()

    # Constraint 2
    for k in model.K:
        for t in model.T:
            model.constraints.add(
                sum(model.b[k, i, t] for i in model.I) + sum(model.x[k, n, t] for n in model.N) <= 1
            )

    # Constraint 3
    for n in model.N:
        for t in model.T:
            model.constraints.add(sum(model.x[k, n, t] for k in model.K) <= 1)

    # Constraint 4 — enforce trip allocation during trip time
    for i in model.I:
        t_start = T_start[i - 1]
        t_end = t_start + duration[i - 1]
        for t in range(t_start, t_end):
            if t <= T:
                model.constraints.add(sum(model.b[k, i, t] for k in model.K) == 1)

    # Constraint 5 — force continuity of assigned trips
    for i in model.I:
        t_start = T_start[i - 1]
        t_end = t_start + duration[i - 1]
        for k in model.K:
            for t in range(t_start, t_end - 1):
                if t + 1 <= T:
                    model.constraints.add(model.b[k, i, t + 1] >= model.b[k, i, t])

    # Constraint 6 — battery evolution
    for k in model.K:
        for t in range(2, T + 1):
            model.constraints.add(
                model.e[k, t] ==
                model.e[k, t - 1] +
                sum(model.delta_t * model.ch_eff * model.alpha[n] * model.x[k, n, t] for n in model.N) -
                sum(model.gama[i] * model.b[k, i, t] for i in model.I)
            )

    # Constraint 7 — total energy bought
    for t in model.T:
        model.constraints.add(
            sum(model.delta_t * model.ch_eff * model.alpha[n] * model.x[k, n, t] for n in model.N for k in model.K) ==
            model.w_buy[t]
        )

    # Constraint 8 and 9 — battery bounds
    for k in model.K:
        for t in model.T:
            model.constraints.add(model.e[k, t] >= model.C_bat[k] * model.E_min)
            model.constraints.add(model.e[k, t] <= model.C_bat[k] * model.E_max)

    # Constraint 10 — initial SOC
    for k in model.K:
        model.constraints.add(model.e[k, 1] == model.E_0 * model.C_bat[k])

    return model

def plots(K, T, e, w, delta_t, C_bat):
    bus_list = []
    energy_list = []
    for k in K:
        bus_number = 'bus' + ' ' + str(k)
        bus_list.append(bus_number)
    for t in T:
        for k in K:
            energy_list.append(pyo.value(e[k, t]))
    energy_array = np.reshape(energy_list, (len(T), len(bus_list)))
    Energy = pd.DataFrame(energy_array, index=T, columns=bus_list)
    Energy_perc = (Energy * 100) / C_bat

    transac_list = []
    for t in T:
        value = pyo.value(w[t])
        transac_list.append(value)
    Power = pd.DataFrame(transac_list, index=T, columns=['Power']) / delta_t

    fig, axs = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    Energy_perc.plot(ax=axs[0])
    axs[0].set_ylabel('State of Charge [%]')
    axs[0].set_title('Bus State of Charge Over Time')
    axs[0].legend(loc='best')

    Power.plot(ax=axs[1])
    axs[1].set_xlabel('Time [min]')
    axs[1].set_ylabel('Power [kWh]')
    axs[1].set_title('Grid Power Over Time')
    axs[1].legend(loc='best')
    
    plt.tight_layout()
    plt.show()
    return Energy, Energy_perc, Power


def get_departure_times(file_path):
    
    df = pd.read_excel(file_path)

    # Create dictionary
    departure_dict = defaultdict(list)

    for _, row in df.iterrows():
        line_id = row["Line ID"]
        times_str = row["Unique Departure Times (HH:mm)"]
        times = [t.strip() for t in times_str.split(",")]
        departure_dict[line_id].extend(times)

    # Convert to regular dict
    departure_dict = dict(departure_dict)
    return departure_dict

data = pd.read_excel('python/input.xlsx', None)
departure_times = get_departure_times('python/transit_departures.xlsx')
model = optimize(data)

opt = pyo.SolverFactory('gurobi')
#opt.options['timelimit'] = 60
#opt.options['mipgap'] = 0.01
results = opt.solve(model,tee=True)

energy, energy_perc, power = plots(model.K,model.T,model.e, model.w_buy, model.delta_t, C_bat=348)

print('The objective function values is:', model.obj())
