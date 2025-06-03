from speed_access import plot_speeds

def analysis(speed_results, freespeeds):
    
# Print all results.
    for rec in speed_results[:10]:  # Print first 10 records for brevity
        free_speed = freespeeds.get(rec['link'], None)
        print(f"Vehicle {rec['vehicle']} on link {rec['link']} (length: {rec['length']:.2f}m, free speed: {rec['freespeed']:.2f} m/s): "
            f"Entered at {rec['entry_time']} sec, left at {rec['exit_time']} sec, "
            f"travel time = {rec['travel_time']} sec, speed = {rec['speed']:.2f} m/s, "
            f"freespeed distance = {rec['freespeed_distance']:.2f}m, stop-and-go distance = {rec['stop_and_go_distance']:.2f}m, "
            f"freespeed time = {rec['freespeed_time']:.2f}s, stop-and-go time = {rec['stop_and_go_time']:.2f}s")
        
    # Print results for a specific vehicle ID.
    specific_vehicle_id = '44227'
    specific_vehicle_results = [r for r in speed_results if r['vehicle'] == specific_vehicle_id]
    for rec in specific_vehicle_results[:10]:
        print(f"Specific Vehicle {rec['vehicle']} on link {rec['link']} (length: {rec['length']:.2f}m, free speed: {rec['freespeed']:.2f} m/s): "
            f"Entered at {rec['entry_time']} sec, left at {rec['exit_time']} sec, "
            f"travel time = {rec['travel_time']} sec, speed = {rec['speed']:.2f} m/s, "
            f"freespeed distance = {rec['freespeed_distance']:.2f}m, stop-and-go distance = {rec['stop_and_go_distance']:.2f}m, "
            f"freespeed time = {rec['freespeed_time']:.2f}s, stop-and-go time = {rec['stop_and_go_time']:.2f}s")
        
    plot_speeds(speed_results, '44227', 14400, 15450)