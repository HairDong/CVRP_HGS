# Algorithm Description — Paper-Ready Version
> Phân tích từ `cvrp-hgs.cpp` · Dùng để viết bài báo khoa học

---

## ❶ Nhận xét về file ALGORITHM_DESCRIPTION.md hiện tại

### ✅ Những gì đã đúng và đủ
| Mục | Đánh giá |
|-----|-----------|
| Mô hình CVRP (Section 2) | Đủ |
| Công thức khoảng cách EUC_2D (Section 3) | Đúng |
| Hàm chi phí route, violation, fitness (Section 4–5) | Đúng, đủ |
| Greedy / Savings / Split initialization (Section 6) | Đủ |
| 4 destroy operators (Section 7) | Đúng nhưng thiếu chi tiết adaptive weight |
| 2 repair operators (Section 8) | Đúng |
| Local search neighborhoods (Section 9) | Thiếu 2 operator quan trọng |
| Pseudocode chính (Section 13) | Đúng nhưng chưa thể hiện các tham số cụ thể |
| Bảng ánh xạ hàm (Section 15) | Đủ |

### ⚠️ Những điểm còn thiếu / sai
1. **`fastIntraOrOpt` chưa được đề cập** — operator này thử relocate segment _trong cùng route_ (kể cả reverse), khác với `fastIntraTwoOpt`.
2. **Adaptive operator weight trong `Fast_ALNS`** — file chỉ đề cập ALNS_HGS_TS (solver phụ), còn `Fast_ALNS` dùng fixed probability (25/30/45) không có score-based weight.
3. **Cơ chế adaptive penalty** chỉ có trong `ALNS_HGS_TS`, **không có** trong `Fast_ALNS` — cần làm rõ.
4. **Stagnation restart** trong `Fast_ALNS` (dòng 1836–1849): chọn nghiệm từ elite, shuffle giant tour, split lại, local search — file hiện tại mô tả chưa chi tiết.
5. **Elite pool deduplication**: loại bỏ nghiệm có `totalCost` trùng nhau — chưa được nhắc đến.
6. **Tham số cụ thể** của `Fast_ALNS` chưa được liệt kê đầy đủ.
7. **`orOptLocalSearch`** và **`twoOptStarLocalSearch`** xuất hiện trong `ALNS_HGS_TS` nhưng _không được dùng_ trong `Fast_ALNS`.
8. **Tên thuật toán** (Section 1) vẫn ghi `chatgpt.cpp` — nên cập nhật thành `cvrp-hgs.cpp`.

---

## ❷ Mô hình bài toán CVRP (chuẩn bài báo)

Cho đồ thị đầy đủ $G = (V, E)$ với:
- $V = \{0, 1, \ldots, n\}$: tập đỉnh, $0$ là depot.
- $E = \{(i,j) \mid i \neq j\}$: tập cạnh.
- $d_{ij}$: khoảng cách từ $i$ đến $j$.
- $q_i$: nhu cầu của khách hàng $i$, $q_0 = 0$.
- $Q$: sức chứa tối đa mỗi xe.

**Mục tiêu:** Tìm tập route $\mathcal{R} = \{R_1, \ldots, R_k\}$ sao cho:
- Mỗi khách hàng $i \in \{1,\ldots,n\}$ xuất hiện đúng một lần.
- Mỗi route bắt đầu và kết thúc tại depot $0$.
- $\sum_{v \in R_j} q_v \leq Q$ với mọi $j$.
- Tổng $\sum_{j} c(R_j)$ nhỏ nhất.

### Khoảng cách (TSPLIB EUC_2D)

$$d_{ij} = \left\lfloor \sqrt{(x_i - x_j)^2 + (y_i - y_j)^2} + 0.5 \right\rfloor$$

```cpp
double euclidDist(const Customer& a, const Customer& b) {
    double dx = a.x - b.x, dy = a.y - b.y;
    return floor(sqrt(dx*dx + dy*dy) + 0.5);
}
```

### Chi phí route

$$c(R) = d_{0,v_1} + \sum_{i=1}^{k-1} d_{v_i, v_{i+1}} + d_{v_k, 0}$$

### Hàm fitness (có penalty)

$$f(S) = C(S) + \lambda \cdot \sum_{R \in S} \max\!\left(0,\, \text{load}(R) - Q\right)$$

với $\lambda = 1000$ (mặc định), $C(S) = \sum_{R \in S} c(R)$.

---

## ❸ Khởi tạo nghiệm

### 3.1 Clarke–Wright Savings

Savings của cặp $(i, j)$:
$$s_{ij} = d_{0i} + d_{0j} - d_{ij}$$

