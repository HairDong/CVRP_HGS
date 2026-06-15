#include <bits/stdc++.h>
using namespace std;

struct Customer {
    int id;
    double x, y;
    int demand;
};

struct Route {
    vector<int> customers; // lưu index khách hàng: 1..n, depot = 0
    int load = 0;
    double cost = 0;
};

struct Solution {
    vector<Route> routes;
    double totalCost = 0;
    int violation = 0;
    double fitness = 0;
};

int n, capacityVehicle;
vector<Customer> nodes;
vector<vector<double>> distMat;

mt19937 rng(3);

double penaltyCapacity = 1000.0;

double euclidDist(const Customer& a, const Customer& b) {
    double dx = a.x - b.x;
    double dy = a.y - b.y;
    double dist = sqrt(dx * dx + dy * dy);
    return floor(dist + 0.5); // TSPLIB EUC_2D rounding
}

void buildDistanceMatrix() {
    distMat.assign(n + 1, vector<double>(n + 1, 0));
    for (int i = 0; i <= n; i++) {
        for (int j = 0; j <= n; j++) {
            distMat[i][j] = euclidDist(nodes[i], nodes[j]);
        }
    }
}

double routeCost(const vector<int>& r) {
    if (r.empty()) return 0;
    double cost = distMat[0][r[0]];
    for (int i = 0; i + 1 < (int)r.size(); i++) {
        cost += distMat[r[i]][r[i + 1]];
    }
    cost += distMat[r.back()][0];
    return cost;
}

int routeLoad(const vector<int>& r) {
    int load = 0;
    for (int c : r) load += nodes[c].demand;
    return load;
}

void evaluate(Solution& sol) {
    sol.totalCost = 0;
    sol.violation = 0;

    for (auto& route : sol.routes) {
        route.load = routeLoad(route.customers);
        route.cost = routeCost(route.customers);

        sol.totalCost += route.cost;

        if (route.load > capacityVehicle) {
            sol.violation += route.load - capacityVehicle;
        }
    }

    sol.fitness = sol.totalCost + penaltyCapacity * sol.violation;
}

void removeEmptyRoutes(Solution& sol) {
    vector<Route> newRoutes;
    for (auto& r : sol.routes) {
        if (!r.customers.empty()) newRoutes.push_back(r);
    }
    sol.routes = newRoutes;
    evaluate(sol);
}

Solution greedyInitialSolution(bool randomized = false) {
    Solution sol;
    vector<int> customers;
    for (int i = 1; i <= n; i++) customers.push_back(i);

    vector<bool> used(n + 1, false);
    int remaining = n;

    while (remaining > 0) {
        Route route;
        int current = 0;
        int load = 0;

        while (true) {
            vector<pair<double, int>> candidates;

            for (int c = 1; c <= n; c++) {
                if (used[c]) continue;
                if (load + nodes[c].demand > capacityVehicle) continue;

                candidates.push_back(make_pair(distMat[current][c], c));
            }

            if (candidates.empty()) break;

            sort(candidates.begin(), candidates.end());

            int chooseIndex = 0;
            if (randomized) {
                int k = min(3, (int)candidates.size());
                uniform_int_distribution<int> pick(0, k - 1);
                chooseIndex = pick(rng);
            }

            int best = candidates[chooseIndex].second;

            route.customers.push_back(best);
            used[best] = true;
            load += nodes[best].demand;
            current = best;
            remaining--;
        }

        if (route.customers.empty()) {
            for (int c = 1; c <= n; c++) {
                if (!used[c]) {
                    route.customers.push_back(c);
                    used[c] = true;
                    remaining--;
                    break;
                }
            }
        }

        sol.routes.push_back(route);
    }

    evaluate(sol);
    return sol;
}

Solution savingsInitialSolution() {
    Solution sol;
    sol.routes.clear();
    sol.routes.reserve(n);

    vector<int> routeOf(n + 1, -1);

    for (int i = 1; i <= n; i++) {
        Route r;
        r.customers.push_back(i);
        r.load = nodes[i].demand;
        sol.routes.push_back(r);
        routeOf[i] = (int)sol.routes.size() - 1;
    }

    vector<tuple<double, int, int>> savings;
    savings.reserve(n * (n - 1) / 2);

    for (int i = 1; i <= n; i++) {
        for (int j = i + 1; j <= n; j++) {
            double s = distMat[0][i] + distMat[0][j] - distMat[i][j];
            savings.push_back(make_tuple(s, i, j));
        }
    }

    sort(savings.rbegin(), savings.rend());

    for (int idx = 0; idx < (int)savings.size(); idx++) {
        int i = get<1>(savings[idx]);
        int j = get<2>(savings[idx]);

        int ri = routeOf[i];
        int rj = routeOf[j];

        if (ri == rj || ri < 0 || rj < 0) continue;

        Route& routeI = sol.routes[ri];
        Route& routeJ = sol.routes[rj];

        if (routeI.customers.empty() || routeJ.customers.empty()) continue;

        bool iFront = routeI.customers.front() == i;
        bool iBack = routeI.customers.back() == i;
        bool jFront = routeJ.customers.front() == j;
        bool jBack = routeJ.customers.back() == j;

        if (!(iFront || iBack) || !(jFront || jBack)) continue;

        if (routeI.load + routeJ.load > capacityVehicle) continue;

        vector<int> merged;

        if (iBack && jFront) {
            merged.insert(merged.end(), routeI.customers.begin(), routeI.customers.end());
            merged.insert(merged.end(), routeJ.customers.begin(), routeJ.customers.end());
        } else if (iFront && jBack) {
            merged.insert(merged.end(), routeJ.customers.begin(), routeJ.customers.end());
            merged.insert(merged.end(), routeI.customers.begin(), routeI.customers.end());
        } else if (iFront && jFront) {
            vector<int> left = routeI.customers;
            reverse(left.begin(), left.end());
            merged.insert(merged.end(), left.begin(), left.end());
            merged.insert(merged.end(), routeJ.customers.begin(), routeJ.customers.end());
        } else if (iBack && jBack) {
            vector<int> right = routeJ.customers;
            reverse(right.begin(), right.end());
            merged.insert(merged.end(), routeI.customers.begin(), routeI.customers.end());
            merged.insert(merged.end(), right.begin(), right.end());
        }

        if (merged.empty()) continue;

        routeI.customers = merged;
        routeI.load += routeJ.load;

        routeJ.customers.clear();
        routeJ.load = 0;

        for (int k = 0; k < (int)routeI.customers.size(); k++) {
            routeOf[routeI.customers[k]] = ri;
        }
    }

    removeEmptyRoutes(sol);
    evaluate(sol);
    return sol;
}

Solution splitFromTour(const vector<int>& tour) {
    Solution sol;
    int m = (int)tour.size();
    if (m == 0) return sol;

    vector<double> prefixDist(m, 0.0);
    for (int i = 1; i < m; i++) {
        prefixDist[i] = prefixDist[i - 1] + distMat[tour[i - 1]][tour[i]];
    }

    vector<double> dp(m + 1, 1e18);
    vector<int> prev(m + 1, -1);
    dp[0] = 0.0;

    for (int i = 1; i <= m; i++) {
        int load = 0;

        for (int j = i; j >= 1; j--) {
            int c = tour[j - 1];
            load += nodes[c].demand;
            if (load > capacityVehicle) break;

            double segmentDist = 0.0;
            if (j - 1 < i - 1) {
                segmentDist = prefixDist[i - 1] - (j - 1 == 0 ? 0.0 : prefixDist[j - 1]);
            }

            double cost = distMat[0][tour[j - 1]] + segmentDist + distMat[tour[i - 1]][0];
            double cand = dp[j - 1] + cost;

            if (cand < dp[i]) {
                dp[i] = cand;
                prev[i] = j - 1;
            }
        }
    }

    if (prev[m] == -1) return sol;

    vector<vector<int>> routesRev;
    int idx = m;
    while (idx > 0 && prev[idx] != -1) {
        int start = prev[idx];
        vector<int> route;
        for (int k = start; k < idx; k++) route.push_back(tour[k]);
        routesRev.push_back(route);
        idx = start;
    }

    reverse(routesRev.begin(), routesRev.end());
    for (int i = 0; i < (int)routesRev.size(); i++) {
        Route r;
        r.customers = routesRev[i];
        sol.routes.push_back(r);
    }

    evaluate(sol);
    return sol;
}

