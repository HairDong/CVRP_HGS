

### Bước 1 – Compile
```powershell
cd "d:\NextJs\CVRP-test"
g++ -O2 -std=c++17 -o cvrp-hgs.exe cvrp-hgs.cpp
```

### Bước 2 – Chạy với X-n641-k35 (giới hạn 60 giây)
```powershell
Get-Content "A-VRP\G-n262-k25.vrp" | .\cvrp-hgs.exe 120
```

Hoặc dùng `cmd`:
```cmd
cvrp-hgs.exe 60 < X-VRP\X-n641-k35.vrp
```

---

> **Lưu ý:** Nếu chưa có `g++`, cài **MinGW-w64** hoặc dùng **MSYS2** (`pacman -S mingw-w64-ucrt-x86_64-gcc`).