Sắp xếp giảm dần, hợp nhất hai route nếu $i$, $j$ ở đầu/cuối route và tổng tải $\leq Q$.

### 3.2 Randomized Nearest-Neighbor Greedy

Bắt đầu từ depot, lặp chọn khách hàng chưa phục vụ gần nhất còn chứa được. Khi `randomized=true`, chọn ngẫu nhiên trong top-3 ứng viên.

### 3.3 Giant-Tour Split (DP)

Cho chuỗi khách hàng `tour[1..n]`:
$$dp[i] = \min_{\substack{j \leq i \\ \text{load}(j..i) \leq Q}} \left( dp[j-1] + c(\text{route}(j..i)) \right)$$

```cpp
// Trạng thái: dp[0] = 0, dp[i] = chi phí tối ưu phục vụ tour[1..i]
for (int i = 1; i <= m; i++) {
    int load = 0;
    for (int j = i; j >= 1; j--) {
        load += nodes[tour[j-1]].demand;
        if (load > capacityVehicle) break;
        double cost = d[0][tour[j-1]] + segDist(j-1, i-1) + d[tour[i-1]][0];
        dp[i] = min(dp[i], dp[j-1] + cost);
    }
}
```

---

## ❹ Destroy Operators

| Operator | Tỷ lệ chọn (Fast_ALNS) | Mô tả |
|----------|------------------------|-------|
| Random destroy | 25% | Xóa ngẫu nhiên `removeCount` khách |
| Worst destroy | 30% | Xóa khách có đóng góp tuyến đường lớn nhất |
| Related destroy | 35%~45% | Xóa nhóm khách gần nhau về vị trí & nhu cầu |
| Route destroy | ~10% (khi stagnate) | Xóa 1–3 route liên quan |

### Worst destroy — đóng góp của khách $v$

$$\text{saving}(v) = d_{\text{prev},v} + d_{v,\text{next}} - d_{\text{prev},\text{next}}$$

### Related destroy — độ liên quan giữa seed $s$ và khách $c$

$$\text{related}(s, c) = d_{sc} + |q_s - q_c|$$

### Số lượng xóa

```text
baseRemove = max(6, n/6)
if noImprove > 80:  baseRemove = max(baseRemove, n/4)
if noImprove > 180: baseRemove = max(baseRemove, n/3)
removeCount = min(n-1, baseRemove + uniform(0, n/7))
```

---

## ❺ Repair Operators

### 5.1 Greedy Repair

Chi phí chèn khách $c$ vào giữa `prev` và `next`:
$$\Delta_{\text{insert}}(c) = d_{\text{prev},c} + d_{c,\text{next}} - d_{\text{prev},\text{next}} + \lambda \cdot \max(0, \text{newLoad} - Q)$$

Chọn vị trí có $\Delta_{\text{insert}}$ nhỏ nhất; nếu tạo route mới rẻ hơn thì tạo route mới.

### 5.2 Regret-2 Repair

$$\text{regret}(c) = \Delta^{(2)}_{\text{best}}(c) - \Delta^{(1)}_{\text{best}}(c)$$

Chèn khách có `regret` lớn nhất trước.

```cpp
// Với mỗi khách c chưa được chèn:
sort(options); // theo delta tăng dần
regret = options[1].delta - options[0].delta;
// Chọn c có regret lớn nhất, chèn vào options[0]
```

---

## ❻ Local Search Neighborhoods (`fastLocalSearch`)

Thứ tự ưu tiên (first-improvement cascade):

```
1. fastRelocate        — di chuyển 1 khách
2. fastSegmentRelocate(2) — di chuyển đoạn 2 khách (+ reverse)
3. fastSegmentRelocate(3) — di chuyển đoạn 3 khách (+ reverse)
4. fastCrossExchange(3)   — hoán đổi đoạn 1–3 giữa 2 route (+ reverse)
5. fastSwap            — hoán đổi 2 khách
6. fastTwoOptStar      — 2-opt* liên route
7. fastIntraTwoOpt     — 2-opt trong route
```

### Relocate delta

$$\Delta = \underbrace{(d_{\text{prev},\text{next}} - d_{\text{prev},c} - d_{c,\text{next}})}_{\text{delta remove}} + \underbrace{(d_{\text{before},c} + d_{c,\text{after}} - d_{\text{before},\text{after}})}_{\text{delta insert}}$$

### 2-opt* liên route

Cắt route $R_1$ sau $a$, route $R_2$ sau $c$, nối chéo:
$$\Delta = d_{a,d} + d_{c,b} - d_{a,b} - d_{c,d}$$

Chấp nhận nếu $\Delta < 0$ và cả hai route mới đều không vượt tải:
$$\text{newLoad}_1 = \text{prefix}_1 + \text{tail}_2 \leq Q$$
$$\text{newLoad}_2 = \text{prefix}_2 + \text{tail}_1 \leq Q$$

