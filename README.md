#Electric Bus and Transit Module in MATSim
This repository contains the implementation and contribution of an Electric Bus and Transit Module for MATSim (Multi-Agent Transport Simulation), a widely used open-source framework for simulating large-scale transportation systems. The module integrates electric buses into the MATSim ecosystem, enabling the simulation of electric public transit systems, including charging infrastructure, energy consumption, and scheduling.

#Table of Contents
Introduction

Features

Installation

Usage

Contributing

License

Acknowledgments

#Introduction

The goal of this project is to extend MATSim's capabilities to support the simulation of electric buses and their integration into public transit networks. This includes modeling:

##Electric bus energy consumption.

##Charging infrastructure placement and scheduling.

##Impact of electric buses on transit operations and energy grids.

This module is particularly useful for researchers, urban planners, and policymakers interested in evaluating the feasibility and impact of transitioning to electric public transit systems.

#Features
Electric Bus Energy Consumption Model: Simulates the energy consumption of electric buses based on route characteristics, traffic conditions, and vehicle specifications.

Charging Infrastructure: Supports the placement and operation of charging stations at transit hubs, depots, and along routes.

Charging Scheduling: Optimizes charging schedules to minimize downtime and ensure bus availability.

Integration with MATSim Transit: Seamlessly integrates with MATSim's existing transit simulation capabilities.

Scenario Analysis: Enables comparison of different electric bus deployment strategies, such as battery size, charging locations, and fleet composition.

#Installation
To use this module, follow these steps:

#Clone the Repository:

bash
Copy
git clone https://github.com/prvnpandey/EvTransitMatsim.git
cd EvTransitMatsim
Install Dependencies:
Ensure you have MATSim installed. You can download MATSim from the official website.

Build the Module:
Use Maven to build the project:

bash
Copy
mvn clean install
Run Simulations:
Use the provided configuration files to run simulations. Example configurations are located in the src/main/resources directory.

Usage
To run a simulation with the Electric Bus and Transit Module:

Prepare Input Data:

Transit schedule (in MATSim format).

Electric bus specifications (e.g., battery capacity, energy consumption rates).

Charging station locations and specifications.

Configure Simulation:
Modify the config.xml file to include electric bus and charging parameters. Example:

xml
Copy
<module name="electricBus">
    <param name="batteryCapacity" value="300" /> <!-- in kWh -->
    <param name="chargingPower" value="150" /> <!-- in kW -->
    <param name="chargingStationsFile" value="path/to/charging/stations.xml" />
</module>
Run HTML
Run the Simulation:
Execute the simulation using the MATSim command-line interface:

bash
Copy
java -cp matsim-electric-bus.jar org.matsim.run.Controler config.xml
Analyze Results:
Output files will include energy consumption statistics, charging logs, and transit performance metrics.

Contributing
We welcome contributions to this project! If you'd like to contribute, please follow these steps:

Fork the repository.

Create a new branch for your feature or bugfix:

bash
Copy
git checkout -b feature/your-feature-name
Commit your changes:

bash
Copy
git commit -m "Add your commit message here"
Push your branch:

bash
Copy
git push origin feature/your-feature-name
Open a pull request on GitHub.

Please ensure your code follows the project's coding standards and includes appropriate documentation.

#License

This project is licensed under the GNU General Public License v3.0. See the LICENSE file for details.

#Acknowledgments

The MATSim community for providing a robust and extensible simulation framework.

Contributors to this project for their valuable input and efforts.

For questions or feedback, please open an issue or contact the maintainers.

Happy simulating! 🚌⚡