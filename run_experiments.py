"""Reproducible multi-seed experiments for CVRP_TS_ALNS_v2.

The default configuration runs the proposed Python solver independently from
Vidal's executable: HGS warm-start is disabled unless explicitly requested.
Each run is validated against capacity, fleet size K, and exact customer
coverage before it is written to CSV.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

from CVRP_TS_ALNS_v2 import (
    HybridMemeticCVRP,
    build_dist,
    parse_vrp_file,
    validate_solution,
)


RUN_FIELDS = [
    "algorithm",
    "instance",
    "source_file",
    "seed",
    "time_limit_s",
    "elapsed_s",
    "cost",
    "bks",
    "gap_bks_pct",
    "route_count",
    "vehicle_limit_k",
    "capacity",
    "feasible",
    "excess_load",
    "excess_vehicles",
    "missing_customers",
    "duplicate_count",
    "invalid_customers",
    "adaptive_penalty",
    "adaptive_removal",
    "adaptive_operator_weights",
    "search_mode",
    "hgs_warmstart",
    "iterations",
    "final_penalty",
    "status",
    "error",
    "git_commit",
    "git_dirty",
    "solver_sha256",
    "python_version",
    "platform",
]

SUMMARY_FIELDS = [
    "algorithm",
    "instance",
    "runs_requested",
    "runs_successful",
    "bks",
    "best",
    "mean",
    "std",
    "gap_bks_pct",
    "sr_at_bks_pct",
    "mean_time_s",
    "vehicle_limit_k",
    "adaptive_penalty",
    "adaptive_removal",
    "adaptive_operator_weights",
    "search_mode",
    "hgs_warmstart",
]


def parse_seeds(spec: str) -> list[int]:
    """Parse seed specifications such as ``1-10`` or ``1,3,7``."""
    seeds: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            start, stop = int(left), int(right)
            if stop < start:
                raise ValueError(f"Invalid descending seed range: {part}")
            seeds.extend(range(start, stop + 1))
        else:
            seeds.append(int(part))
    unique = list(dict.fromkeys(seeds))
    if not unique:
        raise ValueError("At least one seed is required")
    return unique


def default_time_limit(n_customers: int) -> float:
    """Piecewise time budget used by the v2 solver."""
    if n_customers <= 50:
        return max(20.0, n_customers * 0.8)
    if n_customers <= 100:
        return max(40.0, n_customers * 1.0)
    if n_customers <= 200:
        return max(120.0, min(360.0, n_customers * 2.0))
    return max(360.0, min(600.0, n_customers * 2.5))


def auto_parameters(n_customers: int, dist, demands) -> dict:
    if n_customers <= 50:
        nb_granular = max(15, n_customers // 4)
    elif n_customers <= 100:
        nb_granular = max(20, min(30, n_customers // 3))
    else:
        nb_granular = min(50, max(35, n_customers // 4))
    return {
        "nb_granular": nb_granular,
        "k_destroy": max(4, min(n_customers // 5, 30)),
        "tabu_tenure": max(5, n_customers // 5),
        "ml_tenure": max(3, n_customers // 10),
        "pop_mu": max(5, min(25, n_customers // 4)),
        "init_penalty": max(
            1.0, max(dist[0]) / max(max(demands), 1)),
    }


def git_metadata(project_dir: Path) -> tuple[str, bool]:
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "-C", str(project_dir), "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    os.replace(temporary, path)


def load_existing_runs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def run_key(row: dict) -> tuple:
    return (
        row.get("algorithm"),
        row.get("instance"),
        str(row.get("seed")),
        str(row.get("time_limit_s")),
        str(row.get("adaptive_penalty")),
        str(row.get("adaptive_removal")),
        str(row.get("adaptive_operator_weights")),
        str(row.get("search_mode")),
        str(row.get("hgs_warmstart")),
    )


def run_one(
    vrp_path: Path,
    seed: int,
    time_limit: float | None,
    adaptive_penalty: bool,
    adaptive_removal: bool,
    adaptive_operator_weights: bool,
    search_mode: str,
    hgs_warmstart: bool,
    verbose: bool,
    commit: str,
    dirty: bool,
    solver_sha256: str,
) -> dict:
    ds = parse_vrp_file(str(vrp_path), seed=seed)[0]
    coords = [ds["depot"]] + [c["coord"] for c in ds["customers"]]
    demands = [0] + [c["demand"] for c in ds["customers"]]
    dist = build_dist(coords, integer_round=True)
    n_customers = len(demands) - 1
    budget = float(time_limit) if time_limit is not None else default_time_limit(
        n_customers)
    params = auto_parameters(n_customers, dist, demands)
    algorithm = "Proposed-Python-v2"

    base = {
        "algorithm": algorithm,
        "instance": ds["label"],
        "source_file": str(vrp_path.resolve()),
        "seed": seed,
        "time_limit_s": f"{budget:.6g}",
        "bks": "" if ds.get("bks") is None else f"{ds['bks']:.10g}",
        "vehicle_limit_k": ds["num_vehicles"],
        "capacity": ds["vehicle_capacity"],
        "adaptive_penalty": adaptive_penalty,
        "adaptive_removal": adaptive_removal,
        "adaptive_operator_weights": adaptive_operator_weights,
        "search_mode": search_mode,
        "hgs_warmstart": hgs_warmstart,
        "git_commit": commit,
        "git_dirty": dirty,
        "solver_sha256": solver_sha256,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }

    try:
        solver = HybridMemeticCVRP(
            dist,
            demands,
            ds["vehicle_capacity"],
            ds["num_vehicles"],
            pop_mu=params["pop_mu"],
            nb_elite=2,
            nb_close=3,
            init_penalty=params["init_penalty"],
            target_feas=0.20,
            tabu_tenure=params["tabu_tenure"],
            ml_tenure=params["ml_tenure"],
            k_destroy=params["k_destroy"],
            nb_granular=params["nb_granular"],
            vrp_filepath=str(vrp_path),
            use_hgs_warmstart=hgs_warmstart,
            adaptive_penalty=adaptive_penalty,
            adaptive_removal=adaptive_removal,
            adaptive_operator_weights=adaptive_operator_weights,
            search_mode=search_mode,
        )
        started = time.perf_counter()
        cost, routes = solver.solve(
            time_limit=budget, seed=seed, verbose=verbose)
        elapsed = time.perf_counter() - started
        validation = validate_solution(
            routes, demands, ds["vehicle_capacity"], ds["num_vehicles"])
        if not validation["feasible"]:
            raise RuntimeError(f"Post-run validation failed: {validation}")
        bks = ds.get("bks")
        gap = "" if bks is None else (cost - bks) / bks * 100.0
        return {
            **base,
            "elapsed_s": f"{elapsed:.6f}",
            "cost": f"{cost:.10g}",
            "gap_bks_pct": "" if gap == "" else f"{gap:.8f}",
            "route_count": validation["route_count"],
            "feasible": True,
            "excess_load": validation["excess_load"],
            "excess_vehicles": validation["excess_vehicles"],
            "missing_customers": "",
            "duplicate_count": validation["duplicate_count"],
            "invalid_customers": "",
            "iterations": solver.total_iter,
            "final_penalty": f"{solver.penalty.penalty:.10g}",
            "status": "ok",
            "error": "",
        }
    except Exception as exc:  # keep the experiment batch auditable
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


def build_summary(rows: list[dict], seeds: list[int]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (
            row.get("algorithm"),
            row.get("instance"),
            str(row.get("adaptive_penalty")),
            str(row.get("adaptive_removal")),
            str(row.get("adaptive_operator_weights")),
            str(row.get("search_mode")),
            str(row.get("hgs_warmstart")),
        )
        grouped.setdefault(key, []).append(row)

    summary = []
    for key, group in sorted(grouped.items()):
        good = [r for r in group if r.get("status") == "ok" and
                str(r.get("feasible")).lower() == "true"]
        costs = [float(r["cost"]) for r in good]
        times = [float(r["elapsed_s"]) for r in good]
        bks_values = [float(r["bks"]) for r in good if r.get("bks")]
        bks = bks_values[0] if bks_values else None
        mean = statistics.mean(costs) if costs else math.nan
        std = statistics.stdev(costs) if len(costs) >= 2 else 0.0 if costs else math.nan
        sr = (
            100.0 * sum(abs(value - bks) <= 1e-6 for value in costs) / len(costs)
            if costs and bks is not None else math.nan
        )
        gap = ((mean - bks) / bks * 100.0
               if costs and bks not in (None, 0) else math.nan)
        summary.append({
            "algorithm": key[0],
            "instance": key[1],
            "runs_requested": len(seeds),
            "runs_successful": len(good),
            "bks": "" if bks is None else f"{bks:.10g}",
            "best": "" if not costs else f"{min(costs):.10g}",
            "mean": "" if not costs else f"{mean:.10g}",
            "std": "" if not costs else f"{std:.10g}",
            "gap_bks_pct": "" if math.isnan(gap) else f"{gap:.8f}",
            "sr_at_bks_pct": "" if math.isnan(sr) else f"{sr:.4f}",
            "mean_time_s": "" if not times else f"{statistics.mean(times):.6f}",
            "vehicle_limit_k": group[0].get("vehicle_limit_k", ""),
            "adaptive_penalty": key[2],
            "adaptive_removal": key[3],
            "adaptive_operator_weights": key[4],
            "search_mode": key[5],
            "hgs_warmstart": key[6],
        })
    return summary


def resolve_instances(dataset_dir: Path, patterns: list[str]) -> list[Path]:
    if not patterns:
        paths = sorted(dataset_dir.glob("*.vrp"))
    else:
        found = []
        for pattern in patterns:
            candidate = Path(pattern)
            if candidate.is_file():
                found.append(candidate)
            else:
                found.extend(dataset_dir.glob(pattern))
        paths = sorted({path.resolve() for path in found})
    if not paths:
        raise FileNotFoundError("No .vrp instances matched the requested input")
    return paths


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Run reproducible multi-seed experiments for Python v2.")
    parser.add_argument(
        "instances", nargs="*",
        help="Instance paths or glob patterns relative to --dataset-dir.")
    parser.add_argument(
        "--dataset-dir", type=Path,
        default=project_dir / "Dataset-VRP")
    parser.add_argument("--seeds", default="1-10")
    parser.add_argument(
        "--time-limit", type=float, default=None,
        help="Seconds per run; omit to use the documented piecewise T(n).")
    parser.add_argument(
        "--output-dir", type=Path,
        default=project_dir / "benchmark_results" / "proposed")
    parser.add_argument(
        "--fixed-penalty", action="store_true",
        help="Disable dynamic lambda updates (ablation configuration).")
    parser.add_argument(
        "--fixed-removal", action="store_true",
        help="Use k_destroy on every destroy/repair call.")
    parser.add_argument(
        "--fixed-operator-weights", action="store_true",
        help="Keep ALNS roulette weights at their initial values.")
    parser.add_argument(
        "--search-mode",
        choices=("full", "alns_only", "recombination_only"),
        default="full")
    parser.add_argument(
        "--allow-hgs-warmstart", action="store_true",
        help="Use external HGS only for a non-independent diagnostic run.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    seeds = parse_seeds(args.seeds)
    paths = resolve_instances(args.dataset_dir.resolve(), args.instances)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs_path = args.output_dir / "runs.csv"
    summary_path = args.output_dir / "summary.csv"
    rows = load_existing_runs(runs_path) if args.resume else []
    completed = {run_key(row) for row in rows if row.get("status") == "ok"}
    commit, dirty = git_metadata(project_dir)
    solver_sha256 = sha256_file(project_dir / "CVRP_TS_ALNS_v2.py")

    print(
        f"Running {len(paths)} instance(s) x {len(seeds)} seed(s); "
        f"adaptive_penalty={not args.fixed_penalty}; "
        f"adaptive_removal={not args.fixed_removal}; "
        f"adaptive_operator_weights={not args.fixed_operator_weights}; "
        f"search_mode={args.search_mode}; "
        f"hgs_warmstart={args.allow_hgs_warmstart}")
    for vrp_path in paths:
        ds = parse_vrp_file(str(vrp_path))[0]
        n_customers = len(ds["customers"])
        budget = args.time_limit or default_time_limit(n_customers)
        for seed in seeds:
            proposed_key = (
                "Proposed-Python-v2",
                ds["label"],
                str(seed),
                f"{float(budget):.6g}",
                str(not args.fixed_penalty),
                str(not args.fixed_removal),
                str(not args.fixed_operator_weights),
                args.search_mode,
                str(args.allow_hgs_warmstart),
            )
            if proposed_key in completed:
                print(f"SKIP {ds['label']} seed={seed} (already complete)")
                continue
            print(
                f"RUN  {ds['label']} seed={seed} K={ds['num_vehicles']} "
                f"T={budget:.2f}s")
            row = run_one(
                vrp_path,
                seed,
                args.time_limit,
                not args.fixed_penalty,
                not args.fixed_removal,
                not args.fixed_operator_weights,
                args.search_mode,
                args.allow_hgs_warmstart,
                args.verbose,
                commit,
                dirty,
                solver_sha256,
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