double insertionCost(const Route& route, int customer, int pos) {
    int prev = pos == 0 ? 0 : route.customers[pos - 1];
    int next = pos == (int)route.customers.size() ? 0 : route.customers[pos];

    return distMat[prev][customer] + distMat[customer][next] - distMat[prev][next];
}

void greedyRepair(Solution& sol, vector<int>& removed);
void regretRepair(Solution& sol, vector<int>& removed);

vector<int> getAllCustomers(const Solution& sol) {
    vector<int> result;
    for (auto& r : sol.routes) {
        for (int c : r.customers) result.push_back(c);
    }
    return result;
}

int tournamentSelect(const vector<Solution>& pool, int k = 2) {
    if (pool.empty()) return -1;
    uniform_int_distribution<int> pick(0, (int)pool.size() - 1);
    int best = pick(rng);

    for (int i = 1; i < k; i++) {
        int idx = pick(rng);
        if (pool[idx].fitness < pool[best].fitness) {
            best = idx;
        }
    }

    return best;
}

Solution routeBasedCrossover(const Solution& p1, const Solution& p2) {
    vector<bool> used(n + 1, false);
    vector<int> tour;
    tour.reserve(n);

    if (p1.routes.empty()) {
        for (int ri = 0; ri < (int)p2.routes.size(); ri++) {
            for (int c : p2.routes[ri].customers) tour.push_back(c);
        }
        return splitFromTour(tour);
    }

    vector<int> routeIdx;
    for (int i = 0; i < (int)p1.routes.size(); i++) {
        routeIdx.push_back(i);
    }

    shuffle(routeIdx.begin(), routeIdx.end(), rng);

    int k = max(1, (int)(p1.routes.size() / 2));
    k = min(k, (int)p1.routes.size());

    for (int i = 0; i < k; i++) {
        const Route& r = p1.routes[routeIdx[i]];
        for (int c : r.customers) {
            if (!used[c]) {
                used[c] = true;
                tour.push_back(c);
            }
        }
    }

    for (int ri = 0; ri < (int)p2.routes.size(); ri++) {
        const Route& r = p2.routes[ri];
        for (int c : r.customers) {
            if (!used[c]) {
                used[c] = true;
                tour.push_back(c);
            }
        }
    }

    return splitFromTour(tour);
}

bool twoOptStarLocalSearch(Solution& sol, chrono::steady_clock::time_point deadline) {
    evaluate(sol);

    int iter = 0;

    while (chrono::steady_clock::now() < deadline) {
        iter++;
        double bestDelta = -1e-9;
        int bestR1 = -1, bestR2 = -1, bestI = -1, bestJ = -1;

        for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
            const Route& route1 = sol.routes[r1];
            int s1 = (int)route1.customers.size();
            if (s1 == 0) continue;

            vector<int> pref1(s1, 0);
            for (int i = 0; i < s1; i++) {
                pref1[i] = (i == 0 ? 0 : pref1[i - 1]) + nodes[route1.customers[i]].demand;
            }

            for (int r2 = r1 + 1; r2 < (int)sol.routes.size(); r2++) {
                if (chrono::steady_clock::now() >= deadline) break;

                const Route& route2 = sol.routes[r2];
                int s2 = (int)route2.customers.size();
                if (s2 == 0) continue;

                vector<int> pref2(s2, 0);
                for (int j = 0; j < s2; j++) {
                    pref2[j] = (j == 0 ? 0 : pref2[j - 1]) + nodes[route2.customers[j]].demand;
                }

                int load1 = route1.load;
                int load2 = route2.load;

                int oldViol = max(0, load1 - capacityVehicle) + max(0, load2 - capacityVehicle);

                for (int i = 0; i < s1; i++) {
                    int a = route1.customers[i];
                    int aNext = (i + 1 < s1) ? route1.customers[i + 1] : 0;
                    int load1Prefix = pref1[i];
                    int load1Tail = load1 - load1Prefix;

                    for (int j = 0; j < s2; j++) {
                        int b = route2.customers[j];
                        int bNext = (j + 1 < s2) ? route2.customers[j + 1] : 0;

                        int load2Prefix = pref2[j];
                        int load2Tail = load2 - load2Prefix;

                        int newLoad1 = load1Prefix + load2Tail;
                        int newLoad2 = load2Prefix + load1Tail;

                        int newViol = max(0, newLoad1 - capacityVehicle) + max(0, newLoad2 - capacityVehicle);

                        double deltaCost = distMat[a][bNext] + distMat[b][aNext]
                                           - distMat[a][aNext] - distMat[b][bNext];
                        double delta = deltaCost + penaltyCapacity * (newViol - oldViol);

                        if (delta < bestDelta) {
                            bestDelta = delta;
                            bestR1 = r1;
                            bestR2 = r2;
                            bestI = i;
                            bestJ = j;
                        }
                    }
                }
            }
        }

        if (bestR1 < 0 || bestR2 < 0) break;

        Route& r1 = sol.routes[bestR1];
        Route& r2 = sol.routes[bestR2];

        vector<int> newR1;
        vector<int> newR2;

        newR1.insert(newR1.end(), r1.customers.begin(), r1.customers.begin() + bestI + 1);
        newR1.insert(newR1.end(), r2.customers.begin() + bestJ + 1, r2.customers.end());

        newR2.insert(newR2.end(), r2.customers.begin(), r2.customers.begin() + bestJ + 1);
        newR2.insert(newR2.end(), r1.customers.begin() + bestI + 1, r1.customers.end());

        r1.customers = newR1;
        r2.customers = newR2;

        removeEmptyRoutes(sol);
        evaluate(sol);
    }

    return true;
}

bool orOptLocalSearch(Solution& sol, int len, chrono::steady_clock::time_point deadline) {
    if (len <= 0) return false;

    evaluate(sol);
    bool improved = false;

    while (chrono::steady_clock::now() < deadline) {
        double bestFitness = sol.fitness;
        Solution bestSol = sol;

        for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
            if (chrono::steady_clock::now() >= deadline) break;

            int s1 = (int)sol.routes[r1].customers.size();
            if (s1 < len) continue;

            for (int p1 = 0; p1 + len <= s1; p1++) {
                if (chrono::steady_clock::now() >= deadline) break;

                for (int r2 = 0; r2 < (int)sol.routes.size(); r2++) {
                    if (chrono::steady_clock::now() >= deadline) break;

                    int s2 = (int)sol.routes[r2].customers.size();

                    for (int p2 = 0; p2 <= s2; p2++) {
                        if (chrono::steady_clock::now() >= deadline) break;

                        if (r1 == r2 && p2 >= p1 && p2 <= p1 + len) continue;

                        Solution cand = sol;

                        vector<int> segment(
                            cand.routes[r1].customers.begin() + p1,
                            cand.routes[r1].customers.begin() + p1 + len
                        );

                        cand.routes[r1].customers.erase(
                            cand.routes[r1].customers.begin() + p1,
                            cand.routes[r1].customers.begin() + p1 + len
                        );

                        int insertPos = p2;
                        if (r1 == r2 && p2 > p1) {
                            insertPos = p2 - len;
                        }

                        cand.routes[r2].customers.insert(
                            cand.routes[r2].customers.begin() + insertPos,
                            segment.begin(), segment.end()
                        );

                        removeEmptyRoutes(cand);

                        if (cand.fitness < bestFitness - 1e-6) {
                            bestFitness = cand.fitness;
                            bestSol = cand;
                        }
                    }
                }
            }
        }

        if (bestFitness < sol.fitness - 1e-6) {
            sol = bestSol;
            improved = true;
        } else {
            break;
        }
    }

    return improved;
}

Solution setPartitionGreedy(const vector<Solution>& pool) {
    Solution sol;

    vector<Route> candidates;
    for (int i = 0; i < (int)pool.size(); i++) {
        for (int r = 0; r < (int)pool[i].routes.size(); r++) {
            Route cand = pool[i].routes[r];
            if (cand.customers.empty()) continue;
            cand.load = routeLoad(cand.customers);
            if (cand.load > capacityVehicle) continue;
            cand.cost = routeCost(cand.customers);
            candidates.push_back(cand);
        }
    }

    vector<bool> covered(n + 1, false);
    int coveredCount = 0;

    while (coveredCount < n) {
        int bestIdx = -1;
        double bestScore = 1e18;

        for (int i = 0; i < (int)candidates.size(); i++) {
            const Route& r = candidates[i];

            bool conflict = false;
            for (int c : r.customers) {
                if (covered[c]) {
                    conflict = true;
                    break;
                }
            }
            if (conflict) continue;

            int newCount = (int)r.customers.size();
            if (newCount == 0) continue;

            double score = r.cost / newCount;
            if (score < bestScore) {
                bestScore = score;
                bestIdx = i;
            }
        }

        if (bestIdx == -1) break;

        const Route& chosen = candidates[bestIdx];
        sol.routes.push_back(chosen);

        for (int c : chosen.customers) {
            if (!covered[c]) {
                covered[c] = true;
                coveredCount++;
            }
        }
    }

    for (int c = 1; c <= n; c++) {
        if (!covered[c]) {
            Route r;
            r.customers.push_back(c);
            sol.routes.push_back(r);
        }
    }

    evaluate(sol);
    return sol;
}

