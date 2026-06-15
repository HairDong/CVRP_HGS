# Thuật toán đề xuất: Fast Hybrid ALNS cho CVRP

---

## Algorithm 1 — Khởi tạo quần thể (Initialize-Population)

**Input:** Instance CVRP $(V, D, q, Q)$, penalty $\lambda = 1000$, kích thước elite pool $\mu = 24$  
**Output:** Elite pool $P_F$, nghiệm tốt nhất ban đầu $R^*$

```
1.  Xây dựng ma trận khoảng cách D theo chuẩn TSPLIB EUC_2D
       d(i,j) = floor( sqrt((xi-xj)² + (yi-yj)²) + 0.5 )

2.  Tạo 13 nghiệm khởi tạo:
       s₀  ← Clarke-Wright Savings
                 s(i,j) = d(0,i) + d(0,j) - d(i,j), ghép route giảm dần
       s₁..s₁₂ ← Randomized Nearest-Neighbor Greedy
                 Từ depot, chọn ngẫu nhiên trong top-3 khách gần nhất còn chứa được

3.  Cải thiện mỗi nghiệm bằng Fast Local Search (tối đa 120 bước)

4.  R* ← nghiệm có chi phí thấp nhất trong 13 nghiệm

5.  P_F ← { s : violation(s) = 0 }, sắp xếp theo C(s) tăng dần,
           loại trùng (|C(s_i) - C(s_j)| < 1e-6), giữ tối đa μ = 24 nghiệm

6.  return (P_F, R*)
```

---

## Algorithm 2 — Vòng lặp tìm kiếm chính (Fast Hybrid ALNS)

**Input:** Instance CVRP, giới hạn thời gian $T$, $(P_F, R^*)$ từ Algorithm 1  
**Output:** Nghiệm tốt nhất $R^*$

```
 1.  T₀ ← max(20, 0.03 × C(R*))        // nhiệt độ SA ban đầu
     no_improve ← 0
     R_cur ← R*

 2.  while thời gian chạy < T:

     // ── STAGNATION RESTART ──────────────────────────────
 3.    if no_improve > 160:
           Chọn ngẫu nhiên R_base từ top-6 nghiệm trong P_F
           Lấy danh sách tất cả khách từ R_base, shuffle ngẫu nhiên
           R_cur ← Split-DP(danh sách đã shuffle)
                       [ DP: dp[i] = min chi phí phục vụ khách 1..i
                         với mỗi route con không vượt tải Q ]
           R_cur ← Fast-Local-Search(R_cur, 80 bước)
           no_improve ← 0

     // ── SINH NGHIỆM CON (Generate Offspring) ────────────
 4.    Chọn ngẫu nhiên mode ∈ [0, 99]:

       [18%] Route-Based Crossover:
             Chọn p1, p2 từ P_F bằng tournament (k=3)
             Lấy ~50% route từ p1 → ghi nhận các khách đã có
             Bổ sung khách còn thiếu theo thứ tự trong p2
             R_child ← Split-DP(giant tour ghép lại)

       [ 5%] Set-Partition Greedy (chỉ khi |P_F| ≥ 4):
             Gom tất cả route từ P_F làm ứng viên
             Tham lam chọn route có cost/khách nhỏ nhất, không xung đột
             R_child ← nghiệm ghép từ các route được chọn

       [77%] ALNS Destroy & Repair:
             R_child ← R_cur
             removeCount ← adaptive(n, no_improve)
                   [ n/6 bình thường; n/4 nếu no_improve>80;
                     n/3 nếu no_improve>180; + nhiễu ngẫu nhiên ]

             Chọn Destroy operator:
               [25%] Random destroy  — xóa ngẫu nhiên removeCount khách
               [30%] Worst destroy   — xóa khách có saving lớn nhất
                                         saving(v) = d(prev,v)+d(v,next)-d(prev,next)
               [35%] Related destroy — xóa nhóm khách gần nhau
                                         related(s,c) = d(s,c) + |q_s - q_c|
               [10%] Route destroy   — xóa hẳn 1-3 route liên quan

             Chọn Repair operator:
               [50%] Regret-2 repair — chèn khách có regret lớn nhất trước
                                         regret(c) = delta_best2(c) - delta_best1(c)
               [50%] Greedy repair   — chèn từng khách vào vị trí tốt nhất

     // ── CẢI THIỆN CỤC BỘ (Fast Local Search) ───────────
 5.    R_child ← Fast-Local-Search(R_child)
             Thử lần lượt, nếu tìm được move cải thiện thì áp dụng ngay:
             (1) Relocate 1 khách        delta = d_remove + d_insert < 0
             (2) Segment-Relocate len=2  (thử cả chiều ngược)
             (3) Segment-Relocate len=3  (thử cả chiều ngược)
             (4) Cross-Exchange len≤3    (hoán đổi 2 đoạn, thử 4 tổ hợp reverse)
             (5) Swap 2 khách
             (6) 2-Opt* liên route       delta = d(a,d)+d(c,b)-d(a,b)-d(c,d)
             (7) Intra 2-Opt trong route delta = d(a,c)+d(b,d)-d(a,b)-d(c,d)
             Dừng khi không còn move nào tốt hơn

     // ── CHẤP NHẬN NGHIỆM (Simulated Annealing) ──────────
 6.    if f(R_child) < f(R_cur):
           R_cur ← R_child                    // luôn chấp nhận nếu tốt hơn
       else:
           Chấp nhận với xác suất exp( -(f_child - f_cur) / max(1, T₀) )
           if chấp nhận: R_cur ← R_child

     // ── CẬP NHẬT KẾT QUẢ & ELITE ────────────────────────
 7.    if f(R_child) < f(R*):
           R* ← R_child
           Thêm R_child vào P_F (nếu khả thi)
           no_improve ← 0
       else:
           if violation(R_child) = 0 và |P_F| < 24: thêm vào P_F
           no_improve ← no_improve + 1

 8.    T₀ ← max(0.5, 0.997 × T₀)             // làm nguội SA

 9.  end while

10.  return R*
```

---

## Hàm đánh giá nghiệm

$$f(S) = C(S) + \lambda \cdot \sum_{R \in S} \max(0,\ load(R) - Q)$$

- $C(S)$: tổng chi phí tất cả route  
- $\lambda = 1000$: hệ số phạt vi phạm tải  
- Nghiệm hợp lệ khi $violation = 0$, khi đó $f(S) = C(S)$