### Cross-exchange

Hoán đổi segment $s_1$ (từ $R_1$, dài $l_1$) với segment $s_2$ (từ $R_2$, dài $l_2$), $l_1, l_2 \in \{1,2,3\}$:

$$\Delta = (d_{p_1, s_2^{\text{first}}} + \text{inner}(s_2) + d_{s_2^{\text{last}}, n_1}) + (d_{p_2, s_1^{\text{first}}} + \text{inner}(s_1) + d_{s_1^{\text{last}}, n_2}) - \text{oldCost}$$

Thử cả 4 tổ hợp (reverse $s_1$ / reverse $s_2$).

### Intra-route 2-opt

Đảo đoạn $[i, j]$ trong cùng route:
$$\Delta = d_{a,c} + d_{b,d} - d_{a,b} - d_{c,d}$$

với $a = \text{pred}(i)$, $b = \text{route}[i]$, $c = \text{route}[j]$, $d = \text{succ}(j)$.

---

## ❼ Elite Pool & Recombination (HGS-inspired)

### Elite pool
- Kích thước: `eliteMax = 24`.
- Chỉ chứa nghiệm **khả thi** (`violation = 0`).
- **Deduplication**: loại nghiệm có `totalCost` trùng (sai số $< 10^{-6}$).
- Sắp xếp theo `totalCost` tăng dần.

### Route-based crossover (18% xác suất)

```text
1. Chọn p1, p2 từ elite bằng tournament selection (k=3).
2. Lấy ngẫu nhiên ~50% route từ p1 → ghi nhớ các khách đã chọn.
3. Bổ sung khách còn thiếu theo thứ tự xuất hiện trong p2.
4. Áp dụng Giant-Tour Split để tạo nghiệm con.
```

### Set-partition greedy (5% xác suất, khi |elite| ≥ 4)

```text
1. Thu thập tất cả route khả thi từ elite.
2. Tham lam: chọn route có cost/khách nhỏ nhất, không xung đột.
3. Tiếp tục đến khi mọi khách được bao phủ.
```

$$\text{score}(R) = \frac{c(R)}{|R|}$$

---

## ❽ Simulated Annealing Acceptance

$$P(\text{accept}) = \exp\!\left(-\frac{f(\text{cand}) - f(\text{cur})}{\max(1.0,\, T)}\right)$$

- Nhiệt độ ban đầu: $T_0 = \max(20,\; 0.03 \times C(S_{\text{best}}^{\text{init}}))$
- Làm nguội: $T \leftarrow 0.997 \times T$ mỗi vòng lặp
- Chặn dưới: $T \geq 0.5$

---

## ❾ Stagnation Restart

Khi `noImprove > 160`:
```text
1. Chọn ngẫu nhiên nghiệm từ elite[0..min(5, |elite|-1)].
2. Lấy giant tour, shuffle ngẫu nhiên.
3. Split lại bằng DP.
4. Áp dụng fastLocalSearch (80 moves).
5. Thêm vào elite, reset noImprove = 0.
```

---

## ❿ Pseudocode Hoàn Chỉnh

```
Algorithm: Fast_ALNS (cvrp-hgs.cpp)
─────────────────────────────────────────────────────────────────
Input:  CVRP instance (n customers, capacity Q), time limit T_max
Output: Best feasible solution S_best

INITIALIZATION
  S_savings  ← Clarke-Wright savings solution
  S_1..12    ← 12 randomized greedy solutions
  For each S_i: fastLocalSearch(S_i, maxMoves=120)
  S_current ← argmin fitness over all S_i
  S_best    ← S_current
  T         ← max(20, 0.03 × C(S_best))
  Elite     ← {S_i : violation(S_i) = 0}, deduplicated, |Elite| ≤ 24
  noImprove ← 0

MAIN LOOP (while elapsed < T_max):
  ── Candidate generation ──
  if |Elite| ≥ 2:
    mode ← uniform(0,99)
    if mode < 18:   S_cand ← routeBasedCrossover(Elite)    // 18%
    elif mode < 23 and |Elite| ≥ 4:
                    S_cand ← setPartitionGreedy(Elite)      //  5%
    else:           goto DESTROY_REPAIR                     // 77%
  else: goto DESTROY_REPAIR

  DESTROY_REPAIR:
    S_cand ← S_current
    removeCount ← adaptive(n, noImprove)
    op_d ← sample{random:25%, worst:30%, related:35%, route:10%}
    op_r ← sample{regret:50%, greedy:50%}
    Apply op_d → removed customers
    Apply op_r → reinsert removed customers

  ── Education ──
  fastLocalSearch(S_cand, maxMoves = 110 if recombination else 75)

  ── Acceptance (SA) ──
  if f(S_cand) < f(S_current): accept
  else: accept with prob exp(-(f_cand - f_cur) / max(1, T))
  if accept: S_current ← S_cand

  ── Update best & elite ──
  if f(S_cand) < f(S_best):
    S_best ← S_cand; addElite(S_cand); noImprove ← 0
  else:
    if feasible(S_cand) and |Elite| < 24: addElite(S_cand)
    noImprove++

  ── Stagnation restart ──
  if noImprove > 160:
    S_current ← shuffleSplitLocalSearch(Elite)
    noImprove ← 0

  T ← max(0.5, 0.997 × T)

Return S_best
```

