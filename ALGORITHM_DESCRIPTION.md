# Mo ta thuat toan va co che cai dat

## 1. Co dung thu vien dac biet khong?

Code trong `chatgpt.cpp` khong dung thu vien toi uu dac biet cho VRP, HGS, ALNS hay Tabu Search.

File chi include:

```cpp
#include <bits/stdc++.h>
using namespace std;
```

Nghia la chuong trinh chi dung cac thanh phan C++ STL co san nhu `vector`, `sort`, `shuffle`, `mt19937`, `chrono`, `set`, `tuple`, `priority` logic, v.v.

Ba nhom thuat toan/chuc nang chinh deu duoc viet bang ham thuan trong code:

- ALNS-like search: destroy/repair + simulated annealing acceptance.
- HGS-like mechanism: elite pool, route-based crossover, set-partition greedy.
- Tabu/local search: tabu education co san trong file va bo local search nhanh hien dang dung trong solver chinh.

Solver chinh hien tai goi:

```cpp
Solution best = Fast_ALNS(timeLimitSeconds);
```

Do do ket qua benchmark hien tai den tu cac ham tu cai dat, khong phai goi thu vien ngoai.

## 2. Mo hinh bai toan CVRP

Cho tap diem:

- Depot: diem 0.
- Khach hang: tap `V = {1, 2, ..., n}`.
- Moi khach hang `i` co toa do `(x_i, y_i)` va nhu cau `q_i`.
- Moi xe co suc chua `Q`.

Muc tieu: tim tap route bat dau va ket thuc tai depot, moi khach duoc phuc vu dung 1 lan, tai moi route khong vuot qua `Q`, tong quang duong nho nhat.

## 3. Cong thuc khoang cach

Instance dung chuan TSPLIB `EUC_2D`. Khoang cach giua hai diem `i, j`:

```text
d(i, j) = round(sqrt((x_i - x_j)^2 + (y_i - y_j)^2))
```

Trong code:

```cpp
return floor(dist + 0.5);
```

## 4. Cong thuc chi phi route

Voi route:

```text
R = (v_1, v_2, ..., v_k)
```

Chi phi route:

```text
c(R) = d(0, v_1) + sum_{i=1}^{k-1} d(v_i, v_{i+1}) + d(v_k, 0)
```

Tai route:

```text
load(R) = sum_{v in R} q_v
```

Tong chi phi nghiem:

```text
C(S) = sum_{R in S} c(R)
```

## 5. Ham danh gia co penalty

Neu route vuot tai, code tinh vi pham:

```text
violation(S) = sum_{R in S} max(0, load(R) - Q)
```

Fitness:

```text
fitness(S) = C(S) + lambda * violation(S)
```

Trong code:

```cpp
sol.fitness = sol.totalCost + penaltyCapacity * sol.violation;
```

Voi:

```cpp
double penaltyCapacity = 1000.0;
```

Nghiem hop le co `violation = 0`, khi do:

```text
fitness(S) = C(S)
```

## 6. Khoi tao nghiem

Code co nhieu co che khoi tao:

### 6.1 Greedy nearest insertion

Ham:

```cpp
greedyInitialSolution(bool randomized)
```

Co che:

1. Bat dau tu depot.
2. Chon khach hang gan diem hien tai nhat ma khong lam vuot tai.
3. Neu `randomized = true`, chon ngau nhien trong top 3 ung vien gan nhat.
4. Lap den khi het khach.

### 6.2 Clarke-Wright savings

Ham:

```cpp
savingsInitialSolution()
```

Savings cua cap khach `i, j`:

```text
s(i, j) = d(0, i) + d(0, j) - d(i, j)
```

Y nghia: neu ghep `i` va `j` vao cung route, ta tiet kiem duoc bao nhieu so voi di rieng tung route.

Co che:

1. Ban dau moi khach la mot route rieng.
2. Sap xep cac cap theo savings giam dan.
3. Ghep hai route neu `i, j` nam o dau/cuoi route va tong tai khong vuot `Q`.

### 6.3 Split from tour

Ham:

```cpp
splitFromTour(const vector<int>& tour)
```

Cho mot thu tu khach hang duy nhat, ham dung dynamic programming de cat thanh cac route hop le.

DP:

```text
dp[i] = chi phi nho nhat de phuc vu tour[1..i]
```

Chuyen trang thai:

```text
dp[i] = min_{j <= i, load(j..i) <= Q} dp[j-1] + cost(route tour[j..i])
```

## 7. Destroy operators trong ALNS

Trong `Fast_ALNS`, moi vong lap tao candidate bang cach pha mot phan nghiem hien tai, sau do sua lai.

### 7.1 Random destroy

Ham:

```cpp
randomDestroy(sol, removed, removeCount)
```

Chon ngau nhien `removeCount` khach hang va dua vao danh sach `removed`.

