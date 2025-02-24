package run;
import org.matsim.vehicles.Vehicle;
import org.matsim.vehicles.Vehicles;
import org.matsim.utils.objectattributes.attributable.Attributes;

import java.util.Random;

public class AddInitialSoc {

    public static void addInitialSoc(Vehicles vehicles) {
        // Create a Random object to generate random values
        Random random = new Random();

        // Iterate through all vehicles
        for (Vehicle vehicle : vehicles.getVehicles().values()) {
            // Check if the vehicle is a bus (e.g., by type or ID prefix)
            if (isBus(vehicle)) {
                // Generate a random initialSoc between 0.2 (20%) and 0.8 (80%)
                double initialSoc = 0.2 + (0.8 - 0.2) * random.nextDouble();

                // Add the initialSoc attribute
                Attributes attributes = vehicle.getAttributes();
                attributes.putAttribute("initialSoc", initialSoc);
            }
        }
    }

    private static boolean isBus(Vehicle vehicle) {
        // Example: Check if the vehicle type is "bus"
//        return "bus".equals(vehicle.getType().getId().toString());
        // Alternatively, check if the vehicle ID starts with "bus_"
         return vehicle.getId().toString().startsWith("bus_");
    }
}