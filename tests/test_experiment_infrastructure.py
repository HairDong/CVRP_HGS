import unittest
from pathlib import Path

from CVRP_TS_ALNS_v2 import (
    HybridMemeticCVRP,
    Individual,
    build_dist,
    parse_vrp_file,
    validate_solution,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_DIR / "Dataset-VRP"


class ExperimentInfrastructureTests(unittest.TestCase):
    def test_parser_uses_internal_instance_name_and_vehicle_limit(self):
        dataset = parse_vrp_file(str(DATASET_DIR / "A-n44-k7.vrp"))[0]
        self.assertEqual(dataset["label"], "A-n44-k6")
        self.assertEqual(dataset["num_vehicles"], 6)
        self.assertEqual(dataset["bks"], 937.0)

    def test_vehicle_limit_is_a_hard_feasibility_condition(self):
        validation = validate_solution(
            routes=[[1], [2]],
            demands=[0, 1, 1],
            capacity=1,
            max_vehicles=1,
        )
        self.assertFalse(validation["feasible"])
        self.assertEqual(validation["excess_load"], 0)
        self.assertEqual(validation["excess_vehicles"], 1)

        dist = build_dist([(0, 0), (1, 0), (0, 1)])
        individual = Individual(
            [[1], [2]], dist, [0, 1, 1], 1, 1, penalty_cap=10)
        self.assertFalse(individual.is_feasible)
        self.assertEqual(individual.total_violation, 1)
        self.assertEqual(individual.pen_cost, individual.cost + 10)

    def test_adaptive_removal_grows_with_stagnation(self):
        coords = [(0, 0)] + [(i, 0) for i in range(1, 31)]
        solver = HybridMemeticCVRP(
            build_dist(coords),
            [0] + [1] * 30,
            capacity=10,
            num_vehicles=3,
            k_destroy=6,
            adaptive_removal=True,
        )
        solver._restart_threshold = 500
        solver._stagnation = 0
        self.assertEqual(solver._current_destroy_size(), 6)
        solver._stagnation = 250
        self.assertEqual(solver._current_destroy_size(), 8)
        solver._stagnation = 500
        self.assertEqual(solver._current_destroy_size(), 10)

        solver.adaptive_removal = False
        self.assertEqual(solver._current_destroy_size(), 6)


if __name__ == "__main__":
    unittest.main()
