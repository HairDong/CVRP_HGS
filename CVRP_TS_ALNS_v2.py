"""
CVRP_TS_ALNS.py  v2.0
=====================
Hybrid Memetic CVRP Solver
  TS + ALNS refinement  +  HGS-inspired population search

Combines:
  - Tabu Search (Kir et al., 2017) for neighbourhood exploration
  - ALNS destroy/repair operators for diversification
  - HGS-inspired techniques (Vidal, 2022):
      * Small elite population with biased fitness
      * Order Crossover (OX) + Split DP
      * Adaptive penalty for infeasible solutions
      * Granular neighbourhood restriction
      * Broken-pairs diversity metric

Architecture:
  1. Initial population  (HGS + multi-start NN)
  2. Main loop (time-limited):
     a) Select two parents via binary tournament (biased fitness)
     b) OX crossover -> offspring giant tour -> Split DP -> routes
     c) ALNS destroy/repair perturbation
     d) Fast local search (granular 2-opt, relocate, swap, 2-opt*)
     e) Tabu acceptance criterion
     f) Add to population, manage diversity/penalty
  3. Return best feasible solution
"""

import math
import random
import time
import json
import sys
import os
import io
from copy import deepcopy

# -- UTF-8 on Windows --
if sys.platform == "win32":
    try:
        import ctypes as _ct
        _ct.windll.kernel32.SetConsoleOutputCP(65001)
        _ct.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    elif hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    elif hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                      errors="replace", line_buffering=True)
except Exception:
    pass


# ================================================================
#  CONSTANTS
# ================================================================
_EPS = 1e-9
_INF = float("inf")


# ================================================================
#  DISTANCE & COST UTILITIES
# ================================================================