void randomDestroy(Solution& sol, vector<int>& removed, int removeCount) {
    vector<pair<int, int>> positions;

    for (int i = 0; i < (int)sol.routes.size(); i++) {
        for (int j = 0; j < (int)sol.routes[i].customers.size(); j++) {
            positions.push_back({i, j});
        }
    }

    shuffle(positions.begin(), positions.end(), rng);

    set<pair<int, int>, greater<pair<int, int>>> toRemove;
    for (int i = 0; i < min(removeCount, (int)positions.size()); i++) {
        toRemove.insert(positions[i]);
    }

    for (set<pair<int, int>, greater<pair<int, int>>>::const_iterator it = toRemove.begin(); it != toRemove.end(); ++it) {
        int ri = it->first;
        int pi = it->second;
        removed.push_back(sol.routes[ri].customers[pi]);
        sol.routes[ri].customers.erase(sol.routes[ri].customers.begin() + pi);
    }

    removeEmptyRoutes(sol);
}

void worstDestroy(Solution& sol, vector<int>& removed, int removeCount) {
    vector<tuple<double, int, int>> contribution;

    for (int ri = 0; ri < (int)sol.routes.size(); ri++) {
        auto& r = sol.routes[ri].customers;

        for (int pi = 0; pi < (int)r.size(); pi++) {
            int cur = r[pi];
            int prev = pi == 0 ? 0 : r[pi - 1];
            int next = pi == (int)r.size() - 1 ? 0 : r[pi + 1];

            double saving = distMat[prev][cur] + distMat[cur][next] - distMat[prev][next];
            contribution.push_back({saving, ri, pi});
        }
    }

    sort(contribution.rbegin(), contribution.rend());

    set<pair<int, int>, greater<pair<int, int>>> toRemove;
    for (int i = 0; i < min(removeCount, (int)contribution.size()); i++) {
        const auto& entry = contribution[i];
        int ri = get<1>(entry);
        int pi = get<2>(entry);
        toRemove.insert(make_pair(ri, pi));
    }

    for (set<pair<int, int>, greater<pair<int, int>>>::const_iterator it = toRemove.begin(); it != toRemove.end(); ++it) {
        int ri = it->first;
        int pi = it->second;
        removed.push_back(sol.routes[ri].customers[pi]);
        sol.routes[ri].customers.erase(sol.routes[ri].customers.begin() + pi);
    }

    removeEmptyRoutes(sol);
}

void relatedDestroy(Solution& sol, vector<int>& removed, int removeCount) {
    vector<int> all = getAllCustomers(sol);
    if (all.empty()) return;

    uniform_int_distribution<int> pick(0, (int)all.size() - 1);
    int seed = all[pick(rng)];

    vector<pair<double, pair<int, int>>> related;

    for (int ri = 0; ri < (int)sol.routes.size(); ri++) {
        for (int pi = 0; pi < (int)sol.routes[ri].customers.size(); pi++) {
            int c = sol.routes[ri].customers[pi];
            double score = distMat[seed][c] + abs(nodes[seed].demand - nodes[c].demand);
            related.push_back({score, {ri, pi}});
        }
    }

    sort(related.begin(), related.end());

    set<pair<int, int>, greater<pair<int, int>>> toRemove;
    for (int i = 0; i < min(removeCount, (int)related.size()); i++) {
        toRemove.insert(related[i].second);
    }

    for (set<pair<int, int>, greater<pair<int, int>>>::const_iterator it = toRemove.begin(); it != toRemove.end(); ++it) {
        int ri = it->first;
        int pi = it->second;
        removed.push_back(sol.routes[ri].customers[pi]);
        sol.routes[ri].customers.erase(sol.routes[ri].customers.begin() + pi);
    }

    removeEmptyRoutes(sol);
}

void routeDestroy(Solution& sol, vector<int>& removed, int routeCount) {
    if (sol.routes.empty()) return;

    vector<pair<double, int>> routeScore;
    for (int ri = 0; ri < (int)sol.routes.size(); ri++) {
        double score = sol.routes[ri].cost;
        score += 0.15 * (capacityVehicle - sol.routes[ri].load);
        routeScore.push_back({score, ri});
    }

    sort(routeScore.rbegin(), routeScore.rend());

    vector<int> selected;
    uniform_int_distribution<int> pickAny(0, (int)sol.routes.size() - 1);
    if (!routeScore.empty()) {
        uniform_int_distribution<int> pickTop(0, min((int)routeScore.size() - 1, 4));
        selected.push_back(routeScore[pickTop(rng)].second);
    } else {
        selected.push_back(pickAny(rng));
    }

    while ((int)selected.size() < routeCount && (int)selected.size() < (int)sol.routes.size()) {
        int base = selected[0];
        double bestScore = 1e18;
        int bestRoute = -1;

        for (int ri = 0; ri < (int)sol.routes.size(); ri++) {
            bool already = false;
            for (int s : selected) {
                if (s == ri) {
                    already = true;
                    break;
                }
            }
            if (already || sol.routes[ri].customers.empty()) continue;

            double minLink = 1e18;
            for (int a : sol.routes[base].customers) {
                for (int b : sol.routes[ri].customers) {
                    minLink = min(minLink, distMat[a][b]);
                }
            }

            if (minLink < bestScore) {
                bestScore = minLink;
                bestRoute = ri;
            }
        }

        if (bestRoute == -1) break;
        selected.push_back(bestRoute);
    }

    sort(selected.rbegin(), selected.rend());
    for (int ri : selected) {
        for (int c : sol.routes[ri].customers) {
            removed.push_back(c);
        }
        sol.routes.erase(sol.routes.begin() + ri);
    }

    evaluate(sol);
}

void greedyRepair(Solution& sol, vector<int>& removed) {
    shuffle(removed.begin(), removed.end(), rng);

    for (int customer : removed) {
        double bestDelta = 1e18;
        int bestRoute = -1;
        int bestPos = -1;

        for (int ri = 0; ri < (int)sol.routes.size(); ri++) {
            Route& r = sol.routes[ri];

            for (int pos = 0; pos <= (int)r.customers.size(); pos++) {
                int newLoad = r.load + nodes[customer].demand;
                int violation = max(0, newLoad - capacityVehicle);
                double delta = insertionCost(r, customer, pos) + penaltyCapacity * violation;

                if (delta < bestDelta) {
                    bestDelta = delta;
                    bestRoute = ri;
                    bestPos = pos;
                }
            }
        }

        Route newRoute;
        newRoute.customers.push_back(customer);
        double newRouteDelta = routeCost(newRoute.customers);

        if (newRouteDelta < bestDelta || bestRoute == -1) {
            sol.routes.push_back(newRoute);
        } else {
            sol.routes[bestRoute].customers.insert(
                sol.routes[bestRoute].customers.begin() + bestPos,
                customer
            );
        }

        evaluate(sol);
    }

    removed.clear();
    removeEmptyRoutes(sol);
}

