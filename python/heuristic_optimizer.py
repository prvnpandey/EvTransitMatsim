import numpy as np
import pandas as pd
import pyomo.environ as pyo
from typing import List, Tuple, Dict
from optimizer_functions import optimization
import random
from collections import defaultdict

class BusSchedulingHeuristic:
    def __init__(
        self,
        trip_start: list[int],
        trip_end: list[int],
        alpha: list[float],
        gamma: list[float],
        C_bat: list[float],
        P: list[float],
        E_0: float = 0.20,
        E_min: float = 0.20,
        E_max: float = 1.00,
        E_end: float = 0.20,
        delta_t: float = 0.25
    ):
        self.trip_start = trip_start
        self.trip_end = trip_end
        self.alpha = alpha
        self.gamma = gamma
        self.C_bat = C_bat
        self.P = P
        self.E_0 = E_0
        self.E_min = E_min
        self.E_max = E_max
        self.E_end = E_end
        self.delta_t = delta_t
        
        self.num_trips = len(trip_start)
        self.num_buses = len(C_bat)
        self.num_chargers = len(alpha)
        self.time_steps = len(P) if len(P) > max(trip_end) else max(trip_end)
        
        # Initialize best solution tracking
        self.best_cost = float('inf')
        self.best_solution = None

    def _check_trip_compatibility(self, trip1_idx: int, trip2_idx: int) -> bool:
        """Check if two trips can be served by the same bus sequentially"""
        if trip1_idx == trip2_idx:
            return False
        return self.trip_end[trip1_idx] <= self.trip_start[trip2_idx]

    def _calculate_energy_feasibility(self, trip_sequence: List[int], bus_idx: int) -> bool:
        """Check if a sequence of trips is feasible regarding energy constraints for a given bus"""
        current_energy = self.C_bat[bus_idx] * self.E_0
        min_energy = self.C_bat[bus_idx] * self.E_min
        
        for trip_idx in trip_sequence:
            # Calculate energy consumption for the trip
            trip_duration = self.trip_end[trip_idx] - self.trip_start[trip_idx]
            energy_consumption = self.gamma[trip_idx] * trip_duration * self.delta_t
            
            # Update energy level
            current_energy -= energy_consumption
            
            # Check if energy level is feasible
            if current_energy < min_energy:
                return False
        
        # Check final SOC requirement
        return current_energy >= self.C_bat[bus_idx] * self.E_end

    def _construct_initial_solution(self) -> Dict[int, List[int]]:
        """
        Construct initial solution using a greedy approach
        Returns: Dictionary mapping bus indices to their assigned trip sequences
        """
        unassigned_trips = list(range(self.num_trips))
        bus_assignments = defaultdict(list)
        
        # Sort trips by start time
        unassigned_trips.sort(key=lambda x: self.trip_start[x])
        
        for trip_idx in unassigned_trips:
            assigned = False
            
            # Try to assign to existing bus routes
            for bus_idx in range(self.num_buses):
                current_sequence = bus_assignments[bus_idx]
                
                # Check if trip can be added to this bus's sequence
                if not current_sequence or (
                    self._check_trip_compatibility(current_sequence[-1], trip_idx) and
                    self._calculate_energy_feasibility(current_sequence + [trip_idx], bus_idx)
                ):
                    bus_assignments[bus_idx].append(trip_idx)
                    assigned = True
                    break
            
            # If trip couldn't be assigned to any existing bus, create new assignment
            if not assigned:
                for bus_idx in range(self.num_buses):
                    if bus_idx not in bus_assignments:
                        bus_assignments[bus_idx] = [trip_idx]
                        assigned = True
                        break
                        
            if not assigned:
                raise ValueError("Not enough buses to cover all trips")
                
        return bus_assignments

    def _optimize_charging_schedule(self, bus_assignments: Dict[int, List[int]]):
        """
        Optimize charging schedule for a given bus-trip assignment using relaxed binary variables
        """
        # Create binary assignment matrices based on the bus_assignments
        b_matrix = np.zeros((self.num_buses, self.num_trips, self.time_steps))
        
        # Fill the b_matrix based on bus_assignments
        for bus_idx, trips in bus_assignments.items():
            for trip_idx in trips:
                b_matrix[bus_idx, trip_idx, self.trip_start[trip_idx]:self.trip_end[trip_idx]] = 1
                
        # Solve relaxed optimization problem for charging schedule
        try:
            model = optimization(
                self.trip_start,
                self.trip_end,
                self.alpha,
                self.gamma,
                self.C_bat,
                self.P,
                self.E_0,
                self.E_min,
                self.E_max,
                self.E_end,
                self.delta_t,
                relaxed_binary=True  # Use relaxed binary variables
            )
            
            # Fix the bus assignment variables according to our solution
            for k in model.K:
                for i in model.I:
                    for t in model.T:
                        model.b[k,i,t].fix(b_matrix[k-1,i-1,t-1])
            
            # Solve the reduced problem
            solver = pyo.SolverFactory('glpk')
            result = solver.solve(model)
            
            if result.solver.status == pyo.SolverStatus.ok:
                cost = pyo.value(model.obj)
                if cost < self.best_cost:
                    self.best_cost = cost
                    self.best_solution = (bus_assignments, model)
                return cost
            
        except Exception as e:
            print(f"Optimization failed: {e}")
            return float('inf')
        
        return float('inf')

    def _local_search(self, current_solution: Dict[int, List[int]], max_iterations: int = 100):
        """
        Perform local search to improve the solution
        """
        current_cost = self._optimize_charging_schedule(current_solution)
        
        for _ in range(max_iterations):
            # Randomly select two buses
            bus1, bus2 = random.sample(list(current_solution.keys()), 2)
            
            # Try swapping random trips between buses
            if current_solution[bus1] and current_solution[bus2]:
                idx1 = random.randint(0, len(current_solution[bus1])-1)
                idx2 = random.randint(0, len(current_solution[bus2])-1)
                
                # Create new solution with swapped trips
                new_solution = current_solution.copy()
                new_solution[bus1] = current_solution[bus1].copy()
                new_solution[bus2] = current_solution[bus2].copy()
                new_solution[bus1][idx1], new_solution[bus2][idx2] = new_solution[bus2][idx2], new_solution[bus1][idx1]
                
                # Check if new solution is feasible and better
                if (self._calculate_energy_feasibility(new_solution[bus1], bus1) and 
                    self._calculate_energy_feasibility(new_solution[bus2], bus2)):
                    new_cost = self._optimize_charging_schedule(new_solution)
                    
                    if new_cost < current_cost:
                        current_solution = new_solution
                        current_cost = new_cost
                        print(f"Found better solution with cost: {current_cost}")
        
        return current_solution

    def solve(self, max_iterations: int = 100) -> Tuple[Dict[int, List[int]], float]:
        """
        Main solving method that combines construction and local search
        """
        # Phase 1: Construct initial solution
        initial_solution = self._construct_initial_solution()
        
        # Phase 2: Improve solution with local search
        final_solution = self._local_search(initial_solution, max_iterations)
        
        return self.best_solution, self.best_cost

def solve_large_instance(
    trip_start: list[int],
    trip_end: list[int],
    alpha: list[float],
    gamma: list[float],
    C_bat: list[float],
    P: list[float],
    E_0: float = 0.20,
    E_min: float = 0.20,
    E_max: float = 1.00,
    E_end: float = 0.20,
    delta_t: float = 0.25,
    max_iterations: int = 100
) -> Tuple[Dict[int, List[int]], float]:
    """
    Wrapper function to solve large instances using the heuristic approach
    
    Returns:
        Tuple containing:
        - Dictionary mapping bus indices to their assigned trip sequences
        - Best objective value found (total energy cost)
    """
    heuristic = BusSchedulingHeuristic(
        trip_start, trip_end, alpha, gamma, C_bat, P,
        E_0, E_min, E_max, E_end, delta_t
    )
    return heuristic.solve(max_iterations)