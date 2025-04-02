# 🚌 Electric Bus and Transit Module in MATSim ⚡

This repository contains an **Electric Bus and Transit Module** for **MATSim** (Multi-Agent Transport Simulation), a widely used open-source framework for simulating large-scale transportation systems. This module integrates electric buses into the MATSim ecosystem, enabling the simulation of electric public transit systems—charging infrastructure, energy consumption, and scheduling included.

---

## 📑 Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## 📌 Introduction

This project extends MATSim's capabilities to support electric bus simulation within public transit networks, including:

- ⚡ **Electric bus energy consumption**
- 🏙️ **Charging infrastructure placement and scheduling**
- 🕒 **Operational impact on transit systems and the energy grid**

It is particularly useful for **researchers**, **urban planners**, and **policymakers** exploring sustainable public transport solutions.

---

## 🚀 Features

- **Electric Bus Energy Consumption Model**  
  Simulates energy use based on route, traffic, and vehicle parameters.

- **Charging Infrastructure Support**  
  Models charging stations at depots, hubs, and on-route points.

- **Charging Scheduling**  
  Minimises downtime and ensures bus availability through optimised scheduling.

- **Full Integration with MATSim Transit**  
  Works seamlessly with existing MATSim transit features.

- **Scenario Analysis Tools**  
  Evaluate fleet configurations, battery capacities, and charging setups.

---

## 🔧 Installation

To install and build the module:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/prvnpandey/EvTransitMatsim.git
   cd EvTransitMatsim
   ```

2. **Install dependencies**:  
   Make sure [MATSim](https://www.matsim.org/) is installed.

3. **Build with Maven**:
   ```bash
   mvn clean install
   ```

4. **Run simulations**:  
   Use example config files in `src/main/resources`.

---

## ▶️ Usage

To simulate electric bus transit:

### 1. Prepare Input Data

- Transit schedule (MATSim format)
- Electric bus specs (e.g., battery capacity, consumption rates)
- Charging station locations/specs

### 2. Configure the Simulation

Update your `config.xml` with electric bus settings:

```xml
<module name="electric bus">
    <param name="batteryCapacity" value="300" /> <!-- in kWh -->
    <param name="charging power" value="150" /> <!-- in kW -->
    <param name="chargingStationsFile" value="path/to/charging/stations.xml" />
</module>
```

### 3. Run the Simulation

```bash
java -cp matsim-electric-bus.jar org.matsim.run.Controller config.xml
```

### 4. Analyse Results

Results include:

- 📊 Energy consumption reports  
- ⚡ Charging logs  
- 🚏 Transit performance metrics

---

## 🤝 Contributing

We welcome contributions! To get started:

1. **Fork the repository**
2. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Commit changes**:
   ```bash
   git commit -m "Add your commit message here"
   ```
4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
5. **Open a Pull Request** on GitHub

Please follow the coding standards and include documentation with your contributions.

---

## 📄 License

Licensed under the **GNU General Public License v3.0**.  
See the [LICENSE](./LICENSE) file for details.

---

## 🙏 Acknowledgements

- The **MATSim community** for providing a robust simulation platform.
- All **contributors** for their valuable input and efforts.

---

For questions or suggestions, feel free to **open an issue** or contact the maintainers. Happy simulating! 🚌⚡
