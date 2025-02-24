package evTransitRouter;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.matsim.api.core.v01.network.Network;
import org.matsim.api.core.v01.population.Population;
import org.matsim.contrib.ev.EvConfigGroup;
import org.matsim.contrib.ev.discharging.AuxEnergyConsumption;
import org.matsim.contrib.ev.discharging.DriveEnergyConsumption;
import org.matsim.contrib.ev.fleet.ElectricFleetSpecification;
import org.matsim.contrib.ev.infrastructure.ChargingInfrastructureSpecification;
import org.matsim.core.config.Config;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.network.algorithms.TransportModeNetworkFilter;
import org.matsim.core.router.SingleModeNetworksCache;
import org.matsim.core.router.costcalculators.TravelDisutilityFactory;
import org.matsim.core.router.util.LeastCostPathCalculator;
import org.matsim.core.router.util.LeastCostPathCalculatorFactory;
import org.matsim.core.router.util.TravelTime;
import org.matsim.pt.router.TransitRouter;
import org.matsim.pt.router.TransitRouterConfig;

import com.google.inject.Inject;
import com.google.inject.Provider;

public class EvTransitRouterProvider implements Provider<TransitRouter> {
    private static final Logger log = LogManager.getLogger(EvTransitRouterProvider.class);

    private final String mode;
    private final String routingMode;

    @Inject
    private Map<String, TravelTime> travelTimes;

    @Inject
    private Map<String, TravelDisutilityFactory> travelDisutilityFactories;

    @Inject
    private Config config;

    @Inject
    private Network network;

    @Inject
    private Population populationFactory;

    @Inject
    private LeastCostPathCalculatorFactory leastCostPathCalculatorFactory;

    @Inject
    private ElectricFleetSpecification electricFleetSpecification;

    @Inject
    private ChargingInfrastructureSpecification chargingInfrastructureSpecification;

    @Inject
    private DriveEnergyConsumption.Factory driveConsumptionFactory;

    @Inject
    private AuxEnergyConsumption.Factory auxConsumptionFactory;

    @Inject
    private TransitRouterConfig transitRouterConfig;

	@Inject
	private SingleModeNetworksCache singleModeNetworksCache;
	
	public EvTransitRouterProvider(String mode) {
		this(mode, mode);
	}

    public EvTransitRouterProvider(String mode, String routingMode) {
        this.mode = mode;
        this.routingMode = routingMode;
    }

    @Override
    public TransitRouter get() {
        log.debug("Creating EV Transit Router for mode=" + mode + ", routingMode=" + routingMode);
        
    	Network filteredNetwork;

		// Ensure this is not performed concurrently by multiple threads!
		synchronized (this.singleModeNetworksCache.getSingleModeNetworksCache()) {

			filteredNetwork = this.singleModeNetworksCache.getSingleModeNetworksCache().get(mode);
			if (filteredNetwork == null) {
				TransportModeNetworkFilter filter = new TransportModeNetworkFilter(network);
				Set<String> modes = new HashSet<>();
				modes.add(mode);
				filteredNetwork = NetworkUtils.createNetwork(config);
				filter.filter(filteredNetwork, modes);
				this.singleModeNetworksCache.getSingleModeNetworksCache().put(mode, filteredNetwork);
			}
		}

        // Get travel time and disutility for the routing mode
        TravelTime travelTime = travelTimes.get(routingMode);
        if (travelTime == null) {
            throw new RuntimeException("No TravelTime bound for mode " + routingMode + ".");
        }

        TravelDisutilityFactory travelDisutilityFactory = travelDisutilityFactories.get(routingMode);
        if (travelDisutilityFactory == null) {
            throw new RuntimeException("No TravelDisutilityFactory bound for mode " + routingMode + ".");
        }

        // Create a least cost path calculator for the transit router network
        LeastCostPathCalculator leastCostPathCalculator = leastCostPathCalculatorFactory.createPathCalculator(
        		filteredNetwork,
                travelDisutilityFactory.createTravelDisutility(travelTime),
                travelTime
        );

        // Create the transit router travel time and disutility
        TransitRouterNetworkTravelTimeAndDisutility transitRouterTravelTimeAndDisutility =
                new TransitRouterNetworkTravelTimeAndDisutility(transitRouterConfig, travelTime, leastCostPathCalculator, electricFleetSpecification, driveConsumptionFactory);

        // Create the EV Transit Router
        return new EvTransitRouterModule (
                transitRouterConfig,
                filteredNetwork,
                transitRouterTravelTimeAndDisutility,
                populationFactory,
                electricFleetSpecification,
                chargingInfrastructureSpecification,
                driveConsumptionFactory,
                auxConsumptionFactory,
                EvConfigGroup.get(config)
        );
    }
}
