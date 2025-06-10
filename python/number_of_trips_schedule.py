import pandas as pd
from collections import defaultdict
from transit.schedule import parse_transit_departures

# === PARAMETERS ===
TRAVEL_TIME = 30  # in minutes
LAYOVER = 5       # in minutes
TURNAROUND_TIME = TRAVEL_TIME + LAYOVER

# === HELPER FUNCTIONS ===
def time_to_minutes(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m

def minutes_to_hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"

def convert_schedule_to_hhmm(schedule):
    return {
        "start": minutes_to_hhmm(schedule["start_minute"]),
        "end": minutes_to_hhmm(schedule["end_minute"])
    }

# === LOAD DATA ===
file_path = "transit_departures.xlsx"  # adjust path as needed
df = pd.read_excel(file_path)

shape_dict = parse_transit_departures(df)

# === ORGANISE DEPARTURES PER ROUTE ===
line_trips = defaultdict(list)
for _, row in df.iterrows():
    line_id = row["Line ID"]
    times_str = row["Unique Departure Times (HH:mm)"]
    times = [time_to_minutes(t.strip()) for t in times_str.split(",") if isinstance(t, str)]
    times.sort()
    line_trips[line_id].extend(times)

# === ASSIGN BUSES TO TRIPS ===
detailed_operations = {}

for line_id, departures in line_trips.items():
    departures_sorted = sorted(departures)
    buses = []

    for dep in departures_sorted:
        assigned = False
        for i, schedule in enumerate(buses):
            if dep >= schedule[-1] + TURNAROUND_TIME:
                buses[i].append(dep)
                assigned = True
                break
        if not assigned:
            buses.append([dep])

    # Create operation window for each bus
    detailed_operations[line_id] = []
    for bus_schedule in buses:
        start_time = bus_schedule[0]
        end_time = bus_schedule[-1] + TRAVEL_TIME
        detailed_operations[line_id].append({
            "start_minute": start_time,
            "end_minute": end_time
        })

# === SHOW SAMPLE OUTPUT IN HH:mm FORMAT ===
sample_ops = {
    line: [convert_schedule_to_hhmm(s) for s in schedules]
    for line, schedules in list(detailed_operations.items())[:3]
}

# Print sample
for line, schedules in sample_ops.items():
    print(f"Route {line}:")
    for i, op in enumerate(schedules, 1):
        print(f"  Bus {i}: {op['start']} - {op['end']}")