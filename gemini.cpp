#include <iostream>
#include <vector>
#include <cmath>
#include <fstream>
#include <sstream>
#include <chrono>
#include <iomanip>
#include <algorithm>
#include <fstream>
#include <sstream>
#include <string>

using namespace std;
using namespace std::chrono;

// Cấu trúc lưu trữ một điểm (Node)
struct Node {
    int id;
    double x, y;
    int demand;
};

// Cấu trúc lưu trữ một tuyến đường (Route) của một xe
struct Route {
    vector<int> path; // Chứa ID các node, ví dụ: 1 -> 5 -> 12 -> 1
    double cost;
    int load;
};

// Tính khoảng cách Euclidean
double calculateDistance(const Node& a, const Node& b) {
    return round(sqrt(pow(a.x - b.x, 2) + pow(a.y - b.y, 2))); 
}

// ---------------------------------------------------------
// CÁC THÀNH PHẦN CỦA THUẬT TOÁN LAI (HYBRID ALGORITHM)
// ---------------------------------------------------------

// 1. ALNS: Toán tử phá hủy (Destroy)
void alnsDestroy(vector<Route>& routes, int numNodesToRemove) {
    // TODO: Implement Shaw Removal, Random Removal, Worst Removal
}

// 2. ALNS: Toán tử sửa chữa (Repair)
void alnsRepair(vector<Route>& routes, vector<int>& unassignedNodes, const vector<Node>& nodes, const vector<vector<double>>& distMatrix, int capacity) {
    // TODO: Implement Greedy Insertion, Regret-k Insertion
}

// 3. Tabu Search: Tối ưu cục bộ (Education phase của HGS)
void tabuSearch(vector<Route>& routes, const vector<vector<double>>& distMatrix) {
    // TODO: Implement 2-opt, Relocate, Exchange kết hợp với Tabu List để tránh kẹt tối ưu cục bộ
}

// 4. HGS: Crossover (Lai ghép tạo cá thể mới)
void hgsCrossover() {
    // TODO: Implement Order Crossover (OX) hoặc PMX trên dạng chuỗi Giant Tour
}

// ---------------------------------------------------------
// HÀM GIẢI CHÍNH
// ---------------------------------------------------------
void solveCVRP(const vector<Node>& nodes, int capacity, int dimension) {
    auto start_time = high_resolution_clock::now();

    // 1. Khởi tạo ma trận khoảng cách
    vector<vector<double>> distMatrix(dimension + 1, vector<double>(dimension + 1, 0.0));
    for (int i = 1; i <= dimension; ++i) {
        for (int j = 1; j <= dimension; ++j) {
            distMatrix[i][j] = calculateDistance(nodes[i], nodes[j]);
        }
    }

    // 2. Khởi tạo nghiệm ban đầu (Heuristic Tham Lam - Greedy)
    // (Trong code thực tế, phần này sẽ tạo một quần thể Initial Population cho HGS)
    vector<Route> bestRoutes;
    vector<bool> visited(dimension + 1, false);
    visited[1] = true; // Depot
    
    int currentTruck = 0;
    int unvisitedCount = dimension - 1;

    // Giả lập logic sinh nghiệm (Placeholder cho logic HGS+ALNS+TS phức tạp)
    // Ở đây dùng Greedy Nearest Neighbor để sinh ra một nghiệm hợp lệ hiển thị
    while (unvisitedCount > 0) {
        Route currentRoute;
        currentRoute.path.push_back(1); // Xuất phát từ Depot
        currentRoute.cost = 0;
        currentRoute.load = 0;
        
        int currentNode = 1;

        while (true) {
            int nextNode = -1;
            double minDistance = 1e9;

            for (int i = 2; i <= dimension; ++i) {
                if (!visited[i] && currentRoute.load + nodes[i].demand <= capacity) {
                    if (distMatrix[currentNode][i] < minDistance) {
                        minDistance = distMatrix[currentNode][i];
                        nextNode = i;
                    }
                }
            }

            if (nextNode == -1) break; // Xe đầy hoặc không còn điểm thỏa mãn

            currentRoute.path.push_back(nextNode);
            currentRoute.cost += minDistance;
            currentRoute.load += nodes[nextNode].demand;
            visited[nextNode] = true;
            currentNode = nextNode;
            unvisitedCount--;
        }

        // Quay về Depot
        currentRoute.path.push_back(1);
        currentRoute.cost += distMatrix[currentNode][1];
        bestRoutes.push_back(currentRoute);
        currentTruck++;
    }

    // 3. Chạy vòng lặp Tối ưu lai (HGS -> ALNS -> TS)
    // TODO: Tích hợp vòng lặp tiến hóa tại đây
    // tabuSearch(bestRoutes, distMatrix);
    // alnsDestroy(...); alnsRepair(...);

    // Tính tổng chi phí cuối cùng
    double totalCost = 0;
    for (const auto& r : bestRoutes) {
        totalCost += r.cost;
    }

    auto end_time = high_resolution_clock::now();
    duration<double> execution_time = end_time - start_time;

    // ---------------------------------------------------------
    // IN KẾT QUẢ THEO ĐÚNG ĐỊNH DẠNG YÊU CẦU
    // ---------------------------------------------------------
    cout << "\n================ RESULT ================\n";
    cout << "Kết quả tổng đường: " << totalCost << "\n";
    cout << fixed << setprecision(4);
    cout << "Số giây giải nghiệm: " << execution_time.count() << "s\n";
    
    for (size_t i = 0; i < bestRoutes.size(); ++i) {
        cout << "Chuỗi xe " << i + 1 << ": C1";
        // Bắt đầu từ 1 vì bỏ qua Depot C1 đầu tiên để in định dạng C1 -> ...
        for (size_t j = 1; j < bestRoutes[i].path.size(); ++j) {
            cout << " -> C" << bestRoutes[i].path[j];
        }
        cout << "\n";
    }
}

