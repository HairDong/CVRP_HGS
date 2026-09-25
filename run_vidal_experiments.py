"""Run the official Vidal HGS-CVRP executable under matched conditions."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from CVRP_TS_ALNS_v2 import build_dist, parse_vrp_file, total_cost, validate_solution
from run_experiments import (
    RUN_FIELDS,
    SUMMARY_FIELDS,
    atomic_write_csv,
    build_summary,
    default_time_limit,
    git_metadata,
    load_existing_runs,
    parse_seeds,
    resolve_instances,
    run_key,
    sha256_file,
)


def parse_hgs_solution(path: Path) -> tuple[list[list[int]], float]:
    routes: list[list[int]] = []
    reported_cost = None
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line.startswith("Route #"):
                _, customers = line.split(":", 1)
                routes.append([int(value) for value in customers.split()])
            elif line.startswith("Cost "):
                reported_cost = float(line.split(None, 1)[1])
    if reported_cost is None:
        raise ValueError(f"HGS solution has no Cost line: {path}")
    return routes, reported_cost


def run_one(
    hgs_exe: Path,
    hgs_dir: Path,
    vrp_path: Path,
    solution_dir: Path,
    log_dir: Path,
    seed: int,
    time_limit: float | None,
    commit: str,
    dirty: bool,
    executable_sha256: str,
) -> dict:
    ds = parse_vrp_file(str(vrp_path), seed=seed)[0]
    n_customers = len(ds["customers"])
    budget = float(time_limit) if time_limit is not None else default_time_limit(
        n_customers)
    solution_path = solution_dir / f"{ds['label']}__seed-{seed}.sol"
    log_path = log_dir / f"{ds['label']}__seed-{seed}.log"
    algorithm = "Vidal-HGS-CVRP"
    base = {
        "algorithm": algorithm,
        "instance": ds["label"],
        "source_file": str(vrp_path.resolve()),
        "seed": seed,
        "time_limit_s": f"{budget:.6g}",
        "bks": "" if ds.get("bks") is None else f"{ds['bks']:.10g}",
        "vehicle_limit_k": ds["num_vehicles"],
        "capacity": ds["vehicle_capacity"],
        "adaptive_penalty": "HGS-default",
        "adaptive_removal": "HGS-default",
        "adaptive_operator_weights": "HGS-default",
        "search_mode": "HGS",
        "hgs_warmstart": False,
        "git_commit": commit,
        "git_dirty": dirty,
        "solver_sha256": executable_sha256,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
    }

    command = [
        str(hgs_exe),
        str(vrp_path.resolve()),
        str(solution_path.resolve()),
        "-t", str(budget),
        "-seed", str(seed),
        "-veh", str(ds["num_vehicles"]),
        "-round", "1",
        "-log", "0",
    ]
    try:
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=hgs_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        elapsed = time.perf_counter() - started
        log_path.write_text(
            "COMMAND\n" + subprocess.list2cmdline(command) +
            "\n\nSTDOUT\n" + completed.stdout +
            "\n\nSTDERR\n" + completed.stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"HGS exited with code {completed.returncode}; see {log_path}")
        routes, reported_cost = parse_hgs_solution(solution_path)
        coords = [ds["depot"]] + [c["coord"] for c in ds["customers"]]
        demands = [0] + [c["demand"] for c in ds["customers"]]
        dist = build_dist(coords, integer_round=True)
        recomputed_cost = total_cost(routes, dist)
        if abs(recomputed_cost - reported_cost) > 1e-6:
            raise ValueError(
                f"Cost mismatch: HGS={reported_cost}, recomputed={recomputed_cost}")
        validation = validate_solution(
            routes, demands, ds["vehicle_capacity"], ds["num_vehicles"])
        if not validation["feasible"]:
            raise RuntimeError(f"Post-run validation failed: {validation}")
        bks = ds.get("bks")
        gap = "" if bks is None else (reported_cost - bks) / bks * 100.0
        return {
            **base,
            "elapsed_s": f"{elapsed:.6f}",
            "cost": f"{reported_cost:.10g}",
            "gap_bks_pct": "" if gap == "" else f"{gap:.8f}",
            "route_count": validation["route_count"],
            "feasible": True,
            "excess_load": validation["excess_load"],
            "excess_vehicles": validation["excess_vehicles"],
            "missing_customers": "",
            "duplicate_count": validation["duplicate_count"],
            "invalid_customers": "",
            "iterations": "",
            "final_penalty": "",
            "status": "ok",
            "error": "",
        }
    except Exception as exc:
        return {
            **base,
            "elapsed_s": "",
            "cost": "",
            "gap_bks_pct": "",
            "route_count": "",
            "feasible": False,
            "excess_load": "",
            "excess_vehicles": "",
            "missing_customers": "",
            "duplicate_count": "",
            "invalid_customers": "",
            "iterations": "",
            "final_penalty": "",
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Benchmark official Vidal HGS-CVRP with matched K and T(n).")
    parser.add_argument("instances", nargs="*")
    parser.add_argument(
        "--dataset-dir", type=Path,
        default=project_dir / "Dataset-VRP")
    parser.add_argument("--hgs-exe", type=Path, required=True)
    parser.add_argument("--seeds", default="1-10")
    parser.add_argument("--time-limit", type=float, default=None)
    parser.add_argument(
        "--output-dir", type=Path,
        default=project_dir / "benchmark_results" / "vidal_hgs")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    hgs_exe = args.hgs_exe.resolve()
    if not hgs_exe.is_file():
        parser.error(f"HGS executable not found: {hgs_exe}")
    hgs_dir = hgs_exe.parent
    seeds = parse_seeds(args.seeds)
    paths = resolve_instances(args.dataset_dir.resolve(), args.instances)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    solution_dir = args.output_dir / "solutions"
    log_dir = args.output_dir / "logs"
    solution_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    runs_path = args.output_dir / "runs.csv"
    summary_path = args.output_dir / "summary.csv"
    rows = load_existing_runs(runs_path) if args.resume else []
    completed = {run_key(row) for row in rows if row.get("status") == "ok"}
    commit, dirty = git_metadata(hgs_dir)
    executable_sha256 = sha256_file(hgs_exe)

    print(f"Running Vidal HGS: {len(paths)} instance(s) x {len(seeds)} seed(s)")
    for vrp_path in paths:
        ds = parse_vrp_file(str(vrp_path))[0]
        n_customers = len(ds["customers"])
        budget = args.time_limit or default_time_limit(n_customers)
        for seed in seeds:
            proposed_key = (
                "Vidal-HGS-CVRP",
                ds["label"],
                str(seed),
                f"{float(budget):.6g}",
                "HGS-default",
                "HGS-default",
                "HGS-default",
                "HGS",
                "False",
            )
            if proposed_key in completed:
                print(f"SKIP {ds['label']} seed={seed} (already complete)")
                continue
            print(
                f"RUN  {ds['label']} seed={seed} K={ds['num_vehicles']} "
                f"T={budget:.2f}s")
            row = run_one(
                hgs_exe,
                hgs_dir,
                vrp_path,
                solution_dir,
                log_dir,
                seed,
                args.time_limit,
                commit,
                dirty,
                executable_sha256,
            )
            rows.append(row)
            atomic_write_csv(runs_path, RUN_FIELDS, rows)
            atomic_write_csv(
                summary_path, SUMMARY_FIELDS, build_summary(rows, seeds))
            if row["status"] == "ok":
                print(
                    f" OK  cost={row['cost']} routes={row['route_count']} "
                    f"gap={row['gap_bks_pct']}% elapsed={row['elapsed_s']}s")
            else:
                print(f"ERR  {row['error']}", file=sys.stderr)

    failures = sum(row.get("status") != "ok" for row in rows)
    print(f"Runs: {runs_path}")
    print(f"Summary: {summary_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