void regretRepair(Solution& sol, vector<int>& removed) {
    while (!removed.empty()) {
        double bestRegret = -1e18;
        int chosenCustomerIndex = -1;
        int chosenRoute = -1;
        int chosenPos = -1;

        for (int idx = 0; idx < (int)removed.size(); idx++) {
            int customer = removed[idx];

            vector<tuple<double, int, int>> options;

            for (int ri = 0; ri < (int)sol.routes.size(); ri++) {
                Route& r = sol.routes[ri];

                for (int pos = 0; pos <= (int)r.customers.size(); pos++) {
                    int newLoad = r.load + nodes[customer].demand;
                    int violation = max(0, newLoad - capacityVehicle);
                    double delta = insertionCost(r, customer, pos) + penaltyCapacity * violation;
                    options.push_back({delta, ri, pos});
                }
            }

            Route newRoute;
            newRoute.customers.push_back(customer);
            options.push_back({routeCost(newRoute.customers), -1, 0});

            sort(options.begin(), options.end());

            double first = get<0>(options[0]);
            double second = options.size() > 1 ? get<0>(options[1]) : first;
            double regret = second - first;

            if (regret > bestRegret) {
                bestRegret = regret;
                chosenCustomerIndex = idx;
                chosenRoute = get<1>(options[0]);
                chosenPos = get<2>(options[0]);
            }
        }

        int customer = removed[chosenCustomerIndex];

        if (chosenRoute == -1) {
            Route nr;
            nr.customers.push_back(customer);
            sol.routes.push_back(nr);
        } else {
            sol.routes[chosenRoute].customers.insert(
                sol.routes[chosenRoute].customers.begin() + chosenPos,
                customer
            );
        }

        removed.erase(removed.begin() + chosenCustomerIndex);
        evaluate(sol);
    }

    removeEmptyRoutes(sol);
}

bool fastIntraTwoOpt(Solution& sol) {
    evaluate(sol);
    double bestDelta = -1e-9;
    int bestR = -1, bestI = -1, bestJ = -1;

    for (int r = 0; r < (int)sol.routes.size(); r++) {
        vector<int>& route = sol.routes[r].customers;
        int sz = (int)route.size();
        if (sz < 3) continue;

        for (int i = 0; i < sz - 1; i++) {
            int a = (i == 0) ? 0 : route[i - 1];
            int b = route[i];

            for (int j = i + 1; j < sz; j++) {
                int c = route[j];
                int d = (j + 1 == sz) ? 0 : route[j + 1];
                double delta = distMat[a][c] + distMat[b][d] - distMat[a][b] - distMat[c][d];

                if (delta < bestDelta) {
                    bestDelta = delta;
                    bestR = r;
                    bestI = i;
                    bestJ = j;
                }
            }
        }
    }

    if (bestR == -1) return false;

    reverse(sol.routes[bestR].customers.begin() + bestI,
            sol.routes[bestR].customers.begin() + bestJ + 1);
    evaluate(sol);
    return true;
}

bool fastIntraOrOpt(Solution& sol, int len) {
    evaluate(sol);
    if (len <= 1) return false;

    double bestDelta = -1e-9;
    int bestR = -1, bestFrom = -1, bestTo = -1;
    bool bestRev = false;

    for (int r = 0; r < (int)sol.routes.size(); r++) {
        vector<int>& route = sol.routes[r].customers;
        int sz = (int)route.size();
        if (sz <= len) continue;

        double oldCost = routeCost(route);
        for (int from = 0; from + len <= sz; from++) {
            vector<int> segment(route.begin() + from, route.begin() + from + len);
            vector<int> remaining = route;
            remaining.erase(remaining.begin() + from, remaining.begin() + from + len);

            for (int to = 0; to <= (int)remaining.size(); to++) {
                if (to == from) continue;

                for (int rev = 0; rev <= 1; rev++) {
                    vector<int> cand = remaining;
                    vector<int> seg = segment;
                    if (rev) reverse(seg.begin(), seg.end());
                    cand.insert(cand.begin() + to, seg.begin(), seg.end());

                    double delta = routeCost(cand) - oldCost;
                    if (delta < bestDelta) {
                        bestDelta = delta;
                        bestR = r;
                        bestFrom = from;
                        bestTo = to;
                        bestRev = rev != 0;
                    }
                }
            }
        }
    }

    if (bestR == -1) return false;

    vector<int>& route = sol.routes[bestR].customers;
    vector<int> segment(route.begin() + bestFrom, route.begin() + bestFrom + len);
    if (bestRev) reverse(segment.begin(), segment.end());
    route.erase(route.begin() + bestFrom, route.begin() + bestFrom + len);
    route.insert(route.begin() + bestTo, segment.begin(), segment.end());

    evaluate(sol);
    return true;
}

bool fastRelocate(Solution& sol) {
    evaluate(sol);
    double bestDelta = -1e-9;
    int bestR1 = -1, bestP1 = -1, bestR2 = -1, bestP2 = -1;

    for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
        Route& from = sol.routes[r1];
        int s1 = (int)from.customers.size();

        for (int p1 = 0; p1 < s1; p1++) {
            int c = from.customers[p1];
            int prev = (p1 == 0) ? 0 : from.customers[p1 - 1];
            int next = (p1 + 1 == s1) ? 0 : from.customers[p1 + 1];
            double removeDelta = distMat[prev][next] - distMat[prev][c] - distMat[c][next];

            for (int r2 = 0; r2 < (int)sol.routes.size(); r2++) {
                Route& to = sol.routes[r2];
                if (r1 != r2 && to.load + nodes[c].demand > capacityVehicle) continue;

                int s2 = (int)to.customers.size();
                for (int p2 = 0; p2 <= s2; p2++) {
                    if (r1 == r2 && (p2 == p1 || p2 == p1 + 1)) continue;

                    int before = (p2 == 0) ? 0 : to.customers[p2 - 1];
                    int after = (p2 == s2) ? 0 : to.customers[p2];
                    double addDelta = distMat[before][c] + distMat[c][after] - distMat[before][after];
                    double delta = removeDelta + addDelta;

                    if (delta < bestDelta) {
                        bestDelta = delta;
                        bestR1 = r1;
                        bestP1 = p1;
                        bestR2 = r2;
                        bestP2 = p2;
                    }
                }
            }
        }
    }

    if (bestR1 == -1) return false;

    int c = sol.routes[bestR1].customers[bestP1];
    sol.routes[bestR1].customers.erase(sol.routes[bestR1].customers.begin() + bestP1);
    if (bestR1 == bestR2 && bestP2 > bestP1) bestP2--;
    sol.routes[bestR2].customers.insert(sol.routes[bestR2].customers.begin() + bestP2, c);
    removeEmptyRoutes(sol);
    evaluate(sol);
    return true;
}

bool fastSwap(Solution& sol) {
    evaluate(sol);
    double bestDelta = -1e-9;
    int bestR1 = -1, bestP1 = -1, bestR2 = -1, bestP2 = -1;

    for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
        Route& route1 = sol.routes[r1];
        for (int p1 = 0; p1 < (int)route1.customers.size(); p1++) {
            int a = route1.customers[p1];

            for (int r2 = r1; r2 < (int)sol.routes.size(); r2++) {
                Route& route2 = sol.routes[r2];
                int start = (r1 == r2) ? p1 + 1 : 0;

                for (int p2 = start; p2 < (int)route2.customers.size(); p2++) {
                    int b = route2.customers[p2];
                    if (r1 != r2) {
                        int load1 = route1.load - nodes[a].demand + nodes[b].demand;
                        int load2 = route2.load - nodes[b].demand + nodes[a].demand;
                        if (load1 > capacityVehicle || load2 > capacityVehicle) continue;
                    }

                    int aPrev = (p1 == 0) ? 0 : route1.customers[p1 - 1];
                    int aNext = (p1 + 1 == (int)route1.customers.size()) ? 0 : route1.customers[p1 + 1];
                    int bPrev = (p2 == 0) ? 0 : route2.customers[p2 - 1];
                    int bNext = (p2 + 1 == (int)route2.customers.size()) ? 0 : route2.customers[p2 + 1];

                    double before;
                    double after;

                    if (r1 == r2 && p2 == p1 + 1) {
                        before = distMat[aPrev][a] + distMat[a][b] + distMat[b][bNext];
                        after = distMat[aPrev][b] + distMat[b][a] + distMat[a][bNext];
                    } else {
                        before = distMat[aPrev][a] + distMat[a][aNext] +
                                 distMat[bPrev][b] + distMat[b][bNext];
                        after = distMat[aPrev][b] + distMat[b][aNext] +
                                distMat[bPrev][a] + distMat[a][bNext];
                    }

                    double delta = after - before;
                    if (delta < bestDelta) {
                        bestDelta = delta;
                        bestR1 = r1;
                        bestP1 = p1;
                        bestR2 = r2;
                        bestP2 = p2;
                    }
                }
            }
        }
    }

    if (bestR1 == -1) return false;

    swap(sol.routes[bestR1].customers[bestP1], sol.routes[bestR2].customers[bestP2]);
    evaluate(sol);
    return true;
}