int main() {
    // Dữ liệu Input mô phỏng file A-n33-k5.vrp bạn cung cấp
    int dimension = 33;
    int capacity = 100;
    
    // Mảng Nodes (Index từ 1 đến 33 để khớp ID)
    vector<Node> nodes(dimension + 1);
    
    // Khởi tạo Depot (ID 1) và tọa độ, Demand = 0
    nodes[1] = {1, 42, 68, 0};
    
    // Cập nhật tọa độ và demand dựa trên file của bạn (Ví dụ một vài Node đầu và cuối)
    // Bạn cần parse trực tiếp file text vào vector này trong thực tế
    nodes[2] = {2, 77, 97, 5}; nodes[3] = {3, 28, 64, 23}; nodes[4] = {4, 77, 39, 14};
    nodes[5] = {5, 32, 33, 13}; nodes[6] = {6, 32, 8, 8}; nodes[7] = {7, 42, 92, 18};
    nodes[8] = {8, 8, 3, 19}; nodes[9] = {9, 7, 14, 10}; nodes[10] = {10, 82, 17, 18};
    nodes[11] = {11, 48, 13, 20}; nodes[12] = {12, 53, 82, 5}; nodes[13] = {13, 39, 27, 9};
    nodes[14] = {14, 7, 24, 23}; nodes[15] = {15, 67, 98, 9}; nodes[16] = {16, 54, 52, 18};
    nodes[17] = {17, 72, 43, 10}; nodes[18] = {18, 73, 3, 24}; nodes[19] = {19, 59, 77, 13};
    nodes[20] = {20, 58, 97, 14}; nodes[21] = {21, 23, 43, 8}; nodes[22] = {22, 68, 98, 10};
    nodes[23] = {23, 47, 62, 19}; nodes[24] = {24, 52, 72, 14}; nodes[25] = {25, 32, 88, 13};
    nodes[26] = {26, 39, 7, 14}; nodes[27] = {27, 17, 8, 2}; nodes[28] = {28, 38, 7, 23};
    nodes[29] = {29, 58, 74, 15}; nodes[30] = {30, 82, 67, 8}; nodes[31] = {31, 42, 7, 20};
    nodes[32] = {32, 68, 82, 24}; nodes[33] = {33, 7, 48, 3};

    solveCVRP(nodes, capacity, dimension);

    return 0;
}