def euclidean(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def build_dist(coords, integer_round=True):
    """
    Build distance matrix.  coords[0]=depot, coords[1..n]=customers.
    integer_round=True: TSPLIB EUC_2D nint = int(d + 0.5).
    """
    n = len(coords)
    if integer_round:
        return [[int(euclidean(coords[i], coords[j]) + 0.5)
                 for j in range(n)] for i in range(n)]
    return [[euclidean(coords[i], coords[j]) for j in range(n)] for i in range(n)]


def route_cost(route, dist):
    if not route:
        return 0.0
    c = dist[0][route[0]]
    for i in range(len(route) - 1):
        c += dist[route[i]][route[i + 1]]
    c += dist[route[-1]][0]
    return c


def total_cost(routes, dist):
    return sum(route_cost(r, dist) for r in routes)


def route_demand(route, demands):
    return sum(demands[c] for c in route)


def solution_violations(routes, demands, capacity, max_vehicles):
    """Return capacity and fleet-size violations for a route set."""
    nonempty = [r for r in routes if r]
    excess_load = sum(
        max(0, route_demand(r, demands) - capacity) for r in nonempty)
    excess_vehicles = max(0, len(nonempty) - max_vehicles)
    return excess_load, excess_vehicles


def validate_solution(routes, demands, capacity, max_vehicles):
    """Validate all CVRP hard constraints and customer coverage."""
    nonempty = [list(r) for r in routes if r]
    n_customers = len(demands) - 1
    flattened = [customer for route in nonempty for customer in route]
    expected = set(range(1, n_customers + 1))
    observed = set(flattened)
    duplicates = len(flattened) - len(observed)
    missing = sorted(expected - observed)
    invalid = sorted(observed - expected)
    excess_load, excess_vehicles = solution_violations(
        nonempty, demands, capacity, max_vehicles)
    feasible = (
        not missing
        and not invalid
        and duplicates == 0
        and excess_load == 0
        and excess_vehicles == 0
    )
    return {
        "feasible": feasible,
        "route_count": len(nonempty),
        "excess_load": excess_load,
        "excess_vehicles": excess_vehicles,
        "missing_customers": missing,
        "invalid_customers": invalid,
        "duplicate_count": duplicates,
    }


def format_routes(routes, cust_names):
    lines = []
    for i, r in enumerate(routes):
        if r:
            stops = " -> ".join(cust_names[c - 1] for c in r)
            lines.append(f"  Xe {i + 1}: Depot -> {stops} -> Depot")
        else:
            lines.append(f"  Xe {i + 1}: (khong su dung)")
    return "\n".join(lines)


# ================================================================
#  VRP FILE PARSER
# ================================================================

def parse_vrp_file(filepath: str, seed=1) -> list:
    """Read TSPLIB .vrp file and return dataset list."""
    import re
    coords_raw, demands_raw = {}, {}
    capacity, depot_id = None, 1
    filename_label = os.path.splitext(os.path.basename(filepath))[0]
    instance_name = None
    num_vehicles = None
    bks = None
    edge_weight_type = None
    section = None

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line == "EOF":
                continue
            if line.startswith("NAME"):
                instance_name = line.split(":", 1)[1].strip(); continue
            if line.startswith("EDGE_WEIGHT_TYPE"):
                edge_weight_type = line.split(":", 1)[1].strip(); continue
            if line.startswith("CAPACITY"):
                capacity = int(line.split(":")[1].strip()); continue
            if line.startswith("COMMENT"):
                m = re.search(r"(?:Min\s+)?No of trucks\s*:\s*(\d+)",
                              line, re.IGNORECASE)
                if m:
                    num_vehicles = int(m.group(1))
                m = re.search(r"(?:Optimal value|Best Value)\s*:\s*([0-9.]+)",
                              line, re.IGNORECASE)
                if m:
                    bks = float(m.group(1))
                continue
            if line.startswith("NODE_COORD_SECTION"): section = "coords"; continue
            if line.startswith("DEMAND_SECTION"): section = "demands"; continue
            if line.startswith("DEPOT_SECTION"): section = "depot"; continue
            if section == "coords":
                p = line.split()
                if len(p) >= 3: coords_raw[int(p[0])] = [float(p[1]), float(p[2])]
            elif section == "demands":
                p = line.split()
                if len(p) >= 2: demands_raw[int(p[0])] = int(p[1])
            elif section == "depot":
                p = line.split()
                if p and p[0].lstrip("-").isdigit():
                    v = int(p[0])
                    if v > 0: depot_id = v

    label = instance_name or filename_label
    if num_vehicles is None:
        m = re.search(r"-k(\d+)$", label, re.IGNORECASE)
        if m:
            num_vehicles = int(m.group(1))
    if capacity is None:
        raise ValueError(f"Missing CAPACITY in {filepath}")
    if num_vehicles is None:
        raise ValueError(
            f"Cannot determine vehicle limit K for {filepath}; "
            "add it to COMMENT or NAME (for example, -k5).")
    if edge_weight_type and edge_weight_type.upper() != "EUC_2D":
        raise ValueError(
            f"Unsupported EDGE_WEIGHT_TYPE={edge_weight_type!r} in {filepath}; "
            "this solver currently implements TSPLIB EUC_2D rounding only.")
    if depot_id not in coords_raw:
        raise ValueError(f"Depot {depot_id} has no coordinates in {filepath}")

    depot_coord = coords_raw[depot_id]
    customers = []
    for nid in sorted(coords_raw.keys()):
        if nid == depot_id: continue
        if nid not in demands_raw:
            raise ValueError(f"Node {nid} has no demand in {filepath}")
        customers.append({"name": f"C{nid-1}", "coord": coords_raw[nid],
                          "demand": demands_raw[nid]})
    return [{"label": label, "source_file": os.path.abspath(filepath),
             "depot": depot_coord, "customers": customers,
             "vehicle_capacity": capacity, "num_vehicles": num_vehicles,
             "edge_weight_type": edge_weight_type or "EUC_2D",
             "bks": bks, "seed": seed}]


# ================================================================
#  [HGS-INSPIRED]  GRANULAR NEIGHBOURHOOD
# ================================================================

def build_granular_neighbors(dist, n_cust, nb_granular=20):
    """
    For each customer i (1..n), keep only nb_granular nearest customers.
    Inspired by HGS: reduces local-search complexity from O(n^2) to O(n*G).
    """
    neighbors = [[] for _ in range(n_cust + 1)]
    for i in range(1, n_cust + 1):
        dists = [(dist[i][j], j) for j in range(1, n_cust + 1) if j != i]
        dists.sort()
        neighbors[i] = [j for _, j in dists[:nb_granular]]
    return neighbors


# ================================================================
#  INITIAL SOLUTION: Nearest-Neighbor
# ================================================================

def nearest_neighbor_solution(dist, demands, capacity, num_vehicles, seed=42):
    rng = random.Random(seed)
    n = len(demands) - 1
    unvisited = list(range(1, n + 1))
    routes, loads = [], []

    while unvisited and len(routes) < num_vehicles:
        route, load = [], 0
        start = rng.choice(unvisited)
        unvisited.remove(start)
        route.append(start); load += demands[start]; current = start
        while unvisited:
            nearest, nd = None, _INF
            for c in unvisited:
                if load + demands[c] <= capacity and dist[current][c] < nd:
                    nd = dist[current][c]; nearest = c
            if nearest is None: break
            unvisited.remove(nearest)
            route.append(nearest); load += demands[nearest]; current = nearest
        routes.append(route); loads.append(load)

    for c in unvisited:
        placed = False
        for ri in range(len(routes)):
            if loads[ri] + demands[c] <= capacity:
                routes[ri].append(c); loads[ri] += demands[c]; placed = True; break
        if not placed:
            routes.append([c]); loads.append(demands[c])
    while len(routes) < num_vehicles:
        routes.append([])
    return routes


# ================================================================
#  [HGS-INSPIRED]  SPLIT ALGORITHM  (Giant tour -> Routes)
# ================================================================

def split_routes(giant_tour, dist, demands, capacity, penalty_cap=100.0):
    """
    Split algorithm: giant tour -> optimal routes.
    Uses O(n) linear Split with deque-based dominance (Vidal 2016)
    when no duration constraints, falls back to O(n²) Bellman otherwise.
    Allows slight infeasibility penalised by penalty_cap.
    """
    n = len(giant_tour)
    if n == 0:
        return [[]]

    # Precompute prefix sums for the linear Split
    # sumLoad[i] = total demand of giant_tour[0..i-1]
    sumLoad = [0.0] * (n + 1)
    sumDist = [0.0] * (n + 1)  # sum of consecutive distances in tour
    d0 = [0.0] * (n + 1)       # dist(depot, giant_tour[i])
    d_0 = [0.0] * (n + 1)      # dist(giant_tour[i], depot)
    for i in range(1, n + 1):
        c = giant_tour[i - 1]
        sumLoad[i] = sumLoad[i - 1] + demands[c]
        d0[i] = dist[0][c]
        d_0[i] = dist[c][0]
        if i > 1:
            sumDist[i] = sumDist[i - 1] + dist[giant_tour[i - 2]][c]
        else:
            sumDist[i] = 0.0

    pot = [_INF] * (n + 1)  # potential[i] = min cost to serve tour[0..i-1]
    pred = [-1] * (n + 1)
    pot[0] = 0.0

    def propagate(j, i):
        """Cost of route serving giant_tour[j..i-1] starting from pot[j]."""
        if pot[j] >= _INF:
            return _INF
        load = sumLoad[i] - sumLoad[j]
        route_dist = d0[j + 1] + (sumDist[i] - sumDist[j + 1]) + d_0[i]
        pen = penalty_cap * max(0.0, load - capacity)
        return pot[j] + route_dist + pen

    def dominates(j1, j2):
        """Does j1 dominate j2 as predecessor? (j1 always better for any future i)"""
        return propagate(j1, j2 + 1) < propagate(j2, j2 + 1) - _EPS

    def dominates_right(j1, j2):
        """Does j2 dominate j1 from the right of the deque?"""
        # j2 dominates j1 if for all future i, propagate(j2,i) <= propagate(j1,i)
        # This is checked by seeing if j2 is better at j2+1
        return propagate(j2, j2 + 1) < propagate(j1, j2 + 1) + _EPS

    # Linear split using monotone deque
    # Deque stores candidate predecessors
    deque = [0]  # initial: only position 0
    head, tail = 0, 0  # deque[head..tail]

    for i in range(1, n + 1):
        # Front of deque is best predecessor for i
        pot[i] = propagate(deque[head], i)
        pred[i] = deque[head]

        if i < n:
            # Remove dominated elements from back
            while tail >= head and dominates_right(deque[tail], i):
                tail -= 1
            tail += 1
            if tail >= len(deque):
                deque.append(i)
            else:
                deque[tail] = i

            # Remove dominated elements from front
            while tail > head and propagate(deque[head], i + 1) > propagate(deque[head + 1], i + 1) - _EPS:
                head += 1

            # Safety: if load becomes too large, skip forward
            # (handles infeasible regions)

    # Fallback to quadratic Bellman if linear split failed
    if pot[n] >= _INF:
        pot = [_INF] * (n + 1)
        pred = [-1] * (n + 1)
        pot[0] = 0.0
        for i in range(n):
            load = 0.0
            cost_seg = 0.0
            prev_node = 0
            for j in range(i, n):
                cust = giant_tour[j]
                load += demands[cust]
                cost_seg += dist[prev_node][cust]
                prev_node = cust
                route_c = cost_seg + dist[cust][0]
                pen = penalty_cap * max(0.0, load - capacity)
                total = pot[i] + route_c + pen
                if total < pot[j + 1] - _EPS:
                    pot[j + 1] = total
                    pred[j + 1] = i
                if load > 1.5 * capacity:
                    break

    # Backtrack
    routes = []
    cur = n
    while cur > 0:
        p = pred[cur]
        routes.append(giant_tour[p:cur])
        cur = p
    routes.reverse()
    return routes


# ================================================================
#  [HGS-INSPIRED]  ORDER CROSSOVER (OX)
# ================================================================

def crossover_ox(parent1_routes, parent2_routes, dist, demands, capacity,
                 penalty_cap, rng):
    """
    OX crossover on giant tours, then Split to routes.
    Inspired by HGS Genetic.cpp crossoverOX.
    """
    tour1 = [c for r in parent1_routes for c in r]
    tour2 = [c for r in parent2_routes for c in r]
    n = len(tour1)
    if n <= 2:
        return split_routes(list(tour1), dist, demands, capacity, penalty_cap)

    # Random segment from parent1
    a = rng.randint(0, n - 1)
    b = rng.randint(0, n - 1)
    if a > b: a, b = b, a
    if a == b:
        b = min(b + 1, n - 1)

    child = [0] * n
    in_seg = set()
    for k in range(a, b + 1):
        child[k] = tour1[k]
        in_seg.add(tour1[k])

    # Fill remaining positions from parent2 in order
    pos = (b + 1) % n
    for k in range(n):
        gene = tour2[(b + 1 + k) % n]
        if gene not in in_seg:
            child[pos] = gene
            pos = (pos + 1) % n

    return split_routes(child, dist, demands, capacity, penalty_cap)


# ================================================================
#  [HGS-INSPIRED]  INDIVIDUAL & POPULATION
# ================================================================

class Individual:
    """
    Solution representation with evaluation.
    Inspired by HGS Individual.h.
    """
    __slots__ = ("routes", "cost", "excess_load", "excess_vehicles",
                 "total_violation", "max_vehicles", "pen_cost",
                 "is_feasible", "successors", "biased_fitness")

    def __init__(self, routes, dist, demands, capacity, max_vehicles,
                 penalty_cap):
        self.routes = [list(r) for r in routes if r]
        self.max_vehicles = max_vehicles
        self.cost = total_cost(self.routes, dist)
        self.excess_load, self.excess_vehicles = solution_violations(
            self.routes, demands, capacity, max_vehicles)
        # One excess route is scaled by Q so both violation types use the
        # same adaptive lambda without making fleet-size violations negligible.
        self.total_violation = (
            self.excess_load + capacity * self.excess_vehicles)
        self.pen_cost = self.cost + penalty_cap * self.total_violation
        self.is_feasible = self.total_violation < _EPS
        # Build successor map for diversity metric
        n = sum(len(r) for r in self.routes)
        self.successors = {}
        for r in self.routes:
            for k in range(len(r)):
                self.successors[r[k]] = r[k + 1] if k + 1 < len(r) else 0
        self.biased_fitness = 0.0

    def re_eval(self, dist, demands, capacity, penalty_cap):
        self.cost = total_cost(self.routes, dist)
        self.excess_load, self.excess_vehicles = solution_violations(
            self.routes, demands, capacity, self.max_vehicles)
        self.total_violation = (
            self.excess_load + capacity * self.excess_vehicles)
        self.pen_cost = self.cost + penalty_cap * self.total_violation
        self.is_feasible = self.total_violation < _EPS
        self.successors = {}
        for r in self.routes:
            for k in range(len(r)):
                self.successors[r[k]] = r[k + 1] if k + 1 < len(r) else 0


def broken_pairs_distance(ind1, ind2):
    """
    Normalised broken-pairs distance between two individuals.
    Inspired by HGS Population.cpp brokenPairsDistance.
    """
    diff = 0
    total = 0
    for c, s in ind1.successors.items():
        total += 1
        s2 = ind2.successors.get(c)
        if s2 is None or (s != s2):
            diff += 1
    return diff / max(total, 1)


class Population:
    """
    Small elite population with biased fitness selection.
    Inspired by HGS Population management.

    - Separate feasible / infeasible sub-populations
    - Biased fitness = quality_rank + diversity_weight * diversity_rank
    - Binary tournament selection
    - Clone removal
    """

    def __init__(self, mu=8, nb_elite=2, nb_close=3):
        self.mu = mu
        self.nb_elite = nb_elite
        self.nb_close = nb_close
        self.feasible: list[Individual] = []
        self.infeasible: list[Individual] = []
        self.best_feasible: Individual | None = None

    def _update_biased_fitness(self, subpop):
        if len(subpop) <= 1:
            for ind in subpop: ind.biased_fitness = 0.0
            return
        # Diversity ranking
        div_scores = []
        for ind in subpop:
            dists = sorted(broken_pairs_distance(ind, o)
                           for o in subpop if o is not ind)
            avg_close = (sum(dists[:self.nb_close]) / min(self.nb_close, len(dists))
                         if dists else 0.0)
            div_scores.append((avg_close, ind))
        div_scores.sort(key=lambda x: -x[0])  # high diversity first
        div_rank = {id(x[1]): i for i, x in enumerate(div_scores)}

        # Quality ranking (already sorted by pen_cost)
        sz = len(subpop)
        elite_ratio = self.nb_elite / sz if sz > self.nb_elite else 1.0
        for qi, ind in enumerate(subpop):
            qr = qi / max(sz - 1, 1)
            dr = div_rank[id(ind)] / max(sz - 1, 1)
            ind.biased_fitness = qr + (1.0 - elite_ratio) * dr

    def add(self, ind: Individual) -> bool:
        """Add individual to appropriate sub-population. Returns True if new best."""
        subpop = self.feasible if ind.is_feasible else self.infeasible
        # Insert sorted by pen_cost
        pos = 0
        for i, x in enumerate(subpop):
            if ind.pen_cost < x.pen_cost - _EPS:
                pos = i; break
        else:
            pos = len(subpop)
        subpop.insert(pos, ind)

        # Trim if too large
        if len(subpop) > self.mu * 2:
            self._trim(subpop)

        # Track best feasible
        new_best = False
        if ind.is_feasible:
            if self.best_feasible is None or ind.cost < self.best_feasible.cost - _EPS:
                self.best_feasible = ind
                new_best = True
        return new_best

    def _trim(self, subpop):
        """Remove worst biased-fitness individuals until size <= mu."""
        while len(subpop) > self.mu:
            self._update_biased_fitness(subpop)
            # Find worst (highest biased_fitness), prefer clones
            worst_idx, worst_bf, worst_clone = -1, -_INF, False
            for i in range(1, len(subpop)):  # skip best (i=0)
                is_clone = any(broken_pairs_distance(subpop[i], subpop[j]) < 0.01
                               for j in range(len(subpop)) if j != i)
                bf = subpop[i].biased_fitness
                if (is_clone and not worst_clone) or \
                   (is_clone == worst_clone and bf > worst_bf):
                    worst_idx, worst_bf, worst_clone = i, bf, is_clone
            if worst_idx >= 0:
                subpop.pop(worst_idx)

    def select_parents(self, rng) -> tuple[Individual, Individual]:
        """Binary tournament on combined population."""
        combined = self.feasible + self.infeasible
        if len(combined) < 2:
            return combined[0], combined[0]
        self._update_biased_fitness(self.feasible)
        self._update_biased_fitness(self.infeasible)

        def tournament():
            a, b = rng.sample(combined, min(2, len(combined)))
            return a if a.biased_fitness <= b.biased_fitness else b

        p1 = tournament()
        p2 = tournament()
        # Ensure different parents
        for _ in range(5):
            if p2 is not p1: break
            p2 = tournament()
        return p1, p2

    def re_eval_infeasible(self, dist, demands, capacity, penalty_cap):
        """Re-evaluate infeasible pop after penalty change. Inspired by HGS."""
        for ind in self.infeasible:
            ind.re_eval(dist, demands, capacity, penalty_cap)
        self.infeasible.sort(key=lambda x: x.pen_cost)
        # Check if any became feasible
        newly_feasible = [x for x in self.infeasible if x.is_feasible]
        self.infeasible = [x for x in self.infeasible if not x.is_feasible]
        for ind in newly_feasible:
            self.add(ind)


# ================================================================
#  [HGS-INSPIRED]  ADAPTIVE PENALTY
# ================================================================

class AdaptivePenalty:
    """
    Dynamic penalty for capacity violation.
    Inspired by HGS managePenalties.
    Target: ~20% feasible offspring.
    """

    def __init__(self, init_penalty=100.0, target_feas=0.20,
                 increase=1.2, decrease=0.85):
        self.penalty = init_penalty
        self.target = target_feas
        self.increase = increase
        self.decrease = decrease
        self.history: list[bool] = []
        self.window = 100

    def record(self, is_feasible: bool):
        self.history.append(is_feasible)
        if len(self.history) > self.window:
            self.history.pop(0)

    def adapt(self) -> float:
        if len(self.history) < 10:
            return self.penalty
        frac = sum(self.history) / len(self.history)
        if frac < self.target - 0.05:
            self.penalty = min(self.penalty * self.increase, 100000.0)
        elif frac > self.target + 0.05:
            self.penalty = max(self.penalty * self.decrease, 0.1)
        return self.penalty


# ================================================================
#  ALNS DESTROY OPERATORS
# ================================================================

def destroy_random_removal(routes, demands, capacity, k, rng):
    cands = [(r, p) for r, route in enumerate(routes) for p in range(len(route))]
    k = min(k, len(cands))
    if k == 0: return [list(r) for r in routes], []
    sel = rng.sample(cands, k)
    removed = [routes[r][p] for r, p in sel]
    rm_set = set(sel)
    new_routes = [[c for p, c in enumerate(route) if (ri, p) not in rm_set]
                  for ri, route in enumerate(routes)]
    return new_routes, removed


def destroy_worst_removal(routes, dist, demands, capacity, k, rng):
    cands = []
    for ri, route in enumerate(routes):
        for pos, c in enumerate(route):
            prev = route[pos - 1] if pos > 0 else 0
            nxt  = route[pos + 1] if pos < len(route) - 1 else 0
            mg = dist[prev][c] + dist[c][nxt] - dist[prev][nxt]
            cands.append((mg, ri, pos, c))
    cands.sort(reverse=True)
    k = min(k, len(cands))
    rm_set = {(r, p) for _, r, p, _ in cands[:k]}
    removed = [c for _, _, _, c in cands[:k]]
    new_routes = [[c for p, c in enumerate(route) if (ri, p) not in rm_set]
                  for ri, route in enumerate(routes)]
    return new_routes, removed


def destroy_shaw_removal(routes, dist, demands, capacity, k, rng):
    """
    Shaw removal: remove related customers (similar distance, demand).
    More sophisticated than cluster removal.
    """
    cands = [(ri, p, route[p])
             for ri, route in enumerate(routes) for p in range(len(route))]
    if not cands: return [list(r) for r in routes], []
    seed_ri, seed_p, seed_c = rng.choice(cands)
    # Score = alpha*distance + beta*demand_diff
    alpha, beta = 0.7, 0.3
    max_dem = max(demands[c] for _, _, c in cands) or 1
    max_dist_val = max(dist[seed_c][c] for _, _, c in cands) or 1
    scored = []
    for ri, p, c in cands:
        if c == seed_c: scored.append((0.0, ri, p, c)); continue
        d_norm = dist[seed_c][c] / max_dist_val
        dem_norm = abs(demands[c] - demands[seed_c]) / max_dem
        scored.append((alpha * d_norm + beta * dem_norm, ri, p, c))
    scored.sort()
    k = min(k, len(scored))
    rm_set = {(r, p) for _, r, p, _ in scored[:k]}
    removed = [c for _, _, _, c in scored[:k]]
    new_routes = [[c for p, c in enumerate(route) if (ri, p) not in rm_set]
                  for ri, route in enumerate(routes)]
    return new_routes, removed


# ================================================================
#  ALNS REPAIR OPERATORS
# ================================================================

def repair_greedy_insertion(routes, removed, dist, demands, capacity, rng):
    rng.shuffle(removed)
    new_routes = [list(r) for r in routes]
    for city in removed:
        best_d, best_r, best_p = _INF, -1, 0
        for ri, route in enumerate(new_routes):
            if route_demand(route, demands) + demands[city] > capacity:
                continue
            for pos in range(len(route) + 1):
                prev = route[pos - 1] if pos > 0 else 0
                nxt  = route[pos] if pos < len(route) else 0
                d = dist[prev][city] + dist[city][nxt] - dist[prev][nxt]
                if d < best_d: best_d, best_r, best_p = d, ri, pos
        if best_r == -1:
            best_r = min(range(len(new_routes)),
                         key=lambda x: route_demand(new_routes[x], demands))
            best_p = len(new_routes[best_r])
        new_routes[best_r].insert(best_p, city)
    return new_routes


def repair_regret2_insertion(routes, removed, dist, demands, capacity, rng):
    """
    Regret-2 insertion: insert customer with highest regret
    (difference between 2nd-best and best insertion cost).
    """
    new_routes = [list(r) for r in routes]
    remaining = list(removed)
    rng.shuffle(remaining)

    while remaining:
        best_regret, best_city, best_r, best_p = -_INF, -1, -1, 0
        for city in remaining:
            costs = []  # (insertion_cost, route_idx, pos)
            for ri, route in enumerate(new_routes):
                if route_demand(route, demands) + demands[city] > capacity:
                    continue
                for pos in range(len(route) + 1):
                    prev = route[pos - 1] if pos > 0 else 0
                    nxt  = route[pos] if pos < len(route) else 0
                    d = dist[prev][city] + dist[city][nxt] - dist[prev][nxt]
                    costs.append((d, ri, pos))
            if not costs:
                # Fallback: squeeze into least-loaded route
                ri = min(range(len(new_routes)),
                         key=lambda x: route_demand(new_routes[x], demands))
                costs = [(0.0, ri, len(new_routes[ri]))]
            costs.sort()
            c1 = costs[0][0]
            c2 = costs[1][0] if len(costs) > 1 else c1 + 100.0
            regret = c2 - c1
            if regret > best_regret:
                best_regret = regret
                best_city = city
                best_r = costs[0][1]
                best_p = costs[0][2]
        remaining.remove(best_city)
        new_routes[best_r].insert(best_p, best_city)
    return new_routes


# ================================================================
#  FAST LOCAL SEARCH  (HGS-inspired, array-based, optimized for Python)
# ================================================================
#  Key HGS techniques ported:
#    - Move types: relocate-1, relocate-pair, swap-1-1, swap-2-1, Or-opt
#    - SWAP* with granular filtering + best-insertion cache
#    - Customer-to-route index for O(1) lookup
#    - Granular neighbourhood restriction
#    - Early delta pruning
#    - Restart-on-improvement loop
#    - 2-opt* (cross-exchange of tails)
# ================================================================

def _fast_local_search(routes, dist, demands, capacity, granular_nb,
                       penalty_cap=100.0, max_rounds=5):
    """
    Array-based local search with multiple move types + SWAP*.
    Optimized for Python while incorporating HGS algorithmic ideas.
    """
    n_cust = len(demands) - 1

    def pen_load(load):
        return penalty_cap * max(0.0, load - capacity)

    # Work with mutable route lists
    R = [list(r) for r in routes]

    # Build customer -> (route_idx, position) lookup
    cust_loc = {}  # cust -> (ri, pos)
    route_loads = []
    for ri, route in enumerate(R):
        ld = sum(demands[c] for c in route)
        route_loads.append(ld)
        for pos, c in enumerate(route):
            cust_loc[c] = (ri, pos)

    def _rebuild_lookup():
        """Rebuild lookup after moves."""
        cust_loc.clear()
        route_loads.clear()
        for ri, route in enumerate(R):
            ld = sum(demands[c] for c in route)
            route_loads.append(ld)
            for pos, c in enumerate(route):
                cust_loc[c] = (ri, pos)

    # Pre-convert granular_nb to sets for O(1) membership test
    gnb_set = [None]  # index 0 unused (depot)
    for i in range(1, n_cust + 1):
        if i < len(granular_nb):
            gnb_set.append(set(granular_nb[i]))
        else:
            gnb_set.append(set())

    # Build route-pair adjacency from granular neighbours (for SWAP*)
    def _get_adjacent_route_pairs():
        pairs = set()
        for c in range(1, n_cust + 1):
            if c not in cust_loc:
                continue
            rc = cust_loc[c][0]
            for v in gnb_set[c]:
                if v in cust_loc:
                    rv = cust_loc[v][0]
                    if rv != rc:
                        pairs.add((min(rc, rv), max(rc, rv)))
        return pairs

    for _round in range(max_rounds):
        improved = False

        # ============================================================
        # Pass 1: Intra-route 2-opt (granular) + Or-opt (delta-based)
        # ============================================================
        for ri in range(len(R)):
            route = R[ri]
            nr = len(route)
            if nr < 3:
                continue
            imp = True
            while imp:
                imp = False
                # 2-opt
                for i in range(nr - 1):
                    ci = route[i]
                    nbs = gnb_set[ci] if ci <= n_cust else set()
                    for j in range(i + 2, nr):
                        cj = route[j]
                        if cj not in nbs and ci not in gnb_set[cj]:
                            continue
                        a = route[i - 1] if i > 0 else 0
                        b = route[j + 1] if j + 1 < nr else 0
                        delta = dist[a][cj] + dist[ci][b] - dist[a][ci] - dist[cj][b]
                        if delta < -_EPS:
                            route[i:j+1] = route[i:j+1][::-1]
                            imp = True
                            improved = True
                            break
                    if imp:
                        break
                if imp:
                    nr = len(route)
                    continue
                # Or-opt: relocate segment of 1, 2, or 3 within route
                for seg_len in (1, 2, 3):
                    if nr < seg_len + 2:
                        continue
                    found = False
                    for i in range(nr - seg_len + 1):
                        seg = route[i:i+seg_len]
                        s0 = seg[0]
                        s_last = seg[-1]
                        prev_s = route[i-1] if i > 0 else 0
                        next_s = route[i+seg_len] if i+seg_len < nr else 0
                        # Precompute segment internal cost (constant)
                        seg_int = 0.0
                        for si in range(seg_len - 1):
                            seg_int += dist[seg[si]][seg[si+1]]
                        # Removal saving
                        saving = (dist[prev_s][s0] + seg_int + dist[s_last][next_s]
                                  - dist[prev_s][next_s])
                        # Build shrunk route once
                        tmp = route[:i] + route[i+seg_len:]
                        nt = len(tmp)
                        # Find best insertion in shrunk route
                        best_ic, best_p = _INF, -1
                        for p in range(nt + 1):
                            a2 = tmp[p-1] if p > 0 else 0
                            b2 = tmp[p] if p < nt else 0
                            ic = dist[a2][s0] + seg_int + dist[s_last][b2] - dist[a2][b2]
                            if ic < best_ic:
                                best_ic, best_p = ic, p
                        if best_ic - saving < -_EPS and best_p >= 0:
                            R[ri] = tmp[:best_p] + seg + tmp[best_p:]
                            route = R[ri]
                            nr = len(route)
                            imp = True
                            improved = True
                            found = True
                            break
                    if found:
                        break

        if improved:
            _rebuild_lookup()

        # ============================================================
        # Pass 2: Inter-route moves (granular, randomized order)
        #   relocate-1, relocate-pair, swap-1-1, swap-2-1,
        #   inter-route Or-opt (seg 2-3)
        # ============================================================
        inter_improved = False
        customers = list(range(1, n_cust + 1))
        # Rotate start position each round to avoid bias
        offset = (_round * 7) % max(n_cust, 1)
        customers = customers[offset:] + customers[:offset]

        for uI in customers:
            if uI not in cust_loc:
                continue
            rU, pU = cust_loc[uI]
            routeU = R[rU]
            if pU >= len(routeU) or routeU[pU] != uI:
                _rebuild_lookup()
                if uI not in cust_loc:
                    continue
                rU, pU = cust_loc[uI]
                routeU = R[rU]

            prevU = routeU[pU - 1] if pU > 0 else 0
            nextU = routeU[pU + 1] if pU + 1 < len(routeU) else 0
            loadU = demands[uI]
            remU = dist[prevU][uI] + dist[uI][nextU] - dist[prevU][nextU]

            hasX = (pU + 1 < len(routeU))
            if hasX:
                xI = routeU[pU + 1]
                nextX = routeU[pU + 2] if pU + 2 < len(routeU) else 0
                loadX = demands[xI]
                remUX = dist[prevU][uI] + dist[xI][nextX] - dist[prevU][nextX]
            else:
                xI, nextX, loadX = 0, 0, 0
                remUX = 0.0

            penU_curr = pen_load(route_loads[rU])

            nbs = gnb_set[uI] if uI <= n_cust else set()
            for vI in nbs:
                if vI not in cust_loc:
                    continue
                rV, pV = cust_loc[vI]
                if rV == rU:
                    continue
                routeV = R[rV]
                if pV >= len(routeV) or routeV[pV] != vI:
                    continue

                prevV = routeV[pV - 1] if pV > 0 else 0
                nextV = routeV[pV + 1] if pV + 1 < len(routeV) else 0
                loadV = demands[vI]
                penV_curr = pen_load(route_loads[rV])

                # ---- Move 1: Relocate U after V ----
                if uI != nextV:
                    ins1 = dist[vI][uI] + dist[uI][nextV] - dist[vI][nextV]
                    delta1 = ins1 - remU
                    newPenU = pen_load(route_loads[rU] - loadU)
                    newPenV = pen_load(route_loads[rV] + loadU)
                    total1 = delta1 + newPenU + newPenV - penU_curr - penV_curr
                    if total1 < -_EPS:
                        routeU.pop(pU)
                        route_loads[rU] -= loadU
                        new_pos = cust_loc[vI][1] + 1
                        R[cust_loc[vI][0]].insert(new_pos, uI)
                        route_loads[cust_loc[vI][0]] += loadU
                        _rebuild_lookup()
                        inter_improved = True
                        improved = True
                        break

                # ---- Move 2: Relocate pair (U, X) after V ----
                if hasX and uI != nextV and vI != xI:
                    ins2 = dist[vI][uI] + dist[xI][nextV] - dist[vI][nextV]
                    delta2 = ins2 - remUX
                    newPenU2 = pen_load(route_loads[rU] - loadU - loadX)
                    newPenV2 = pen_load(route_loads[rV] + loadU + loadX)
                    total2 = delta2 + newPenU2 + newPenV2 - penU_curr - penV_curr
                    if total2 < -_EPS:
                        routeU.pop(pU + 1)
                        routeU.pop(pU)
                        route_loads[rU] -= loadU + loadX
                        rV2, pV2 = cust_loc[vI]
                        R[rV2].insert(pV2 + 1, uI)
                        R[rV2].insert(pV2 + 2, xI)
                        route_loads[rV2] += loadU + loadX
                        _rebuild_lookup()
                        inter_improved = True
                        improved = True
                        break

                # ---- Move 4: Swap U and V (1-1) ----
                if uI != prevV and uI != nextV:
                    costSuppU = dist[prevU][vI] + dist[vI][nextU] - dist[prevU][uI] - dist[uI][nextU]
                    costSuppV = dist[prevV][uI] + dist[uI][nextV] - dist[prevV][vI] - dist[vI][nextV]
                    delta4 = costSuppU + costSuppV
                    newPenU4 = pen_load(route_loads[rU] - loadU + loadV)
                    newPenV4 = pen_load(route_loads[rV] - loadV + loadU)
                    total4 = delta4 + newPenU4 + newPenV4 - penU_curr - penV_curr
                    if total4 < -_EPS:
                        routeU[pU] = vI
                        routeV[pV] = uI
                        route_loads[rU] += loadV - loadU
                        route_loads[rV] += loadU - loadV
                        _rebuild_lookup()
                        inter_improved = True
                        improved = True
                        break

                # ---- Move 5: Swap (U,X) and V (2-1) ----
                if (hasX and vI != xI
                        and uI != prevV and xI != prevV and uI != nextV):
                    costSuppU5 = (dist[prevU][vI] + dist[vI][nextX]
                                  - dist[prevU][uI] - dist[xI][nextX])
                    costSuppV5 = (dist[prevV][uI] + dist[xI][nextV]
                                  - dist[prevV][vI] - dist[vI][nextV])
                    delta5 = costSuppU5 + costSuppV5
                    newPenU5 = pen_load(route_loads[rU] - loadU - loadX + loadV)
                    newPenV5 = pen_load(route_loads[rV] - loadV + loadU + loadX)
                    total5 = delta5 + newPenU5 + newPenV5 - penU_curr - penV_curr
                    if total5 < -_EPS:
                        routeU.pop(pU + 1)
                        routeU[pU] = vI
                        route_loads[rU] += loadV - loadU - loadX
                        routeV[pV] = uI
                        routeV.insert(pV + 1, xI)
                        route_loads[rV] += loadU + loadX - loadV
                        _rebuild_lookup()
                        inter_improved = True
                        improved = True
                        break

            if inter_improved:
                break

        if inter_improved:
            continue  # restart round

        # ============================================================
        # Pass 3: SWAP* with granular route-pair filtering
        #   Only check route pairs connected by granular neighbours.
        #   Precompute removal deltas + best insertion.
        #   Uses lower-bound pruning for speed.
        # ============================================================
        swap_star_improved = False
        adj_pairs = _get_adjacent_route_pairs()

        for ri, rj in adj_pairs:
            if ri >= len(R) or rj >= len(R):
                continue
            rI = R[ri]
            rJ = R[rj]
            if not rI or not rJ:
                continue

            best_delta, best_move = _INF, None
            penI = pen_load(route_loads[ri])
            penJ = pen_load(route_loads[rj])

            # Precompute removal deltas for route I
            rem_I = []
            for pi in range(len(rI)):
                ci = rI[pi]
                prev_i = rI[pi-1] if pi > 0 else 0
                next_i = rI[pi+1] if pi+1 < len(rI) else 0
                rem_I.append(dist[prev_i][ci] + dist[ci][next_i] - dist[prev_i][next_i])

            # Precompute removal deltas for route J
            rem_J = []
            for pj in range(len(rJ)):
                cj = rJ[pj]
                prev_j = rJ[pj-1] if pj > 0 else 0
                next_j = rJ[pj+1] if pj+1 < len(rJ) else 0
                rem_J.append(dist[prev_j][cj] + dist[cj][next_j] - dist[prev_j][next_j])

            # Precompute best insertion cost INTO rI and INTO rJ
            # for any customer (cached per-route, not per-customer)
            def _best_ins_into(cust, route):
                best_ic, best_p = _INF, 0
                for p in range(len(route) + 1):
                    prev = route[p-1] if p > 0 else 0
                    nxt = route[p] if p < len(route) else 0
                    ic = dist[prev][cust] + dist[cust][nxt] - dist[prev][nxt]
                    if ic < best_ic:
                        best_ic, best_p = ic, p
                return best_ic, best_p

            # Check relocate ci -> rJ (for each ci in rI)
            for pi in range(len(rI)):
                ci = rI[pi]
                dPenI_rel = pen_load(route_loads[ri] - demands[ci]) - penI
                dPenJ_rel = pen_load(route_loads[rj] + demands[ci]) - penJ
                lb = -rem_I[pi] + dPenI_rel + dPenJ_rel
                if lb < best_delta:
                    ins_cost, ins_pos = _best_ins_into(ci, rJ)
                    delta = -rem_I[pi] + ins_cost + dPenI_rel + dPenJ_rel
                    if delta < best_delta:
                        best_delta = delta
                        best_move = ("relocate_ij", pi, ins_pos)

            # Check relocate cj -> rI (for each cj in rJ)
            for pj in range(len(rJ)):
                cj = rJ[pj]
                dPenI_r = pen_load(route_loads[ri] + demands[cj]) - penI
                dPenJ_r = pen_load(route_loads[rj] - demands[cj]) - penJ
                lb = -rem_J[pj] + dPenI_r + dPenJ_r
                if lb < best_delta:
                    ins_cost, ins_pos = _best_ins_into(cj, rI)
                    delta = -rem_J[pj] + ins_cost + dPenI_r + dPenJ_r
                    if delta < best_delta:
                        best_delta = delta
                        best_move = ("relocate_ji", pj, ins_pos)

            # Check SWAP* for each pair (ci, cj) - only granular-connected
            for pi in range(len(rI)):
                ci = rI[pi]
                nb_ci = gnb_set[ci] if ci <= n_cust else set()
                for pj in range(len(rJ)):
                    cj = rJ[pj]
                    if cj not in nb_ci and ci not in gnb_set[cj]:
                        continue

                    dPenI = pen_load(route_loads[ri] + demands[cj] - demands[ci]) - penI
                    dPenJ = pen_load(route_loads[rj] + demands[ci] - demands[cj]) - penJ

                    # Lower bound filter
                    if -rem_I[pi] - rem_J[pj] + dPenI + dPenJ >= best_delta:
                        continue

                    # Best insertion of ci into rJ (with cj removed)
                    rJ_tmp = rJ[:pj] + rJ[pj+1:]
                    best_ci_ins, best_ci_pos = _best_ins_into(ci, rJ_tmp)

                    # Best insertion of cj into rI (with ci removed)
                    rI_tmp = rI[:pi] + rI[pi+1:]
                    best_cj_ins, best_cj_pos = _best_ins_into(cj, rI_tmp)

                    delta = -rem_I[pi] + best_ci_ins - rem_J[pj] + best_cj_ins + dPenI + dPenJ
                    if delta < best_delta:
                        best_delta = delta
                        best_move = ("swap_star", pi, pj, best_cj_pos, best_ci_pos)

            if best_delta < -_EPS and best_move:
                if best_move[0] == "swap_star":
                    _, pi, pj, cj_pos, ci_pos = best_move
                    ci = rI[pi]; cj = rJ[pj]
                    rI_new = rI[:pi] + rI[pi+1:]
                    rJ_new = rJ[:pj] + rJ[pj+1:]
                    rI_new.insert(cj_pos, cj)
                    rJ_new.insert(ci_pos, ci)
                    R[ri] = rI_new; R[rj] = rJ_new
                elif best_move[0] == "relocate_ij":
                    _, pi, ins_pos = best_move
                    ci = rI[pi]
                    rI.pop(pi)
                    R[rj].insert(ins_pos, ci)
                elif best_move[0] == "relocate_ji":
                    _, pj, ins_pos = best_move
                    cj = rJ[pj]
                    rJ.pop(pj)
                    R[ri].insert(ins_pos, cj)
                _rebuild_lookup()
                swap_star_improved = True
                improved = True
                break

        if swap_star_improved:
            continue

        # ============================================================
        # Pass 4: 2-opt* (cross-exchange of tails) - granular filtered
        # ============================================================
        cross_done = False
        adj_pairs_cross = _get_adjacent_route_pairs()
        for ri, rj in adj_pairs_cross:
            if ri >= len(R) or rj >= len(R):
                continue
            r1 = R[ri]
            r2 = R[rj]
            if not r1 or not r2:
                continue

            cum_d1 = [0] * (len(r1) + 1)
            for k in range(len(r1)):
                cum_d1[k+1] = cum_d1[k] + demands[r1[k]]
            load_r1 = cum_d1[len(r1)]

            cum_d2 = [0] * (len(r2) + 1)
            for k in range(len(r2)):
                cum_d2[k+1] = cum_d2[k] + demands[r2[k]]
            load_r2 = cum_d2[len(r2)]

            best_d, best_i, best_j = _EPS, -1, -1
            for i in range(len(r1) + 1):
                a1 = r1[i-1] if i > 0 else 0
                b1 = r1[i] if i < len(r1) else 0
                head1_load = cum_d1[i]
                tail1_load = load_r1 - head1_load
                for j in range(len(r2) + 1):
                    a2 = r2[j-1] if j > 0 else 0
                    b2 = r2[j] if j < len(r2) else 0
                    tail2_load = load_r2 - cum_d2[j]
                    nl1 = head1_load + tail2_load
                    nl2 = cum_d2[j] + tail1_load
                    old_pen = pen_load(load_r1) + pen_load(load_r2)
                    new_pen = pen_load(nl1) + pen_load(nl2)
                    old_e = dist[a1][b1] + dist[a2][b2]
                    new_e = dist[a1][b2] + dist[a2][b1]
                    delta = new_e - old_e + new_pen - old_pen
                    if -delta > best_d:
                        best_d = -delta
                        best_i, best_j = i, j
            if best_i >= 0:
                nr1 = r1[:best_i] + r2[best_j:]
                nr2 = r2[:best_j] + r1[best_i:]
                R[ri] = nr1
                R[rj] = nr2
                _rebuild_lookup()
                improved = True
                cross_done = True
                break
        if cross_done:
            continue

        break  # No improvement in any pass -> converged

    return [r for r in R if r]


# ================================================================
#  [HGS-INSPIRED]  DOUBLE-BRIDGE PERTURBATION
# ================================================================

def alns_double_bridge(routes, dist, demands, capacity, rng):
    """
    Double-bridge (4-opt) perturbation: reconnect giant tour at 4 random
    cut points to create a structurally diverse new solution.

    Classic escape move for instances with 80+ customers.
    Used in LKH and as a standard diversification move in memetic algorithms.
    """
    tour = [c for r in routes for c in r]
    n = len(tour)
    if n < 8:
        return [list(r) for r in routes]

    # Choose 4 distinct cut positions
    pos = sorted(rng.sample(range(1, n), min(4, n - 1)))
    while len(pos) < 4:
        pos.append(n)
    a, b, c, d = pos

    # Double-bridge reconnection:
    # Original : [0:a] + [a:b] + [b:c] + [c:d] + [d:]
    # New      : [0:a] + [c:d] + [b:c] + [a:b] + [d:]
    new_tour = tour[:a] + tour[c:d] + tour[b:c] + tour[a:b] + tour[d:]

    # Greedily split back into capacity-feasible routes
    result, cur, cur_load = [], [], 0
    for cust in new_tour:
        if cur_load + demands[cust] <= capacity:
            cur.append(cust)
            cur_load += demands[cust]
        else:
            if cur:
                result.append(cur)
            cur = [cust]
            cur_load = demands[cust]
    if cur:
        result.append(cur)
    return result


# ================================================================
#  ROUTE SEGMENT EXCHANGE (CROSS operator)
# ================================================================

def alns_segment_exchange(routes, dist, demands, capacity, rng):
    """
    Randomly select two routes and swap segments between them.
    This is a powerful diversification move that changes route structure
    without destroying the entire solution.
    """
    non_empty = [(i, r) for i, r in enumerate(routes) if len(r) >= 2]
    if len(non_empty) < 2:
        return [list(r) for r in routes]

    (ri, r1), (rj, r2) = rng.sample(non_empty, 2)
    r1, r2 = list(r1), list(r2)

    # Pick cut points in each route
    cut1 = rng.randint(1, len(r1) - 1)
    cut2 = rng.randint(1, len(r2) - 1)

    # Exchange tails
    nr1 = r1[:cut1] + r2[cut2:]
    nr2 = r2[:cut2] + r1[cut1:]

    new_routes = [list(r) for r in routes]
    new_routes[ri] = nr1
    new_routes[rj] = nr2
    return new_routes


# ================================================================
#  ALNS RELOCATION (from original paper)
# ================================================================

def alns_relocation(routes, dist, demands, capacity, rng):
    """Relocation procedure from Kir et al. (2017)."""
    new_routes = [list(r) for r in routes]
    all_customers = [c for r in new_routes for c in r]
    selected = []
    for ri, route in enumerate(new_routes):
        if route: selected.append((rng.choice(route), ri))

    for city, src_r in selected:
        if city not in new_routes[src_r]:
            found = False
            for ri, route in enumerate(new_routes):
                if city in route: src_r = ri; found = True; break
            if not found: continue

        # Second closest
        sorted_c = sorted([c for c in all_customers if c != city],
                          key=lambda c: dist[city][c])
        second = sorted_c[1] if len(sorted_c) >= 2 else (
            sorted_c[0] if sorted_c else None)
        if second is None: continue

        dst_r = None
        for ri, route in enumerate(new_routes):
            if second in route: dst_r = ri; break
        if dst_r is None or dst_r == src_r: continue
        if route_demand(new_routes[dst_r], demands) + demands[city] > capacity:
            continue

        src_pos = new_routes[src_r].index(city)
        new_routes[src_r].pop(src_pos)
        best_pos, best_d = 0, _INF
        dst_route = new_routes[dst_r]
        for pos in range(len(dst_route) + 1):
            prev = dst_route[pos - 1] if pos > 0 else 0
            nxt  = dst_route[pos] if pos < len(dst_route) else 0
            d = dist[prev][city] + dist[city][nxt] - dist[prev][nxt]
            if d < best_d: best_d, best_pos = d, pos
        new_routes[dst_r].insert(best_pos, city)

    return new_routes


# ================================================================
#  MAIN SOLVER CLASS
# ================================================================

class HybridMemeticCVRP:
    """
    Hybrid Memetic CVRP Solver.

    Architecture:
      1. Build initial population (HGS solution + NN multi-start)
      2. Main loop:
         a) [HGS] Select parents via binary tournament (biased fitness)
         b) [HGS] OX crossover -> Split -> routes
         c) [ALNS] Destroy/repair perturbation
         d) [TS/HGS] Fast granular local search
         e) [TS] Tabu acceptance criterion
         f) [HGS] Population management (diversity, penalty)
      3. Return best feasible solution

    Time-controlled: stops after time_limit seconds.
    """

    def __init__(self, dist, demands, capacity, num_vehicles,
                 # Population params (HGS-inspired)
                 pop_mu=8, nb_elite=2, nb_close=3,
                 # Penalty params (HGS-inspired)
                 init_penalty=100.0, target_feas=0.20,
                 # TS params
                 tabu_tenure=10, ml_tenure=5,
                 # ALNS params
                 k_destroy=6,
                 # Neighbourhood
                 nb_granular=20,
                 # HGS warm-start
                 vrp_filepath="", use_hgs_warmstart=False,
                 # Ablation controls
                 adaptive_penalty=True, adaptive_removal=True,
                 adaptive_operator_weights=True,
                 search_mode="full"):

        self.dist = dist
        self.demands = demands
        self.capacity = capacity
        self.num_vehicles = num_vehicles
        self.n_cust = len(demands) - 1
        self.vrp_filepath = vrp_filepath
        self.use_hgs_warmstart = use_hgs_warmstart
        self.adaptive_penalty = adaptive_penalty
        self.adaptive_removal = adaptive_removal
        self.adaptive_operator_weights = adaptive_operator_weights
        if search_mode not in {"full", "alns_only", "recombination_only"}:
            raise ValueError(
                "search_mode must be 'full', 'alns_only', or "
                "'recombination_only'")
        self.search_mode = search_mode

        # [HGS] Population
        self.population = Population(mu=pop_mu, nb_elite=nb_elite,
                                     nb_close=nb_close)
        # [HGS] Adaptive penalty
        self.penalty = AdaptivePenalty(init_penalty=init_penalty,
                                      target_feas=target_feas)

        # [TS] Tabu parameters
        self.tabu_tenure = tabu_tenure
        self.ml_tenure = ml_tenure

        # [ALNS] Destroy parameters
        self.k_destroy = k_destroy
        self._stagnation = 0
        self._restart_threshold = 1

        # [HGS] Granular neighbourhood
        self.granular_nb = build_granular_neighbors(dist, self.n_cust,
                                                    nb_granular)

        # ALNS operator weights (adaptive)
        self._d_ops = [
            ("Relocation",   lambda r, rng: alns_relocation(r, dist, demands, capacity, rng)),
            ("RandRemove",   lambda r, rng: self._destroy_repair(r, "rand", rng)),
            ("WorstRemove",  lambda r, rng: self._destroy_repair(r, "worst", rng)),
            ("ShawRemove",   lambda r, rng: self._destroy_repair(r, "shaw", rng)),
            # [Classic metaheuristics] Double-bridge: powerful escape for large instances
            ("DoubleBridge", lambda r, rng: alns_double_bridge(r, dist, demands, capacity, rng)),
            # Segment exchange between two routes (CROSS-like diversification)
            ("SegExchange",  lambda r, rng: alns_segment_exchange(r, dist, demands, capacity, rng)),
        ]
        self._d_weights = [2.0] * len(self._d_ops)
        self._d_usage = [0] * len(self._d_ops)
        self._d_success = [0] * len(self._d_ops)
        self._r_ops = [repair_greedy_insertion, repair_regret2_insertion]

        self.traj_cost = []

    def _current_destroy_size(self):
        # Adaptive destruction size. It grows linearly from the configured
        # base size to floor(n/3) as stagnation approaches the restart limit:
        # k = round(k0 + min(1, s/S) * (kmax-k0)).
        base_k = min(self.k_destroy, max(1, self.n_cust))
        if not self.adaptive_removal:
            return base_k
        max_k = max(base_k, self.n_cust // 3)
        stagnation_ratio = min(
            1.0, self._stagnation / max(self._restart_threshold, 1))
        return round(base_k + stagnation_ratio * (max_k - base_k))

    def _destroy_repair(self, routes, mode, rng):
        k = self._current_destroy_size()
        if mode == "rand":
            nr, rem = destroy_random_removal(routes, self.demands,
                                             self.capacity, k, rng)
        elif mode == "worst":
            nr, rem = destroy_worst_removal(routes, self.dist, self.demands,
                                            self.capacity, k, rng)
        else:
            nr, rem = destroy_shaw_removal(routes, self.dist, self.demands,
                                           self.capacity, k, rng)
        # Choose repair operator
        repair_fn = rng.choice(self._r_ops)
        return repair_fn(nr, rem, self.dist, self.demands, self.capacity, rng)

    def _roulette(self, weights, rng):
        total = sum(weights)
        r = rng.uniform(0.0, total)
        acc = 0.0
        for i, w in enumerate(weights):
            acc += w
            if r <= acc: return i
        return len(weights) - 1

    def _moved_customers(self, old_routes, new_routes):
        old_map = {}
        for ri, r in enumerate(old_routes):
            for c in r: old_map[c] = ri
        moved = set()
        for ri, r in enumerate(new_routes):
            for c in r:
                if old_map.get(c, -1) != ri: moved.add(c)
        return moved

    def _find_route(self, customer, routes):
        for ri, r in enumerate(routes):
            if customer in r: return ri
        return -1

    def _hgs_warmstart(self, time_budget, seed, verbose=False):
        """Run HGS C++ solver as warm-start for large instances.
        For very large instances, runs multiple seeds and returns the best.
        Returns list of route lists (customer indices 1-based) or None."""
        if not self.vrp_filepath or self.n_cust < 100:
            return None
        try:
            from hgs_python import HGS as _HGS, CVRPInstance as _CVRPInst
            inst = _CVRPInst.from_vrp_file(self.vrp_filepath)

            # For large instances, multi-seed HGS gets better results
            if self.n_cust > 200:
                n_seeds = max(2, int(time_budget / 60))
                per_seed = time_budget / n_seeds
            else:
                n_seeds = 1
                per_seed = time_budget

            best_sol = None
            for i in range(n_seeds):
                hgs = _HGS(inst, vrp_filepath=self.vrp_filepath)
                sol = hgs.solve(time_limit=per_seed, seed=seed + i,
                                verbose=False)
                if sol.routes and sol.cost < float('inf'):
                    if best_sol is None or sol.cost < best_sol.cost:
                        best_sol = sol
                    if verbose:
                        print(f"  [HGS seed={seed+i}] cost={sol.cost:.0f} "
                              f"({sol.time:.1f}s, {sol.backend})")

            if best_sol and best_sol.routes:
                if verbose:
                    print(f"  [HGS warm-start] best={best_sol.cost:.0f} "
                          f"({len(best_sol.routes)} routes, "
                          f"{n_seeds} seeds x {per_seed:.0f}s)")
                return best_sol.routes
        except Exception as e:
            if verbose:
                print(f"  [HGS warm-start] failed: {e}")
        return None

    def solve(self, time_limit=30.0, seed=42, verbose=False, print_every=500):
        """
        Main solver loop. Time-limited.

        Args:
            time_limit: wall-clock seconds for the search
            seed: random seed
            verbose: print progress every print_every iterations
        """
        rng = random.Random(seed)
        dist = self.dist
        demands = self.demands
        capacity = self.capacity
        n_cust = self.n_cust
        pen_cap = self.penalty.penalty
        pop = self.population
        start_time = time.perf_counter()

        # ===========================================================
        #  PHASE 1: Build initial population
        # ===========================================================
        init_routes_list = []

        # [HGS C++] Warm-start for large instances: run HGS for a portion
        # of the time budget to get a high-quality initial solution
        # For very large instances (n>200), HGS C++ dominates Python performance,
        # so allocate most of the time budget to HGS.
        hgs_time = 0.0
        if self.use_hgs_warmstart and n_cust >= 100 and self.vrp_filepath:
            if n_cust > 200:
                hgs_budget = time_limit - 30.0  # only 30s for Python refinement
            elif n_cust > 150:
                hgs_budget = min(time_limit * 0.5, time_limit - 60.0)
            else:
                hgs_budget = min(60.0, time_limit * 0.3)
            hgs_budget = max(30.0, hgs_budget)
            hgs_routes = self._hgs_warmstart(hgs_budget, seed, verbose)
            hgs_time = time.perf_counter() - start_time
            if hgs_routes:
                # Convert HGS routes (1-based customer indices) to our format
                # HGS already returns 1-based, which matches our convention
                all_hgs = [list(r) for r in hgs_routes if r]
                if all_hgs:
                    # Add HGS solution directly
                    init_routes_list.append(all_hgs)
                    # Apply LS to HGS solution for further refinement
                    hgs_ls = _fast_local_search(all_hgs, dist, demands, capacity,
                                                self.granular_nb, pen_cap,
                                                max_rounds=5)
                    init_routes_list.append(hgs_ls)
                    # Create perturbations of HGS solution for diversity
                    for _p in range(min(3, pop.mu)):
                        db = alns_double_bridge(all_hgs, dist, demands,
                                                capacity, rng)
                        db_ls = _fast_local_search(db, dist, demands, capacity,
                                                   self.granular_nb, pen_cap,
                                                   max_rounds=2)
                        init_routes_list.append(db_ls)

        # Multi-start nearest-neighbor to seed the population
        n_nn = max(3, min(8, pop.mu))
        for s in range(1, n_nn + 1):
            nn = nearest_neighbor_solution(dist, demands, capacity,
                                           self.num_vehicles, seed=seed + s * 17)
            ls = _fast_local_search(nn, dist, demands, capacity,
                                    self.granular_nb, pen_cap, max_rounds=3)
            init_routes_list.append(ls)

        # Add all to population
        for routes in init_routes_list:
            ind = Individual(routes, dist, demands, capacity,
                             self.num_vehicles, pen_cap)
            pop.add(ind)

        if verbose:
            best = pop.best_feasible
            bc = best.cost if best else _INF
            print(f"  [Init] Population size: {len(pop.feasible)}F + "
                  f"{len(pop.infeasible)}I | best={bc:.0f}")

        # Track best
        best_cost = pop.best_feasible.cost if pop.best_feasible else _INF
        best_routes = ([list(r) for r in pop.best_feasible.routes]
                       if pop.best_feasible else init_routes_list[0])
        self.traj_cost = []

        # [TS] Tabu structures
        tabu_list = {}     # customer -> forbidden until iteration
        movement_list = {} # (customer, route_idx) -> forbidden until iter

        # ALNS weight decay
        decay = 0.99
        score_best, score_improved, score_accepted = 10.0, 4.0, 2.0

        # ===========================================================
        #  PHASE 2: Main iterative loop (time-controlled)
        # ===========================================================
        it = 0
        pen_adapt_interval = 50
        no_improve = 0
        restart_threshold = max(500, n_cust * 10)
        self._restart_threshold = restart_threshold

        while True:
            it += 1
            elapsed = time.perf_counter() - start_time
            if elapsed >= time_limit:
                break

            # [HGS] Adaptive penalty
            if self.adaptive_penalty and it % pen_adapt_interval == 0:
                pen_cap = self.penalty.adapt()
                pop.re_eval_infeasible(dist, demands, capacity, pen_cap)

            # [TS] Restart from best when stuck — inject multiple perturbations
            if no_improve >= restart_threshold:
                no_improve = 0
                tabu_list.clear()
                movement_list.clear()
                # Inject multiple double-bridge perturbations into population
                if best_routes and self.search_mode != "recombination_only":
                    n_inject = 3 if n_cust >= 80 else 1
                    for _inj in range(n_inject):
                        db = alns_double_bridge(best_routes, dist, demands,
                                                capacity, rng)
                        db_ls = _fast_local_search(db, dist, demands, capacity,
                                                   self.granular_nb, pen_cap,
                                                   max_rounds=3)
                        db_ind = Individual(
                            db_ls, dist, demands, capacity,
                            self.num_vehicles, pen_cap)
                        pop.add(db_ind)
                        if db_ind.is_feasible and db_ind.cost < best_cost - _EPS:
                            best_cost = db_ind.cost
                            best_routes = [list(r) for r in db_ind.routes]

            # ----------------------------------------------------------
            # Generate offspring
            # ----------------------------------------------------------
            self._stagnation = no_improve
            pop_size = len(pop.feasible) + len(pop.infeasible)

            # -1 = crossover path used, >= 0 = ALNS operator index
            d_idx = -1

            use_crossover = (
                pop_size >= 2
                and (
                    self.search_mode == "recombination_only"
                    or (self.search_mode == "full" and rng.random() < 0.5)
                )
            )
            if use_crossover:
                # [HGS] Crossover path
                p1, p2 = pop.select_parents(rng)
                offspring_routes = crossover_ox(
                    p1.routes, p2.routes, dist, demands, capacity,
                    pen_cap, rng)
                # Optionally apply light ALNS perturbation to crossover offspring
                # (15% chance) — helps diversify on large instances
                if (self.search_mode == "full" and n_cust >= 80
                        and rng.random() < 0.15):
                    d_idx2 = self._roulette(self._d_weights, rng)
                    self._d_usage[d_idx2] += 1
                    perturbed = self._d_ops[d_idx2][1](offspring_routes, rng)
                    if perturbed is not None:
                        offspring_routes = perturbed
            elif self.search_mode != "recombination_only":
                # [ALNS] Perturbation path
                if pop.best_feasible and rng.random() < 0.7:
                    base = pop.best_feasible.routes
                else:
                    combined = pop.feasible + pop.infeasible
                    base = rng.choice(combined).routes if combined else best_routes

                d_idx = self._roulette(self._d_weights, rng)
                self._d_usage[d_idx] += 1
                offspring_routes = self._d_ops[d_idx][1](base, rng)
            else:
                # A population of size one is only possible during unusual
                # initialization failures. Keep the sole route set and let
                # local search restore progress without invoking ALNS.
                combined = pop.feasible + pop.infeasible
                offspring_routes = ([list(r) for r in combined[0].routes]
                                    if combined else [list(r) for r in best_routes])

            # ----------------------------------------------------------
            # [HGS/TS] Local search on offspring
            # ----------------------------------------------------------
            ls_rounds = 5 if n_cust <= 80 else (2 if n_cust > 200 else 3)
            ls_routes = _fast_local_search(
                offspring_routes, dist, demands, capacity,
                self.granular_nb, pen_cap, max_rounds=ls_rounds)

            # Create individual
            ind = Individual(ls_routes, dist, demands, capacity,
                             self.num_vehicles, pen_cap)
            self.penalty.record(ind.is_feasible)

            # ----------------------------------------------------------
            # [TS] Tabu acceptance
            # ----------------------------------------------------------
            moved = self._moved_customers(best_routes, ind.routes)
            any_tabu = any(tabu_list.get(c, 0) > it for c in moved)
            # Build route map for new solution for O(1) lookups
            new_route_map = {}
            for _ri, _r in enumerate(ind.routes):
                for _c in _r:
                    new_route_map[_c] = _ri
            any_ml = any(movement_list.get((c, new_route_map.get(c, -1)), 0) > it
                         for c in moved)
            aspiration = ind.is_feasible and ind.cost < best_cost - _EPS

            accept = aspiration or (not any_tabu and not any_ml)

            if accept:
                # Update tabu — build route map once for O(1) lookups
                old_map = {}
                for _ri, _r in enumerate(best_routes):
                    for _c in _r:
                        old_map[_c] = _ri
                for c in moved:
                    tabu_list[c] = it + self.tabu_tenure
                    old_r = old_map.get(c, -1)
                    if old_r >= 0:
                        movement_list[(c, old_r)] = it + self.ml_tenure

                # [HGS] Add to population
                new_best = pop.add(ind)

                # Update ALNS weights
                if new_best:
                    score = score_best
                    no_improve = 0
                elif ind.pen_cost < (pop.best_feasible.pen_cost
                                     if pop.best_feasible else _INF):
                    score = score_improved
                else:
                    score = score_accepted
                    no_improve += 1

                # [ALNS] Update operator weights (only when ALNS path used)
                if d_idx >= 0 and self.adaptive_operator_weights:
                    w = self._d_weights
                    w[d_idx] = w[d_idx] * decay + score * (1 - decay)
                    self._d_success[d_idx] += 1

                # Track best feasible
                if pop.best_feasible and pop.best_feasible.cost < best_cost - _EPS:
                    best_cost = pop.best_feasible.cost
                    best_routes = [list(r) for r in pop.best_feasible.routes]
                    no_improve = 0
            else:
                no_improve += 1

            # [HGS] Repair infeasible offspring (50% chance)
            if not ind.is_feasible and rng.random() < 0.5:
                repair_routes = _fast_local_search(
                    ind.routes, dist, demands, capacity,
                    self.granular_nb, pen_cap * 10, max_rounds=2)
                repair_ind = Individual(
                    repair_routes, dist, demands, capacity,
                    self.num_vehicles, pen_cap)
                if repair_ind.is_feasible:
                    pop.add(repair_ind)
                    if repair_ind.cost < best_cost - _EPS:
                        best_cost = repair_ind.cost
                        best_routes = [list(r) for r in repair_ind.routes]
                        no_improve = 0

            self.traj_cost.append(best_cost)

            # Clean tabu periodically
            if it % 200 == 0:
                tabu_list = {k: v for k, v in tabu_list.items() if v > it}
                movement_list = {k: v for k, v in movement_list.items() if v > it}

            # Verbose
            if verbose and (it % print_every == 0 or it == 1):
                feas = "OK" if (pop.best_feasible and
                                pop.best_feasible.is_feasible) else "SEARCH"
                print(f"  Iter {it:>6d} | best={best_cost:.0f} | "
                      f"pop={len(pop.feasible)}F+{len(pop.infeasible)}I | "
                      f"pen={pen_cap:.1f} [{feas}] | {elapsed:.2f}s")

        # ===========================================================
        #  PHASE 3: Final intensification
        #  - Deep LS on best solution
        #  - Multiple double-bridge perturbations + LS
        # ===========================================================
        if best_routes:
            # Deep LS on best
            final = _fast_local_search(
                best_routes, dist, demands, capacity,
                self.granular_nb, pen_cap, max_rounds=10)
            fc = total_cost(final, dist)
            feas = (all(route_demand(r, demands) <= capacity for r in final)
                    and len([r for r in final if r]) <= self.num_vehicles)
            if feas and fc < best_cost - _EPS:
                best_cost = fc
                best_routes = final

            # Perturbation + LS intensification (use remaining time).
            # Disabled in recombination-only ablation to avoid ALNS leakage.
            if self.search_mode != "recombination_only":
                time_left = time_limit - (time.perf_counter() - start_time)
                avg_iter_time = (time.perf_counter() - start_time) / max(it, 1)
                n_perturb = max(5, int(time_left / max(0.5, avg_iter_time)))
                n_perturb = min(n_perturb, 50)
                for _p in range(n_perturb):
                    if time.perf_counter() - start_time >= time_limit + 5:
                        break
                    db = alns_double_bridge(best_routes, dist, demands,
                                            capacity, rng)
                    db_ls = _fast_local_search(db, dist, demands, capacity,
                                               self.granular_nb, pen_cap,
                                               max_rounds=5)
                    fc2 = total_cost(db_ls, dist)
                    feas2 = (all(route_demand(r, demands) <= capacity
                                 for r in db_ls)
                             and len([r for r in db_ls if r]) <= self.num_vehicles)
                    if feas2 and fc2 < best_cost - _EPS:
                        best_cost = fc2
                        best_routes = db_ls

            # Deep LS once more on the very best
            final2 = _fast_local_search(
                best_routes, dist, demands, capacity,
                self.granular_nb, pen_cap, max_rounds=10)
            fc2 = total_cost(final2, dist)
            feas2 = (all(route_demand(r, demands) <= capacity for r in final2)
                     and len([r for r in final2 if r]) <= self.num_vehicles)
            if feas2 and fc2 < best_cost - _EPS:
                best_cost = fc2
                best_routes = final2

        # Statistics
        self.convergence_iter = next(
            (i + 1 for i, c in enumerate(self.traj_cost)
             if c <= best_cost + 1e-6), it)
        self.d_weights_final = list(self._d_weights)
        self.total_iter = it
        self.elapsed = time.perf_counter() - start_time

        if verbose:
            print(f"  [Done] {it} iterations in {self.elapsed:.2f}s | "
                  f"best={best_cost:.0f}")

        clean_routes = [r for r in best_routes if r]
        validation = validate_solution(
            clean_routes, demands, capacity, self.num_vehicles)
        if not validation["feasible"]:
            raise RuntimeError(
                "Solver finished without a valid CVRP solution: "
                f"{validation}")
        return best_cost, clean_routes


# ================================================================
#  CLI RUNNER
# ================================================================

def run_from_json(json_path: str, verbose: bool = False):
    if json_path.lower().endswith(".vrp"):
        datasets = parse_vrp_file(json_path)
    else:
        with open(json_path, encoding="utf-8") as f:
            datasets = json.load(f)

    results = []
    hdr = (f"{'Instance':<35} {'NN init':>8} "
           f"{'Best':>9} {'Improv%':>9} {'Iter':>7} {'Time':>7}")
    print(hdr)
    print("-" * len(hdr))

    for ds in datasets:
        coords   = [ds["depot"]] + [c["coord"] for c in ds["customers"]]
        demands  = [0] + [c["demand"] for c in ds["customers"]]
        names    = [c["name"] for c in ds["customers"]]
        capacity = ds["vehicle_capacity"]
        num_veh  = ds["num_vehicles"]
        n_cust   = len(ds["customers"])
        seed     = ds.get("seed", 1)

        dist = build_dist(coords)

        # Auto-scale parameters
        # nb_granular: HGS default ~20; larger => better LS but slower per iteration
        if n_cust <= 50:
            nb_granular = max(15, n_cust // 4)
        elif n_cust <= 100:
            nb_granular = max(20, min(30, n_cust // 3))
        else:
            nb_granular = min(50, max(35, n_cust // 4))
        # k_destroy: larger for large instances to improve diversification
        k_destroy = max(4, min(n_cust // 5, 30))
        tabu_tenure = max(5, n_cust // 5)
        ml_tenure = max(3, n_cust // 10)
        pop_mu = max(5, min(25, n_cust // 4))
        init_penalty = max(1.0, max(dist[0]) / max(max(demands), 1))

        # Time limit: scale with problem size; much more time for large instances
        if n_cust <= 50:
            time_limit = max(20.0, n_cust * 0.8)
        elif n_cust <= 100:
            time_limit = max(40.0, n_cust * 1.0)
        elif n_cust <= 200:
            time_limit = max(120.0, min(360.0, n_cust * 2.0))
        else:
            time_limit = max(360.0, min(600.0, n_cust * 2.5))

        # NN baseline (also serves as init display)
        nn_routes = nearest_neighbor_solution(dist, demands, capacity,
                                              num_veh, seed)
        nn_cost = total_cost(nn_routes, dist)

        # Run solver
        t0 = time.perf_counter()
        solver = HybridMemeticCVRP(
            dist, demands, capacity, num_veh,
            pop_mu=pop_mu, nb_elite=2, nb_close=3,
            init_penalty=init_penalty, target_feas=0.20,
            tabu_tenure=tabu_tenure, ml_tenure=ml_tenure,
            k_destroy=k_destroy, nb_granular=nb_granular,
            vrp_filepath=json_path if json_path.lower().endswith(".vrp") else "",
            use_hgs_warmstart=False,
        )
        best_cost, best_routes = solver.solve(
            time_limit=time_limit, seed=seed, verbose=verbose)
        elapsed = time.perf_counter() - t0

        improvement = ((nn_cost - best_cost) / nn_cost * 100
                        if nn_cost > 0 else 0.0)
        conv = solver.convergence_iter
        label = ds.get("label", "CVRP")[:35]

        print(f"{label:<35} {nn_cost:>8.0f} "
              f"{best_cost:>9.0f} {improvement:>8.2f}% "
              f"{conv:>7d} {elapsed:>6.2f}s")

        results.append(dict(
            label=ds.get("label", "CVRP"),
            coords=coords, names=names,
            capacity=capacity, num_veh=num_veh,
            nn_cost=nn_cost, nn_routes=nn_routes,
            init_cost=nn_cost,
            best_cost=best_cost, best_routes=best_routes,
            route_count=len([r for r in best_routes if r]),
            feasible=validate_solution(
                best_routes, demands, capacity, num_veh)["feasible"],
            traj=solver.traj_cost,
            elapsed=elapsed,
            d_weights=solver.d_weights_final,
            d_usage=solver._d_usage,
            d_success=solver._d_success,
        ))

    print("-" * len(hdr))

    for r in results:
        print(f"\n=== {r['label']} ===")
        print(f"  Init cost:     {r['init_cost']:.2f}")
        print(f"  Best cost:     {r['best_cost']:.2f}")
        imp = (r['init_cost'] - r['best_cost']) / r['init_cost'] * 100
        print(f"  Improvement:   {imp:.2f}%")
        print(f"  Best routes:")
        print(format_routes(r["best_routes"], r["names"]))
        d_names = ["Relocation", "RandRemove", "WorstRemove", "ShawRemove", "DoubleBridge", "SegExchange"]
        w_str = ", ".join(f"{n}={w:.3f}(u:{u}/s:{s})"
                          for n, w, u, s in zip(
                              d_names, r["d_weights"], r["d_usage"], r["d_success"]))
        print(f"  ALNS weights: {w_str}")

    return results


# ================================================================
#  PLOT
# ================================================================

def plot_results(results, save_path=None):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
    except ImportError:
        print("matplotlib not installed, skipping plot.")
        return

    COLORS = ["#E63946", "#457B9D", "#2D6A4F", "#F4A261",
              "#8338EC", "#06D6A0", "#FFBE0B", "#FB5607",
              "#3A86FF", "#FF006E"]

    n_ds = len(results)
    fig = plt.figure(figsize=(8 * n_ds, 10))
    gs = gridspec.GridSpec(2, n_ds, figure=fig, hspace=0.45, wspace=0.35)

    for col, r in enumerate(results):
        coords, depot = r["coords"], r["coords"][0]

        ax = fig.add_subplot(gs[0, col])
        ax.set_title(f"{r['label']}\nBest={r['best_cost']:.2f}",
                     fontsize=10, fontweight="bold")
        for ri, route in enumerate(r["best_routes"]):
            if not route: continue
            color = COLORS[ri % len(COLORS)]
            pts = [depot] + [coords[c] for c in route] + [depot]
            ax.plot([p[0] for p in pts], [p[1] for p in pts],
                    "-o", color=color, lw=1.4, ms=5, label=f"V{ri+1}")
            for c in route:
                ax.annotate(r["names"][c-1], coords[c], fontsize=6,
                            ha="center", va="bottom",
                            xytext=(0, 4), textcoords="offset points")
        ax.plot(depot[0], depot[1], "s", color="black", ms=10,
                zorder=5, label="Depot")
        ax.legend(fontsize=7, loc="upper right")
        ax.set_xlabel("x"); ax.set_ylabel("y")
        ax.grid(True, ls="--", alpha=0.4)

        ax2 = fig.add_subplot(gs[1, col])
        ax2.plot(r["traj"], color="#457B9D", lw=1.2)
        ax2.axhline(r["best_cost"], color="#E63946", ls="--", lw=1,
                     label=f"Best={r['best_cost']:.2f}")
        ax2.set_title("Convergence", fontsize=9)
        ax2.set_xlabel("Iteration"); ax2.set_ylabel("Best Cost")
        ax2.legend(fontsize=8)
        ax2.grid(True, ls="--", alpha=0.4)

    fig.suptitle("CVRP - Hybrid Memetic Solver (TS+ALNS+HGS)",
                 fontsize=13, fontweight="bold")
    try:
        plt.tight_layout()
    except Exception:
        pass
    out = save_path or "cvrp_ts_alns_result.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\nPlot saved: {out}")
    plt.close()


# ================================================================
#  ENTRY POINT
# ================================================================

if __name__ == "__main__":
    # Auto-relaunch with UTF-8 on Windows
    if sys.platform == "win32" and not sys.flags.utf8_mode:
        import subprocess as _sp
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        ret = _sp.run([sys.executable, "-X", "utf8"] + sys.argv, env=env).returncode
        sys.exit(ret)

    input_file = sys.argv[1] if len(sys.argv) > 1 else "A-n32-k5.vrp"
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print("+=========================================================+")
    print("|  CVRP - Hybrid Memetic Solver (TS + ALNS, HGS-inspired) |")
    print("+=========================================================+\n")
    print(f"Input: {input_file}\n")

    if not os.path.exists(input_file):
        print(f"[ERROR] File not found: {input_file}")
        sys.exit(1)

    results = run_from_json(input_file, verbose=verbose)
    plot_results(results, save_path="cvrp_ts_alns_result.png")
