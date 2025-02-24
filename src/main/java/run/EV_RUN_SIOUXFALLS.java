package run;


import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.TransportMode;
import org.matsim.contrib.ev.EvConfigGroup;
import org.matsim.contrib.ev.EvModule;
import org.matsim.contrib.ev.routing.EvNetworkRoutingProvider;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.config.groups.RoutingConfigGroup.TeleportedModeParams;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.controler.Controler;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.router.RoutingModule;
import org.matsim.core.router.costcalculators.TravelDisutilityFactory;
import org.matsim.core.router.util.TravelTime;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.utils.objectattributes.ObjectAttributes;

import com.google.inject.Provider;
import com.google.inject.name.Names;

import evTransitRouter.EvTransitRouterProvider;

public class EV_RUN_SIOUXFALLS {

    public static void main(String[] args) {
        // Load EV configuration group
        EvConfigGroup evGroup = new EvConfigGroup();
        Config config = ConfigUtils.loadConfig("scenarios\\siouxfall-2014\\config_ev.xml", evGroup);
        

        // Set output directory and overwrite settings
        config.controller().setOutputDirectory("D:\\EV Transit\\simple_pt_output");
        config.controller().setLastIteration(1);
  
        config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.deleteDirectoryIfExists);
     
        // Load the scenario
        Scenario scenario = ScenarioUtils.loadScenario(config);
        AddInitialSoc.addInitialSoc(scenario.getVehicles());

        config.routing().clearTeleportedModeParams();
        // Add teleportation parameters only for the modes you want (e.g., walk, bike)
        TeleportedModeParams walkParams = new TeleportedModeParams(TransportMode.walk);
        walkParams.setTeleportedModeSpeed(3.0 / 3.6); // 3.0 km/h --> m/s
        config.routing().addTeleportedModeParams(walkParams);

        TeleportedModeParams bikeParams = new TeleportedModeParams(TransportMode.bike);
        bikeParams.setTeleportedModeSpeed(15.0 / 3.6); // 15.0 km/h --> m/s
        config.routing().addTeleportedModeParams(bikeParams);

        // Create an instance of the custom travel disutility factory
        CustomPtTravelDisutilityFactory customPtTravelDisutilityFactory = new CustomPtTravelDisutilityFactory(
            1.0, // Weight for in-vehicle time
            2.0, // Weight for waiting time
            3.0, // Weight for transfer penalty
            4.0  // Weight for fare
        );

        // Create the controler
        Controler controler = new Controler(scenario);

        // Add overriding modules
        controler.addOverridingModule(new AbstractModule() {
        	@SuppressWarnings("unchecked")
			@Override
        	public void install() {
        	    // Install the EV module
        	    install(new EvModule());

        	    bind(TravelTime.class).annotatedWith(Names.named("pt")).to(org.matsim.core.trafficmonitoring.FreeSpeedTravelTime.class);

        	    // Bind the custom travel disutility factory for the "pt" mode
        	    bind(TravelDisutilityFactory.class).annotatedWith(Names.named("pt")).toInstance(customPtTravelDisutilityFactory);
        	    
        	    addRoutingModuleBinding( TransportMode.pt ).toProvider( (Provider<? extends RoutingModule>) new EvTransitRouterProvider( TransportMode.pt ) );
        	}
        });
  

        // Run the simulation
        controler.run();
    }
}
