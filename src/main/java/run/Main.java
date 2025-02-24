package run;

import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.TransportMode;
import org.matsim.contrib.ev.EvConfigGroup;
import org.matsim.contrib.ev.EvModule;
import org.matsim.contrib.ev.routing.EvNetworkRoutingProvider;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.config.groups.RoutingConfigGroup;
import org.matsim.core.config.groups.RoutingConfigGroup.TeleportedModeParams;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.controler.Controler;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.router.costcalculators.TravelDisutilityFactory;
import org.matsim.core.router.util.TravelTime;
import org.matsim.core.scenario.ScenarioUtils;

import com.google.inject.name.Names;

public class Main {

    public static void main(String[] args) {
        // Load EV configuration group
        EvConfigGroup evGroup = new EvConfigGroup();
        Config config = ConfigUtils.loadConfig("scenarios\\simple_pt\\config.xml", evGroup);

        // Set output directory and overwrite settings
        config.controller().setOutputDirectory("D:\\EV Transit\\simple_pt_output");
        config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.deleteDirectoryIfExists);

        // Load the scenario
        Scenario scenario = ScenarioUtils.loadScenario(config);
        
        RoutingConfigGroup routingConfig = config.routing();
        routingConfig.clearTeleportedModeParams();

        // Add teleportation parameters only for the modes you want (e.g., walk, bike)
        TeleportedModeParams walkParams = new TeleportedModeParams(TransportMode.walk);
        walkParams.setTeleportedModeSpeed(3.0 / 3.6); // 3.0 km/h --> m/s
        routingConfig.addTeleportedModeParams(walkParams);

        TeleportedModeParams bikeParams = new TeleportedModeParams(TransportMode.bike);
        bikeParams.setTeleportedModeSpeed(15.0 / 3.6); // 15.0 km/h --> m/s
        routingConfig.addTeleportedModeParams(bikeParams);

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
        	@Override
        	public void install() {
        	    // Install the EV module
        	    install(new EvModule());

        	    bind(TravelTime.class).annotatedWith(Names.named("pt")).to(org.matsim.core.trafficmonitoring.FreeSpeedTravelTime.class);

        	    // Bind the custom travel disutility factory for the "pt" mode
        	    bind(TravelDisutilityFactory.class).annotatedWith(Names.named("pt")).toInstance(customPtTravelDisutilityFactory);
        	    
        	    addRoutingModuleBinding( TransportMode.pt ).toProvider( new EvNetworkRoutingProvider( TransportMode.pt ) );
        	}
        });
  

        // Run the simulation
        controler.run();
    }
}