### 7.2 Worst destroy

Ham:

```cpp
worstDestroy(sol, removed, removeCount)
```

Do muc dong gop cua khach `v` nam giua `prev` va `next`:

```text
saving(v) = d(prev, v) + d(v, next) - d(prev, next)
```

Khach co `saving` lon la khach lam route dai hon nhieu, nen bi xoa truoc.

### 7.3 Related destroy

Ham:

```cpp
relatedDestroy(sol, removed, removeCount)
```

Chon mot seed customer, sau do xoa cac khach gan seed theo do do:

```text
related(seed, c) = d(seed, c) + |q_seed - q_c|
```

Khach cang gan ve vi tri va nhu cau cang de bi xoa cung nhau.

### 7.4 Route destroy

Ham:

```cpp
routeDestroy(sol, removed, routeCount)
```

Xoa nguyen 1-3 route, uu tien route co chi phi cao hoac lien quan gan voi route da chon. Operator nay chi kich hoat nhieu hon khi stagnation, giup pha cau truc route bi ket.

## 8. Repair operators

### 8.1 Greedy repair

Ham:

```cpp
greedyRepair(sol, removed)
```

Voi moi khach bi xoa, chen vao vi tri co chi phi tang nho nhat.

Chi phi chen khach `c` vao giua `prev` va `next`:

```text
delta_insert = d(prev, c) + d(c, next) - d(prev, next)
```

Neu tao route moi re hon, code co the tao route moi.

### 8.2 Regret repair

Ham:

```cpp
regretRepair(sol, removed)
```

Voi moi khach, tinh hai vi tri chen tot nhat:

```text
best_1(c), best_2(c)
```

Regret:

```text
regret(c) = best_2(c) - best_1(c)
```

Khach co regret cao duoc chen truoc, vi neu khong chen ngay thi co the mat vi tri tot.

## 9. Local search neighborhoods

Solver chinh dung:

```cpp
fastLocalSearch(candidate, deadline, maxMoves)
```

Cac move duoc thu theo thu tu:

1. Relocate 1 khach.
2. Segment relocate doan 2 khach.
3. Segment relocate doan 3 khach.
4. Cross-exchange giua hai route.
5. Swap 2 khach.
6. 2-opt* lien route.
7. Intra-route 2-opt.

### 9.1 Relocate

Di chuyen mot khach `c` tu route A sang route B.

Delta xoa:

```text
delta_remove = d(prev, next) - d(prev, c) - d(c, next)
```

Delta chen:

```text
delta_add = d(before, c) + d(c, after) - d(before, after)
```

Tong:

```text
delta = delta_remove + delta_add
```

Move duoc chap nhan neu `delta < 0` va tai hop le.

### 9.2 Segment relocate

Tuong tu relocate, nhung di chuyen ca doan lien tiep 2 hoac 3 khach. Code co thu ca chieu goc va chieu dao cua doan.

### 9.3 Swap

Doi cho hai khach `a` va `b`. Neu khac route, phai thoa:

```text
load(route_1) - q_a + q_b <= Q
load(route_2) - q_b + q_a <= Q
```

### 9.4 2-opt* lien route

Cat hai route tai hai vi tri, sau do doi phan duoi cua hai route.

Neu route 1 co canh `(a, b)`, route 2 co canh `(c, d)`, delta:

```text
delta = d(a, d) + d(c, b) - d(a, b) - d(c, d)
```

Chi chap nhan neu hai route moi khong vuot tai.

### 9.5 Intra-route 2-opt

Dao nguoc mot doan trong cung route de giam duong di.

Voi hai canh bi cat `(a, b)` va `(c, d)`:

```text
delta = d(a, c) + d(b, d) - d(a, b) - d(c, d)
```

### 9.6 Cross-exchange

Doi hai doan ngan giua hai route, moi doan dai 1-3 khach. Code thu ca chieu dao cua tung doan.

Day la move quan trong voi instance lon vi no thay doi cau truc route manh hon swap/relocate don.

## 10. Elite pool va HGS-like recombination

Trong `Fast_ALNS`, code duy tri `elite` gom cac nghiem hop le tot.

### 10.1 Route-based crossover

Ham:

```cpp
routeBasedCrossover(parent1, parent2)
```

Co che:

1. Lay mot so route tu parent 1.
2. Them cac khach con thieu theo thu tu xuat hien trong parent 2.
3. Dung `splitFromTour` de tach tour thanh route hop le.

### 10.2 Set-partition greedy

Ham:

```cpp
setPartitionGreedy(elite)
```

Lay route hop le tu cac nghiem elite lam ung vien, sau do chon route co:

```text
score(route) = cost(route) / number_of_customers(route)
```

va khong xung dot khach da chon.

Day la bien the greedy cua set partitioning, khong giai exact MIP.