---

## ⓫ Tham số chính (Fast_ALNS)

| Tham số | Giá trị | Ghi chú |
|---------|---------|---------|
| `eliteMax` | 24 | Kích thước elite pool |
| `penaltyCapacity` (λ) | 1000.0 | Penalty tải cố định |
| `temperature` khởi tạo | max(20, 0.03×C₀) | Phụ thuộc nghiệm ban đầu |
| Hệ số làm nguội | 0.997 | Mỗi vòng lặp |
| `T_min` | 0.5 | Chặn dưới nhiệt độ |
| `noImprove` restart | 160 | Ngưỡng stagnation |
| Xác suất crossover | 18% | mode < 18 |
| Xác suất set-partition | 5% | 18 ≤ mode < 23 |
| `maxMoves` local search | 75 / 110 | ALNS / Recombination |
| Số starts ban đầu | 13 | 1 savings + 12 greedy |
| Tournament size | k = 3 | Chọn từ elite |

---

## ⓬ Đề xuất tên thuật toán và abstract cho bài báo

### Tên gọi đề xuất

> **Fast Hybrid ALNS with Elite-Pool Recombination for CVRP**

Hoặc viết tắt: **FH-ALNS**

### Abstract đề xuất (English)

> We present a hybrid metaheuristic for the Capacitated Vehicle Routing Problem (CVRP) implemented entirely using C++ STL without external optimization libraries. The proposed method, termed Fast Hybrid ALNS (FH-ALNS), integrates adaptive large neighborhood search with elite-pool-based recombination inspired by Hybrid Genetic Search (HGS). Construction heuristics include Clarke–Wright savings and randomized nearest-neighbor greedy, combined with a DP-based giant-tour split procedure. The iterative improvement phase employs four destroy operators (random, worst, related, and route-based) paired with greedy and regret-2 repair operators. A granular local search cascade applies seven neighborhood moves: single-customer relocate, segment relocate (length 2–3) with reversal, cross-exchange (length 1–3) with reversal, swap, inter-route 2-opt*, and intra-route 2-opt. An elite pool of up to 24 feasible solutions drives route-based crossover and set-partition greedy recombination. Simulated annealing governs acceptance of non-improving moves, and stagnation restarts are triggered after 160 consecutive non-improving iterations. Experiments on the X-benchmark instances demonstrate competitive solution quality.

---

## ⓭ Bảng ánh xạ hàm (cập nhật)

| Thành phần | Hàm trong code |
|---|---|
| Đọc instance CVRP | `readInput()` |
| Ma trận khoảng cách | `buildDistanceMatrix()` |
| Đánh giá nghiệm | `evaluate()` |
| Savings initialization | `savingsInitialSolution()` |
| Greedy initialization | `greedyInitialSolution(true/false)` |
| Split giant tour (DP) | `splitFromTour()` |
| Random destroy | `randomDestroy()` |
| Worst destroy | `worstDestroy()` |
| Related destroy | `relatedDestroy()` |
| Route destroy | `routeDestroy()` |
| Greedy repair | `greedyRepair()` |
| Regret-2 repair | `regretRepair()` |
| Route-based crossover | `routeBasedCrossover()` |
| Set-partition greedy | `setPartitionGreedy()` |
| Local search cascade | `fastLocalSearch()` |
| Relocate | `fastRelocate()` |
| Segment relocate (+rev) | `fastSegmentRelocate(len)` |
| Swap | `fastSwap()` |
| 2-opt* inter-route | `fastTwoOptStar()` |
| Intra-route 2-opt | `fastIntraTwoOpt()` |
| Cross-exchange (+rev) | `fastCrossExchange(maxLen=3)` |
| Intra-route Or-opt (+rev) | `fastIntraOrOpt(len)` ← **chưa có trong file cũ** |
| Solver chính | `Fast_ALNS()` |
| Solver phụ (Tabu) | `ALNS_HGS_TS()` |
| Solver phụ (HGS) | `HGS_Lite()` |
