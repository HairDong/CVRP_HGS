#!/usr/bin/env python3
import argparse
import csv
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


BENCHMARKS = [
    ("A-n32-k5", 784, 25),
    ("A-n33-k5", 661, 26),
    ("A-n33-k6", 742, 26),
    ("A-n34-k5", 778, 27),
    ("A-n36-k5", 799, 29),
    ("A-n37-k5", 669, 29),
    ("A-n37-k6", 949, 29),
    ("A-n38-k5", 730, 30),
    ("A-n39-k5", 822, 31),
    ("A-n39-k6", 831, 31),
    ("A-n44-k7", 937, 35),
    ("A-n45-k6", 944, 36),
    ("A-n45-k7", 1146, 36),
    ("A-n46-k7", 914, 37),
    ("A-n48-k7", 1073, 38),
    ("A-n53-k7", 1016, 53),
    ("A-n54-k7", 1167, 54),
    ("A-n55-k9", 1073, 55),
    ("A-n60-k9", 1354, 60),
    ("A-n61-k9", 1034, 61),
    ("A-n62-k8", 1288, 62),
    ("A-n63-k10", 1314, 63),
    ("A-n63-k9", 1616, 63),
    ("A-n64-k9", 1401, 64),
    ("A-n65-k9", 1174, 65),
    ("A-n69-k9", 1159, 69),
    ("A-n80-k10", 1763, 80),
    ("G-n262-k25", 6119, 601),
    ("M-n151-k12", 1053, 301),
    ("M-n200-k17", 1373, 361),
]


TOTAL_RE = re.compile(r"Tong duong di:\s*([0-9]+(?:\.[0-9]+)?)")
SECONDS_RE = re.compile(r"So giay giai nghiem:\s*([0-9]+(?:\.[0-9]+)?)")
VEHICLES_RE = re.compile(r"So xe su dung:\s*([0-9]+)")


def compile_solver(root: Path, source: Path, exe: Path) -> None:
    cmd = ["g++", "-std=c++14", "-O2", str(source), "-o", str(exe)]
    print("Compiling:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=root, check=True)


def run_instance(exe: Path, instance: Path, seconds: int, seed: Optional[int]) -> dict:
    cmd = [str(exe), str(seconds)]
    if seed is not None:
        cmd.append(str(seed))

    input_text = instance.read_text(encoding="utf-8", errors="replace")
    proc = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=seconds + 30,
    )

    output = proc.stdout + "\n" + proc.stderr
    total_match = TOTAL_RE.search(output)
    seconds_match = SECONDS_RE.search(output)
    vehicles_match = VEHICLES_RE.search(output)

    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "our_result": int(round(float(total_match.group(1)))) if total_match else None,
        "cpu_time": float(seconds_match.group(1)) if seconds_match else None,
        "vehicles": int(vehicles_match.group(1)) if vehicles_match else None,
    }


def format_float(value: Optional[float], digits: int = 3) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def make_row(index: int, code: str, current: int, our: Optional[int], cpu: Optional[float]) -> dict:
    if our is None:
        return {
            "Prob. #": index,
            "Prob. code": code,
            "Current result": current,
            "Our result": "ERROR",
            "Difference": "ERROR",
            "% Difference": "ERROR",
            "CPU time (s)": format_float(cpu, 2),
        }

    diff = our - current
    pct = 100.0 * diff / current if current else 0.0
    return {
        "Prob. #": index,
        "Prob. code": code,
        "Current result": current,
        "Our result": our,
        "Difference": diff,
        "% Difference": f"{pct:.3f}",
        "CPU time (s)": format_float(cpu, 2),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    headers = [
        "Prob. #",
        "Prob. code",
        "Current result",
        "Our result",
        "Difference",
        "% Difference",
        "CPU time (s)",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict]) -> None:
    headers = [
        "Prob. #",
        "Prob. code",
        "Current result",
        "Our result",
        "Difference",
        "% Difference",
        "CPU time (s)",
    ]
    with path.open("w", encoding="utf-8") as f:
        f.write("Table 1. Comparison between our solutions and current results\n\n")
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("| " + " | ".join(["---:"] + ["---"] + ["---:"] * 5) + " |\n")
        for row in rows:
            f.write("| " + " | ".join(str(row[h]) for h in headers) + " |\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run CVRP benchmark instances and generate comparison tables."
    )
    parser.add_argument("--root", default=".", help="Repository root directory.")
    parser.add_argument("--data-dir", default="A-VRP", help="Directory containing .vrp files.")
    parser.add_argument("--exe", default="vrp.exe", help="Solver executable path.")
    parser.add_argument("--source", default="chatgpt.cpp", help="C++ source file.")
    parser.add_argument("--compile", action="store_true", help="Compile solver before running.")
    parser.add_argument("--time", type=int, default=10, help="Time limit per instance in seconds.")
    parser.add_argument(
        "--profile",
        choices=["fixed", "paper"],
        default="fixed",
        help="fixed uses --time for every instance; paper uses the CPU-time budget from the sample table.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Override solver RNG seed.")
    parser.add_argument("--only", default=None, help="Regex filter for instance code.")
    parser.add_argument("--output-dir", default="benchmark_results", help="Where to write result tables.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    data_dir = (root / args.data_dir).resolve()
    exe = (root / args.exe).resolve()
    source = (root / args.source).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.compile:
        compile_solver(root, source, exe)

    if not exe.exists():
        print(f"Executable not found: {exe}", file=sys.stderr)
        return 1

    only_re = re.compile(args.only) if args.only else None
    rows: list[dict] = []

    for index, (code, current, paper_seconds) in enumerate(BENCHMARKS, start=1):
        if only_re and not only_re.search(code):
            continue

        instance = data_dir / f"{code}.vrp"
        if not instance.exists():
            print(f"[{index:02d}] {code}: missing file {instance}", flush=True)
            rows.append(make_row(index, code, current, None, None))
            continue

        seconds = paper_seconds if args.profile == "paper" else args.time
        print(f"[{index:02d}] {code}: running {seconds}s", flush=True)

        try:
            result = run_instance(exe, instance, seconds, args.seed)
            if result["returncode"] != 0:
                print(result["stderr"], file=sys.stderr)
            row = make_row(index, code, current, result["our_result"], result["cpu_time"])
        except subprocess.TimeoutExpired:
            print(f"[{index:02d}] {code}: timeout", flush=True)
            row = make_row(index, code, current, None, float(seconds))

        rows.append(row)
        print(
            f"     current={row['Current result']} our={row['Our result']} "
            f"diff={row['Difference']} cpu={row['CPU time (s)']}",
            flush=True,
        )

    csv_path = output_dir / "results.csv"
    md_path = output_dir / "results.md"
    write_csv(csv_path, rows)
    write_markdown(md_path, rows)

    print(f"\nWrote {csv_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