## 11. Simulated annealing acceptance

Neu candidate tot hon current:

```text
accept = true
```

Neu candidate xau hon, chap nhan voi xac suat:

```text
P(accept) = exp(-(fitness(candidate) - fitness(current)) / T)
```

Trong code:

```cpp
double prob = exp(-diff / max(1.0, temperature));
```

Nhiet do giam dan:

```text
T = 0.997 * T
```

Va co san duoi:

```text
T >= 0.5
```

## 12. Tabu Search trong code

File van co ham:

```cpp
tabuSearchEducation(...)
```

Ham nay dung trong cac solver phu `ALNS_HGS_TS` va `HGS_Lite`, khong phai solver chinh hien tai. Solver chinh hien tai la `Fast_ALNS`.

Co che tabu:

- Xet cac move relocate, swap, intra-route 2-opt.
- Luu cap move `(a, b)` vao tabu list.
- Move tabu bi cam den khi het `expire`.
- Co aspiration: neu move tabu tao nghiem tot hon best thi van co the duoc chap nhan trong mot so truong hop.

## 13. Pseudocode thuat toan de dua vao bai

```text
Algorithm: Fast_ALNS_HGS_for_CVRP
Input:
    CVRP instance, time limit T_max, capacity Q
Output:
    Best feasible solution S_best

1. Build distance matrix using TSPLIB EUC_2D rounding.
2. Generate initial solutions:
       S_0 = Clarke-Wright savings solution
       S_i = randomized greedy solutions
3. Improve each initial solution by fast local search.
4. Set:
       S_current = best initial solution
       S_best = S_current
       Elite = set of best feasible initial solutions
       temperature = max(20, 0.03 * cost(S_best))

5. While elapsed time < T_max:
       With small probability:
           Build candidate by route-based crossover from Elite
           or by greedy set-partitioning from Elite
       Otherwise:
           S_candidate = copy(S_current)
           Choose destroy operator:
               random destroy
               worst destroy
               related destroy
               route destroy if stagnated
           Remove selected customers/routes.
           Choose repair operator:
               greedy repair
               regret repair
           Reinsert removed customers.

       Apply fast local search:
           relocate
           segment relocate 2/3
           cross-exchange
           swap
           2-opt*
           intra-route 2-opt

       If fitness(S_candidate) < fitness(S_current):
           accept S_candidate
       Else:
           accept with probability exp(-(fitness(S_candidate)-fitness(S_current))/temperature)

       If S_candidate is better than S_best:
           S_best = S_candidate
           add S_candidate to Elite

       If stagnation is detected:
           restart from an elite solution
           shuffle its giant tour
           split and locally improve it

       temperature = max(0.5, 0.997 * temperature)

6. Return S_best.
```

## 14. De xuat trinh bay trong bai/report

Ten goi de viet trong bai:

```text
Hybrid ALNS with HGS-style Elite Recombination and Granular Local Search
```

Mo ta ngan:

```text
We propose a hybrid metaheuristic for CVRP that combines adaptive large
neighborhood search, route-based recombination inspired by hybrid genetic
search, and a set of efficient local-search neighborhoods. The method does
not rely on external optimization libraries. It constructs initial solutions
using savings and randomized greedy heuristics, iteratively applies destroy
and repair operators, improves candidates by relocate, segment relocate,
swap, 2-opt*, intra-route 2-opt, and cross-exchange moves, and maintains an
elite pool for recombination and diversification. A simulated annealing
criterion is used to accept non-improving moves and avoid premature
convergence.
```

## 15. Mapping giua thuat toan va ham trong code

| Thanh phan | Ham trong code |
|---|---|
| Doc instance CVRP | `readInput()` |
| Ma tran khoang cach | `buildDistanceMatrix()` |
| Danh gia nghiem | `evaluate()` |
| Savings initialization | `savingsInitialSolution()` |
| Randomized greedy initialization | `greedyInitialSolution(true)` |
| Split giant tour | `splitFromTour()` |
| Random destroy | `randomDestroy()` |
| Worst destroy | `worstDestroy()` |
| Related destroy | `relatedDestroy()` |
| Route destroy | `routeDestroy()` |
| Greedy repair | `greedyRepair()` |
| Regret repair | `regretRepair()` |
| Route-based crossover | `routeBasedCrossover()` |
| Set-partition greedy | `setPartitionGreedy()` |
| Local search controller | `fastLocalSearch()` |
| Relocate | `fastRelocate()` |
| Segment relocate | `fastSegmentRelocate()` |
| Swap | `fastSwap()` |
| 2-opt* | `fastTwoOptStar()` |
| Intra-route 2-opt | `fastIntraTwoOpt()` |
| Cross-exchange | `fastCrossExchange()` |
| Solver chinh | `Fast_ALNS()` |

