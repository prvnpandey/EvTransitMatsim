package run;

import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Person;
import org.matsim.core.router.costcalculators.TravelDisutilityFactory;
import org.matsim.core.router.util.TravelDisutility;
import org.matsim.core.router.util.TravelTime;
import org.matsim.vehicles.Vehicle;

public class CustomPtTravelDisutilityFactory implements TravelDisutilityFactory {

    // Define weights for different components of the disutility
    private final double weightInVehicleTime; // Weight for in-vehicle time
    private final double weightWaitingTime;   // Weight for waiting time
    private final double weightTransferPenalty; // Weight for transfer penalties
    private final double weightFare;          // Weight for fare cost

    public CustomPtTravelDisutilityFactory(double weightInVehicleTime, double weightWaitingTime, double weightTransferPenalty, double weightFare) {
        this.weightInVehicleTime = weightInVehicleTime;
        this.weightWaitingTime = weightWaitingTime;
        this.weightTransferPenalty = weightTransferPenalty;
        this.weightFare = weightFare;
    }

    @Override
    public TravelDisutility createTravelDisutility(TravelTime travelTime) {
        return new TravelDisutility() {
            @Override
            public double getLinkTravelDisutility(Link link, double time, Person person, Vehicle vehicle) {
                // Calculate the disutility for a given link and time
                double inVehicleTime = travelTime.getLinkTravelTime(link, time, person, vehicle);
                double waitingTime = getWaitingTime(link, time); // Custom method to calculate waiting time
                double transferPenalty = getTransferPenalty(link, time); // Custom method to calculate transfer penalty
                double fare = getFare(link, time); // Custom method to calculate fare

                // Combine the components into a single disutility value
                return (weightInVehicleTime * inVehicleTime) +
                       (weightWaitingTime * waitingTime) +
                       (weightTransferPenalty * transferPenalty) +
                       (weightFare * fare);
            }

            @Override
            public double getLinkMinimumTravelDisutility(Link link) {
                // Return the minimum possible disutility for the link
                return link.getLength() / 10.0; // Example: minimum cost based on link length
            }
        };
    }

    // Custom method to calculate waiting time
    private double getWaitingTime(Link link, double time) {
        // Implement your logic to calculate waiting time
        return 5.0; // Example: fixed waiting time of 5 minutes
    }

    // Custom method to calculate transfer penalty
    private double getTransferPenalty(Link link, double time) {
        // Implement your logic to calculate transfer penalty
        return 2.0; // Example: fixed transfer penalty of 2 minutes
    }

    // Custom method to calculate fare
    private double getFare(Link link, double time) {
        // Implement your logic to calculate fare
        return 1.5; // Example: fixed fare of 1.5 monetary units
    }
}