bool fastTwoOptStar(Solution& sol) {
    evaluate(sol);
    double bestDelta = -1e-9;
    int bestR1 = -1, bestR2 = -1, bestCut1 = -1, bestCut2 = -1;

    for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
        Route& route1 = sol.routes[r1];
        int s1 = (int)route1.customers.size();

        vector<int> pref1(s1 + 1, 0);
        for (int i = 0; i < s1; i++) {
            pref1[i + 1] = pref1[i] + nodes[route1.customers[i]].demand;
        }

        for (int r2 = r1 + 1; r2 < (int)sol.routes.size(); r2++) {
            Route& route2 = sol.routes[r2];
            int s2 = (int)route2.customers.size();

            vector<int> pref2(s2 + 1, 0);
            for (int j = 0; j < s2; j++) {
                pref2[j + 1] = pref2[j] + nodes[route2.customers[j]].demand;
            }

            for (int cut1 = 0; cut1 <= s1; cut1++) {
                int a = (cut1 == 0) ? 0 : route1.customers[cut1 - 1];
                int b = (cut1 == s1) ? 0 : route1.customers[cut1];

                for (int cut2 = 0; cut2 <= s2; cut2++) {
                    if (cut1 == s1 && cut2 == s2) continue;

                    int newLoad1 = pref1[cut1] + (pref2[s2] - pref2[cut2]);
                    int newLoad2 = pref2[cut2] + (pref1[s1] - pref1[cut1]);
                    if (newLoad1 > capacityVehicle || newLoad2 > capacityVehicle) continue;

                    int c = (cut2 == 0) ? 0 : route2.customers[cut2 - 1];
                    int d = (cut2 == s2) ? 0 : route2.customers[cut2];

                    double delta = distMat[a][d] + distMat[c][b] - distMat[a][b] - distMat[c][d];
                    if (delta < bestDelta) {
                        bestDelta = delta;
                        bestR1 = r1;
                        bestR2 = r2;
                        bestCut1 = cut1;
                        bestCut2 = cut2;
                    }
                }
            }
        }
    }

    if (bestR1 == -1) return false;

    vector<int>& r1 = sol.routes[bestR1].customers;
    vector<int>& r2 = sol.routes[bestR2].customers;

    vector<int> newR1;
    vector<int> newR2;

    newR1.insert(newR1.end(), r1.begin(), r1.begin() + bestCut1);
    newR1.insert(newR1.end(), r2.begin() + bestCut2, r2.end());

    newR2.insert(newR2.end(), r2.begin(), r2.begin() + bestCut2);
    newR2.insert(newR2.end(), r1.begin() + bestCut1, r1.end());

    r1 = newR1;
    r2 = newR2;

    removeEmptyRoutes(sol);
    evaluate(sol);
    return true;
}

bool fastSegmentRelocate(Solution& sol, int len) {
    evaluate(sol);
    if (len <= 1) return false;

    double bestDelta = -1e-9;
    int bestR1 = -1, bestP1 = -1, bestR2 = -1, bestP2 = -1;
    bool bestRev = false;

    for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
        Route& from = sol.routes[r1];
        int s1 = (int)from.customers.size();
        if (s1 < len) continue;

        for (int p1 = 0; p1 + len <= s1; p1++) {
            int first = from.customers[p1];
            int last = from.customers[p1 + len - 1];
            int prev = (p1 == 0) ? 0 : from.customers[p1 - 1];
            int next = (p1 + len == s1) ? 0 : from.customers[p1 + len];

            int segLoad = 0;
            for (int k = 0; k < len; k++) segLoad += nodes[from.customers[p1 + k]].demand;

            double removeDelta = distMat[prev][next] - distMat[prev][first] - distMat[last][next];

            for (int r2 = 0; r2 < (int)sol.routes.size(); r2++) {
                if (r1 == r2) continue;

                Route& to = sol.routes[r2];
                if (to.load + segLoad > capacityVehicle) continue;

                int s2 = (int)to.customers.size();
                for (int p2 = 0; p2 <= s2; p2++) {
                    int before = (p2 == 0) ? 0 : to.customers[p2 - 1];
                    int after = (p2 == s2) ? 0 : to.customers[p2];
                    for (int rev = 0; rev <= 1; rev++) {
                        int segFirst = rev ? last : first;
                        int segLast = rev ? first : last;
                        double addDelta = distMat[before][segFirst] + distMat[segLast][after] - distMat[before][after];
                        double delta = removeDelta + addDelta;

                        if (delta < bestDelta) {
                            bestDelta = delta;
                            bestR1 = r1;
                            bestP1 = p1;
                            bestR2 = r2;
                            bestP2 = p2;
                            bestRev = rev != 0;
                        }
                    }
                }
            }
        }
    }

    if (bestR1 == -1) return false;

    vector<int> segment(sol.routes[bestR1].customers.begin() + bestP1,
                        sol.routes[bestR1].customers.begin() + bestP1 + len);
    if (bestRev) reverse(segment.begin(), segment.end());
    sol.routes[bestR1].customers.erase(sol.routes[bestR1].customers.begin() + bestP1,
                                       sol.routes[bestR1].customers.begin() + bestP1 + len);
    sol.routes[bestR2].customers.insert(sol.routes[bestR2].customers.begin() + bestP2,
                                        segment.begin(), segment.end());

    removeEmptyRoutes(sol);
    evaluate(sol);
    return true;
}

double segmentInnerCost(const vector<int>& route, int pos, int len) {
    double cost = 0.0;
    for (int i = 0; i + 1 < len; i++) {
        cost += distMat[route[pos + i]][route[pos + i + 1]];
    }
    return cost;
}

int segmentLoad(const vector<int>& route, int pos, int len) {
    int load = 0;
    for (int i = 0; i < len; i++) {
        load += nodes[route[pos + i]].demand;
    }
    return load;
}

