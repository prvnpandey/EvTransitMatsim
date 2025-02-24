package evTransitRouter;

import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Person;
import org.matsim.contrib.ev.discharging.DriveEnergyConsumption;
import org.matsim.contrib.ev.fleet.ElectricFleetSpecification;
import org.matsim.contrib.ev.fleet.ElectricVehicle;
import org.matsim.core.router.util.LeastCostPathCalculator;
import org.matsim.core.router.util.TravelDisutility;
import org.matsim.core.router.util.TravelTime;
import org.matsim.pt.router.TransitRouterConfig;
import org.matsim.vehicles.Vehicle;

public class TransitRouterNetworkTravelTimeAndDisutility implements TravelTime, TravelDisutility {
    private final TransitRouterConfig transitRouterConfig;
    private final TravelTime travelTime;
    private final LeastCostPathCalculator leastCostPathCalculator;
    private final ElectricFleetSpecification electricFleetSpecification;
    private final DriveEnergyConsumption.Factory driveConsumptionFactory;

    public TransitRouterNetworkTravelTimeAndDisutility(TransitRouterConfig transitRouterConfig,
                                                      TravelTime travelTime,
                                                      LeastCostPathCalculator leastCostPathCalculator,
                                                      ElectricFleetSpecification electricFleetSpecification,
                                                      DriveEnergyConsumption.Factory driveConsumptionFactory) {
        this.transitRouterConfig = transitRouterConfig;
        this.travelTime = travelTime;
        this.leastCostPathCalculator = leastCostPathCalculator;
        this.electricFleetSpecification = electricFleetSpecification;
        this.driveConsumptionFactory = driveConsumptionFactory;
    }

    @Override
    public double getLinkTravelTime(Link link, double time, Person person, Vehicle vehicle) {
        // Use the provided travel time for the link
        return travelTime.getLinkTravelTime(link, time, person, vehicle);
    }

    @Override
    public double getLinkTravelDisutility(Link link, double time, Person person, Vehicle vehicle) {
        // Calculate the base travel disutility (e.g., travel time)
        double travelTime = getLinkTravelTime(link, time, person, vehicle);
        double baseDisutility = transitRouterConfig.getMarginalUtilityOfTravelTimePt_utl_s() * travelTime;

        // Add energy-related disutility (e.g., energy consumption)
        if (electricFleetSpecification.getVehicleSpecifications().containsKey(vehicle.getId())) {
            double energyConsumption = driveConsumptionFactory.create((ElectricVehicle) vehicle).calcEnergyConsumption(link, travelTime ,time);
            double energyDisutility = transitRouterConfig.getMarginalUtilityOfTravelDistancePt_utl_m() * energyConsumption;
            baseDisutility += energyDisutility;
        }

        return baseDisutility;
    }

    @Override
    public double getLinkMinimumTravelDisutility(Link link) {
        // Return the minimum possible disutility for the link
        return transitRouterConfig.getMarginalUtilityOfTravelTimePt_utl_s() * link.getLength() / link.getFreespeed();
    }
}