bool fastCrossExchange(Solution& sol, int maxLen = 3) {
    evaluate(sol);
    double bestDelta = -1e-9;
    int bestR1 = -1, bestP1 = -1, bestL1 = -1;
    int bestR2 = -1, bestP2 = -1, bestL2 = -1;
    bool bestRev1 = false, bestRev2 = false;

    for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
        Route& route1 = sol.routes[r1];
        int s1 = (int)route1.customers.size();

        for (int r2 = r1 + 1; r2 < (int)sol.routes.size(); r2++) {
            Route& route2 = sol.routes[r2];
            int s2 = (int)route2.customers.size();

            for (int p1 = 0; p1 < s1; p1++) {
                for (int l1 = 1; l1 <= maxLen && p1 + l1 <= s1; l1++) {
                    int load1Seg = segmentLoad(route1.customers, p1, l1);
                    int first1 = route1.customers[p1];
                    int last1 = route1.customers[p1 + l1 - 1];
                    int prev1 = (p1 == 0) ? 0 : route1.customers[p1 - 1];
                    int next1 = (p1 + l1 == s1) ? 0 : route1.customers[p1 + l1];
                    double inner1 = segmentInnerCost(route1.customers, p1, l1);

                    for (int p2 = 0; p2 < s2; p2++) {
                        for (int l2 = 1; l2 <= maxLen && p2 + l2 <= s2; l2++) {
                            int load2Seg = segmentLoad(route2.customers, p2, l2);
                            int newLoad1 = route1.load - load1Seg + load2Seg;
                            int newLoad2 = route2.load - load2Seg + load1Seg;
                            if (newLoad1 > capacityVehicle || newLoad2 > capacityVehicle) continue;

                            int first2 = route2.customers[p2];
                            int last2 = route2.customers[p2 + l2 - 1];
                            int prev2 = (p2 == 0) ? 0 : route2.customers[p2 - 1];
                            int next2 = (p2 + l2 == s2) ? 0 : route2.customers[p2 + l2];
                            double inner2 = segmentInnerCost(route2.customers, p2, l2);

                            double oldCost = distMat[prev1][first1] + inner1 + distMat[last1][next1] +
                                             distMat[prev2][first2] + inner2 + distMat[last2][next2];

                            for (int rev1 = 0; rev1 <= 1; rev1++) {
                                int put1First = rev1 ? last1 : first1;
                                int put1Last = rev1 ? first1 : last1;

                                for (int rev2 = 0; rev2 <= 1; rev2++) {
                                    int put2First = rev2 ? last2 : first2;
                                    int put2Last = rev2 ? first2 : last2;

                                    double newCost = distMat[prev1][put2First] + inner2 + distMat[put2Last][next1] +
                                                     distMat[prev2][put1First] + inner1 + distMat[put1Last][next2];
                                    double delta = newCost - oldCost;

                                    if (delta < bestDelta) {
                                        bestDelta = delta;
                                        bestR1 = r1;
                                        bestP1 = p1;
                                        bestL1 = l1;
                                        bestR2 = r2;
                                        bestP2 = p2;
                                        bestL2 = l2;
                                        bestRev1 = rev1 != 0;
                                        bestRev2 = rev2 != 0;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (bestR1 == -1) return false;

    vector<int> seg1(sol.routes[bestR1].customers.begin() + bestP1,
                     sol.routes[bestR1].customers.begin() + bestP1 + bestL1);
    vector<int> seg2(sol.routes[bestR2].customers.begin() + bestP2,
                     sol.routes[bestR2].customers.begin() + bestP2 + bestL2);
    if (bestRev1) reverse(seg1.begin(), seg1.end());
    if (bestRev2) reverse(seg2.begin(), seg2.end());

    sol.routes[bestR1].customers.erase(sol.routes[bestR1].customers.begin() + bestP1,
                                       sol.routes[bestR1].customers.begin() + bestP1 + bestL1);
    sol.routes[bestR1].customers.insert(sol.routes[bestR1].customers.begin() + bestP1,
                                        seg2.begin(), seg2.end());

    sol.routes[bestR2].customers.erase(sol.routes[bestR2].customers.begin() + bestP2,
                                       sol.routes[bestR2].customers.begin() + bestP2 + bestL2);
    sol.routes[bestR2].customers.insert(sol.routes[bestR2].customers.begin() + bestP2,
                                        seg1.begin(), seg1.end());

    evaluate(sol);
    return true;
}

void fastLocalSearch(Solution& sol, chrono::steady_clock::time_point deadline, int maxMoves = 200) {
    evaluate(sol);
    for (int iter = 0; iter < maxMoves && chrono::steady_clock::now() < deadline; iter++) {
        if (fastRelocate(sol)) continue;
        if (fastSegmentRelocate(sol, 2)) continue;
        if (fastSegmentRelocate(sol, 3)) continue;
        if (fastCrossExchange(sol, 3)) continue;
        if (fastSwap(sol)) continue;
        if (fastTwoOptStar(sol)) continue;
        if (fastIntraTwoOpt(sol)) continue;
        break;
    }
}

struct TabuMove {
    int a = -1;
    int b = -1;
    int expire = 0;
};

bool isTabu(const vector<TabuMove>& tabuList, int a, int b, int iter) {
    for (auto& t : tabuList) {
        if (((t.a == a && t.b == b) || (t.a == b && t.b == a)) && t.expire > iter) {
            return true;
        }
    }
    return false;
}

void tabuSearchEducation(Solution& sol, int maxIter = 80,
                         chrono::steady_clock::time_point deadline = chrono::steady_clock::time_point::max()) {
    auto timeUp = [&]() {
        return chrono::steady_clock::now() >= deadline;
    };

    evaluate(sol);

    Solution best = sol;
    vector<TabuMove> tabuList;

    int tabuTenure = max(8, n / 10);

    for (int iter = 1; iter <= maxIter; iter++) {
        if (timeUp()) {
            sol = best;
            evaluate(sol);
            return;
        }
        Solution bestNeighbor;
        double bestNeighborFitness = 1e18;

        int moveA = -1;
        int moveB = -1;

        // Relocate move
        for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
            if (timeUp()) {
                sol = best;
                evaluate(sol);
                return;
            }
            for (int p1 = 0; p1 < (int)sol.routes[r1].customers.size(); p1++) {
                if (timeUp()) {
                    sol = best;
                    evaluate(sol);
                    return;
                }
                int customer = sol.routes[r1].customers[p1];

                for (int r2 = 0; r2 < (int)sol.routes.size(); r2++) {
                    if (timeUp()) {
                        sol = best;
                        evaluate(sol);
                        return;
                    }
                    for (int p2 = 0; p2 <= (int)sol.routes[r2].customers.size(); p2++) {
                        if (timeUp()) {
                            sol = best;
                            evaluate(sol);
                            return;
                        }
                        if (r1 == r2 && (p2 == p1 || p2 == p1 + 1)) continue;
                        if (isTabu(tabuList, customer, -1, iter)) continue;

                        Solution cand = sol;

                        int c = cand.routes[r1].customers[p1];
                        cand.routes[r1].customers.erase(cand.routes[r1].customers.begin() + p1);

                        if (r1 == r2 && p2 > p1) p2--;

                        cand.routes[r2].customers.insert(cand.routes[r2].customers.begin() + p2, c);

                        removeEmptyRoutes(cand);

                        if (cand.fitness < bestNeighborFitness) {
                            bestNeighborFitness = cand.fitness;
                            bestNeighbor = cand;
                            moveA = customer;
                            moveB = -1;
                        }
                    }
                }
            }
        }

        // Swap move
        for (int r1 = 0; r1 < (int)sol.routes.size(); r1++) {
            if (timeUp()) {
                sol = best;
                evaluate(sol);
                return;
            }
            for (int p1 = 0; p1 < (int)sol.routes[r1].customers.size(); p1++) {
                if (timeUp()) {
                    sol = best;
                    evaluate(sol);
                    return;
                }
                for (int r2 = r1; r2 < (int)sol.routes.size(); r2++) {
                    if (timeUp()) {
                        sol = best;
                        evaluate(sol);
                        return;
                    }
                    int startP2 = r1 == r2 ? p1 + 1 : 0;

                    for (int p2 = startP2; p2 < (int)sol.routes[r2].customers.size(); p2++) {
                        if (timeUp()) {
                            sol = best;
                            evaluate(sol);
                            return;
                        }
                        int a = sol.routes[r1].customers[p1];
                        int b = sol.routes[r2].customers[p2];

                        if (isTabu(tabuList, a, b, iter)) continue;

                        Solution cand = sol;
                        swap(cand.routes[r1].customers[p1], cand.routes[r2].customers[p2]);

                        evaluate(cand);

                        if (cand.fitness < bestNeighborFitness) {
                            bestNeighborFitness = cand.fitness;
                            bestNeighbor = cand;
                            moveA = a;
                            moveB = b;
                        }
                    }
                }
            }
        }

        // 2-opt trong từng route
        for (int r = 0; r < (int)sol.routes.size(); r++) {
            if (timeUp()) {
                sol = best;
                evaluate(sol);
                return;
            }
            int sz = sol.routes[r].customers.size();
            if (sz < 4) continue;

            for (int i = 0; i < sz; i++) {
                if (timeUp()) {
                    sol = best;
                    evaluate(sol);
                    return;
                }
                for (int j = i + 2; j < sz; j++) {
                    if (timeUp()) {
                        sol = best;
                        evaluate(sol);
                        return;
                    }
                    Solution cand = sol;
                    reverse(cand.routes[r].customers.begin() + i, cand.routes[r].customers.begin() + j + 1);

                    evaluate(cand);

                    int a = sol.routes[r].customers[i];
                    int b = sol.routes[r].customers[j];

                    if (isTabu(tabuList, a, b, iter) && cand.fitness >= best.fitness) {
                        continue;
                    }

                    if (cand.fitness < bestNeighborFitness) {
                        bestNeighborFitness = cand.fitness;
                        bestNeighbor = cand;
                        moveA = a;
                        moveB = b;
                    }
                }
            }
        }

        if (bestNeighborFitness >= 1e18) break;

        sol = bestNeighbor;

        tabuList.push_back({moveA, moveB, iter + tabuTenure});

        if ((int)tabuList.size() > 200) {
            tabuList.erase(tabuList.begin());
        }

        if (sol.fitness < best.fitness) {
            best = sol;
        }
    }

    sol = best;
    evaluate(sol);
}

Solution ALNS_HGS_TS(int timeLimitSeconds) {
    auto start = chrono::steady_clock::now();
    auto deadline = start + chrono::seconds(timeLimitSeconds);

    Solution current = savingsInitialSolution();
    if (current.routes.empty()) {
        current = greedyInitialSolution(false);
    }
    int initIter = 200 + n * 20;
    int innerIter = 80 + n * 8;
    tabuSearchEducation(current, initIter, deadline);

    Solution best = current;
    int noImprove = 0;

    vector<Solution> elite;
    elite.push_back(best);
    int eliteMax = 6;

    double temperature = 1000.0;
    double cooling = 0.995;

    int iter = 0;

    vector<double> destroyScore = {1.0, 1.0, 1.0};
    vector<double> repairScore = {1.0, 1.0};

    while (true) {
        auto now = chrono::steady_clock::now();
        if (now >= deadline) break;

        iter++;

        Solution candidate;
        bool usedCrossover = false;
        int dOp = -1;
        int rOp = -1;

        if ((int)elite.size() >= 2) {
            uniform_real_distribution<double> crossProb(0.0, 1.0);
            if (crossProb(rng) < 0.25) {
                int p1 = tournamentSelect(elite, 2);
                int p2 = tournamentSelect(elite, 2);

                if (p1 == p2) {
                    p2 = (p2 + 1) % elite.size();
                }

                candidate = routeBasedCrossover(elite[p1], elite[p2]);
                usedCrossover = true;
            }
        }

        if (!usedCrossover) {
            candidate = current;

            int removeCount = max(1, (int)(0.18 * n));
            if (noImprove > 80) {
                removeCount = max(removeCount, (int)(0.28 * n));
            }
            uniform_int_distribution<int> extraRemove(0, max(1, (int)(0.22 * n)));
            removeCount += extraRemove(rng);
            removeCount = min(removeCount, max(1, n - 1));

            vector<int> removed;

            discrete_distribution<int> destroyPick(destroyScore.begin(), destroyScore.end());
            discrete_distribution<int> repairPick(repairScore.begin(), repairScore.end());

            dOp = destroyPick(rng);
            rOp = repairPick(rng);

            if (dOp == 0) randomDestroy(candidate, removed, removeCount);
            else if (dOp == 1) worstDestroy(candidate, removed, removeCount);
            else relatedDestroy(candidate, removed, removeCount);

            if (rOp == 0) greedyRepair(candidate, removed);
            else regretRepair(candidate, removed);
        }

        if (chrono::steady_clock::now() >= deadline) break;
        tabuSearchEducation(candidate, innerIter, deadline);

        if (iter % 5 == 0 && chrono::steady_clock::now() < deadline) {
            twoOptStarLocalSearch(candidate, deadline);
        }

        if (iter % 10 == 0 && chrono::steady_clock::now() < deadline) {
            orOptLocalSearch(candidate, 2, deadline);
            orOptLocalSearch(candidate, 3, deadline);
        }

        evaluate(candidate);

        bool accept = false;

        if (candidate.fitness < current.fitness) {
            accept = true;
        } else {
            double diff = candidate.fitness - current.fitness;
            double prob = exp(-diff / temperature);
            uniform_real_distribution<double> realDist(0.0, 1.0);

            if (realDist(rng) < prob) {
                accept = true;
            }
        }

        if (accept) {
            current = candidate;
        }

        if (candidate.fitness < best.fitness) {
            best = candidate;
            if (!usedCrossover && dOp >= 0 && rOp >= 0) {
                destroyScore[dOp] += 5.0;
                repairScore[rOp] += 5.0;
            }
            noImprove = 0;
        } else if (accept) {
            if (!usedCrossover && dOp >= 0 && rOp >= 0) {
                destroyScore[dOp] += 1.0;
                repairScore[rOp] += 1.0;
            }
            noImprove++;
        } else {
            noImprove++;
        }

        if ((int)elite.size() < eliteMax || candidate.fitness < elite.back().fitness) {
            elite.push_back(candidate);
            sort(elite.begin(), elite.end(), [](const Solution& a, const Solution& b) {
                return a.fitness < b.fitness;
            });
            if ((int)elite.size() > eliteMax) {
                elite.resize(eliteMax);
            }
        }

        temperature *= cooling;

        // HGS-like adaptive penalty
        if (iter % 100 == 0) {
            if (current.violation > 0) {
                penaltyCapacity *= 1.2;
            } else {
                penaltyCapacity *= 0.95;
            }

            penaltyCapacity = max(10.0, min(penaltyCapacity, 1000000.0));
            evaluate(current);
            evaluate(best);
        }

        if (noImprove >= 150 && chrono::steady_clock::now() < deadline) {
            current = greedyInitialSolution(true);
            tabuSearchEducation(current, innerIter, deadline);
            evaluate(current);

            if (current.fitness < best.fitness) {
                best = current;
            }

            noImprove = 0;
        }
    }

    return best;
}

Solution Fast_ALNS(int timeLimitSeconds) {
    auto start = chrono::steady_clock::now();
    auto deadline = start + chrono::seconds(timeLimitSeconds);

    vector<Solution> starts;
    starts.push_back(savingsInitialSolution());
    for (int i = 0; i < 12; i++) {
        starts.push_back(greedyInitialSolution(true));
    }

    Solution current = starts[0];
    evaluate(current);

    for (int i = 0; i < (int)starts.size() && chrono::steady_clock::now() < deadline; i++) {
        fastLocalSearch(starts[i], deadline, 120);
        if (starts[i].fitness < current.fitness) current = starts[i];
    }

    Solution best = current;
    double temperature = max(20.0, best.totalCost * 0.03);
    int noImprove = 0;
    int iter = 0;

    vector<Solution> elite;
    int eliteMax = 24;
    auto addElite = [&](const Solution& s) {
        if (s.violation > 0) return;
        elite.push_back(s);
        sort(elite.begin(), elite.end(), [](const Solution& a, const Solution& b) {
            return a.totalCost < b.totalCost;
        });

        vector<Solution> uniqueElite;
        for (int i = 0; i < (int)elite.size(); i++) {
            bool duplicate = false;
            for (int j = 0; j < (int)uniqueElite.size(); j++) {
                if (fabs(elite[i].totalCost - uniqueElite[j].totalCost) < 1e-6) {
                    duplicate = true;
                    break;
                }
            }
            if (!duplicate) uniqueElite.push_back(elite[i]);
        }

        elite = uniqueElite;
        if ((int)elite.size() > eliteMax) elite.resize(eliteMax);
    };

    for (int i = 0; i < (int)starts.size(); i++) addElite(starts[i]);

    while (chrono::steady_clock::now() < deadline) {
        iter++;
        Solution candidate;
        vector<int> removed;
        bool builtByRecombination = false;

        if ((int)elite.size() >= 2) {
            uniform_int_distribution<int> pickMode(0, 99);
            int mode = pickMode(rng);
            if (mode < 18) {
                int p1 = tournamentSelect(elite, 3);
                int p2 = tournamentSelect(elite, 3);
                if (p1 == p2) p2 = (p2 + 1) % elite.size();
                candidate = routeBasedCrossover(elite[p1], elite[p2]);
                builtByRecombination = true;
            } else if (mode < 23 && (int)elite.size() >= 4) {
                candidate = setPartitionGreedy(elite);
                builtByRecombination = true;
            }
        }

        if (!builtByRecombination) {
            candidate = current;

            int baseRemove = max(6, n / 6);
            if (noImprove > 80) baseRemove = max(baseRemove, n / 4);
            if (noImprove > 180) baseRemove = max(baseRemove, n / 3);
            uniform_int_distribution<int> extra(0, max(2, n / 7));
            int removeCount = min(n - 1, baseRemove + extra(rng));

            uniform_int_distribution<int> destroyPick(0, 99);
            int destroy = destroyPick(rng);
            if (destroy < 25) randomDestroy(candidate, removed, removeCount);
            else if (destroy < 55) worstDestroy(candidate, removed, removeCount);
            else if (destroy < 90 || noImprove < 80) relatedDestroy(candidate, removed, removeCount);
            else {
                uniform_int_distribution<int> routePick(1, max(1, min(3, (int)candidate.routes.size() / 6)));
                routeDestroy(candidate, removed, routePick(rng));
            }

            uniform_int_distribution<int> repairPick(0, 1);
            if (repairPick(rng) == 0) regretRepair(candidate, removed);
            else greedyRepair(candidate, removed);
        }

        fastLocalSearch(candidate, deadline, builtByRecombination ? 110 : 75);
        evaluate(candidate);

        bool accept = candidate.fitness < current.fitness;
        if (!accept) {
            double diff = candidate.fitness - current.fitness;
            double prob = exp(-diff / max(1.0, temperature));
            uniform_real_distribution<double> real(0.0, 1.0);
            accept = real(rng) < prob;
        }

        if (accept) current = candidate;

        if (candidate.fitness < best.fitness) {
            best = candidate;
            addElite(candidate);
            noImprove = 0;
        } else {
            if (candidate.violation == 0 && (int)elite.size() < eliteMax) addElite(candidate);
            noImprove++;
        }

        if (noImprove > 160) {
            if (!elite.empty()) {
                uniform_int_distribution<int> pickElite(0, min((int)elite.size() - 1, 5));
                current = elite[pickElite(rng)];
            } else {
                current = savingsInitialSolution();
            }
            vector<int> all = getAllCustomers(current);
            shuffle(all.begin(), all.end(), rng);
            current = splitFromTour(all);
            fastLocalSearch(current, deadline, 80);
            addElite(current);
            noImprove = 0;
        }

        temperature *= 0.997;
        if (temperature < 0.5) temperature = 0.5;
    }

    return best;
}

Solution HGS_Lite(int timeLimitSeconds) {
    auto start = chrono::steady_clock::now();
    auto deadline = start + chrono::seconds(timeLimitSeconds);

    int popSize = 10;
    vector<Solution> population;
    population.reserve(popSize);

    vector<int> baseTour;

    Solution savingsSol = savingsInitialSolution();
    baseTour = getAllCustomers(savingsSol);

    for (int i = 0; i < popSize && chrono::steady_clock::now() < deadline; i++) {
        vector<int> tour;
        tour.reserve(n);

        if (i == 0 && (int)baseTour.size() == n) {
            tour = baseTour;
        } else {
            for (int c = 1; c <= n; c++) tour.push_back(c);
            shuffle(tour.begin(), tour.end(), rng);
        }

        Solution s = splitFromTour(tour);
        if (s.routes.empty()) {
            s = greedyInitialSolution(true);
        }

        tabuSearchEducation(s, 200 + n * 10, deadline);
        evaluate(s);
        population.push_back(s);
    }

    if (population.empty()) {
        Solution fallback = greedyInitialSolution(false);
        evaluate(fallback);
        return fallback;
    }

    sort(population.begin(), population.end(), [](const Solution& a, const Solution& b) {
        return a.fitness < b.fitness;
    });

    Solution best = population.front();
    int iter = 0;

    while (chrono::steady_clock::now() < deadline) {
        iter++;
        int p1 = tournamentSelect(population, 3);
        int p2 = tournamentSelect(population, 3);
        if (p1 == p2) p2 = (p2 + 1) % population.size();

        Solution child = routeBasedCrossover(population[p1], population[p2]);
        if (child.routes.empty()) {
            child = greedyInitialSolution(true);
        }

        tabuSearchEducation(child, 150 + n * 6, deadline);
        if (chrono::steady_clock::now() < deadline) {
            twoOptStarLocalSearch(child, deadline);
            orOptLocalSearch(child, 2, deadline);
        }

        evaluate(child);

        if (child.fitness < best.fitness) {
            best = child;
        }

        population.push_back(child);
        sort(population.begin(), population.end(), [](const Solution& a, const Solution& b) {
            return a.fitness < b.fitness;
        });
        if ((int)population.size() > popSize) {
            population.resize(popSize);
        }

        if (iter % 15 == 0 && chrono::steady_clock::now() < deadline) {
            Solution sp = setPartitionGreedy(population);
            tabuSearchEducation(sp, 120 + n * 4, deadline);
            evaluate(sp);

            if (sp.fitness < best.fitness) {
                best = sp;
            }

            population.push_back(sp);
            sort(population.begin(), population.end(), [](const Solution& a, const Solution& b) {
                return a.fitness < b.fitness;
            });
            if ((int)population.size() > popSize) {
                population.resize(popSize);
            }
        }
    }

    return best;
}

void readInput() {
    string line;
    int dimension = 0;
    int cap = 0;
    int depotId = 1;

    vector<double> x, y;
    vector<int> demand;

    bool readingCoord = false;
    bool readingDemand = false;
    bool readingDepot = false;

    vector<tuple<int, double, double>> coordRows;
    vector<pair<int, int>> demandRows;

    while (getline(cin, line)) {
        if (line.empty()) continue;

        for (char& ch : line) {
            if (ch == ':') ch = ' ';
        }

        stringstream ss(line);
        string key;
        ss >> key;

        if (key == "NAME" || key == "TYPE" || key == "COMMENT" ||
            key == "EDGE_WEIGHT_TYPE" || key == "EOF") {
            continue;
        }

        if (key == "DIMENSION") {
            ss >> dimension;
            continue;
        }

        if (key == "CAPACITY") {
            ss >> cap;
            continue;
        }

        if (key == "NODE_COORD_SECTION") {
            readingCoord = true;
            readingDemand = false;
            readingDepot = false;
            continue;
        }

        if (key == "DEMAND_SECTION") {
            readingCoord = false;
            readingDemand = true;
            readingDepot = false;
            continue;
        }

        if (key == "DEPOT_SECTION") {
            readingCoord = false;
            readingDemand = false;
            readingDepot = true;
            continue;
        }

        if (readingCoord) {
            int id;
            double xx, yy;

            stringstream row(line);
            if (row >> id >> xx >> yy) {
                coordRows.push_back(make_tuple(id, xx, yy));
            }
            continue;
        }

        if (readingDemand) {
            int id, dem;

            stringstream row(line);
            if (row >> id >> dem) {
                demandRows.push_back(make_pair(id, dem));
            }
            continue;
        }

        if (readingDepot) {
            int id;

            stringstream row(line);
            if (row >> id) {
                if (id == -1) {
                    readingDepot = false;
                } else {
                    depotId = id;
                }
            }
            continue;
        }
    }

    if (dimension == 0) {
        dimension = coordRows.size();
    }

    if (dimension <= 1 || cap <= 0) {
        cerr << "Loi doc file .vrp: DIMENSION hoac CAPACITY khong hop le.\n";
        cerr << "DIMENSION = " << dimension << ", CAPACITY = " << cap << "\n";
        exit(1);
    }

    x.assign(dimension + 1, 0);
    y.assign(dimension + 1, 0);
    demand.assign(dimension + 1, 0);

    for (auto& item : coordRows) {
        int id = get<0>(item);
        double xx = get<1>(item);
        double yy = get<2>(item);

        if (id >= 1 && id <= dimension) {
            x[id] = xx;
            y[id] = yy;
        }
    }

    for (auto& item : demandRows) {
        int id = item.first;
        int dem = item.second;

        if (id >= 1 && id <= dimension) {
            demand[id] = dem;
        }
    }

    capacityVehicle = cap;
    n = dimension - 1;

    nodes.assign(n + 1, Customer());

    nodes[0].id = depotId;
    nodes[0].x = x[depotId];
    nodes[0].y = y[depotId];
    nodes[0].demand = 0;

    int idx = 1;

    for (int id = 1; id <= dimension; id++) {
        if (id == depotId) continue;

        nodes[idx].id = id;
        nodes[idx].x = x[id];
        nodes[idx].y = y[id];
        nodes[idx].demand = demand[id];

        idx++;
    }

    buildDistanceMatrix();

    cerr << "Doc file thanh cong: ";
    cerr << "Khach hang = " << n;
    cerr << ", Capacity = " << capacityVehicle;
    cerr << ", Depot = " << depotId << "\n";
}

void printSolution(const Solution& sol, double seconds) {
    cout << fixed << setprecision(4);

    cout << "Tong duong di: " << sol.totalCost << "\n";
    cout << "So giay giai nghiem: " << seconds << "\n";
    cout << "So xe su dung: " << sol.routes.size() << "\n";

    for (int i = 0; i < (int)sol.routes.size(); i++) {
        cout << "Xe " << i + 1 << ": Depot";

        for (int c : sol.routes[i].customers) {
            cout << " -> C" << nodes[c].id;
        }

        cout << " -> Depot";
        cout << " | Tai: " << sol.routes[i].load;
        cout << " | Duong: " << sol.routes[i].cost;
        cout << "\n";
    }
}

int main(int argc, char* argv[]) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    readInput();

    int timeLimitSeconds = 10;
    if (argc > 1) {
        int t = atoi(argv[1]);
        if (t > 0) timeLimitSeconds = t;
    }
    if (argc > 2) {
        unsigned seed = (unsigned)strtoul(argv[2], nullptr, 10);
        rng.seed(seed);
    }

    auto start = chrono::steady_clock::now();

    Solution best = Fast_ALNS(timeLimitSeconds);

    auto end = chrono::steady_clock::now();
    double seconds = chrono::duration<double>(end - start).count();

    evaluate(best);
    printSolution(best, seconds);

    return 0;
}
