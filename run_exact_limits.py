"""Run one solver with the exact per-instance limits from the paper tables."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from CVRP_TS_ALNS_v2 import parse_vrp_file
from run_experiments import (
    RUN_FIELDS,
    SUMMARY_FIELDS,
    atomic_write_csv,
    build_summary,
    git_metadata,
    load_existing_runs,
    run_key,
    run_one as run_proposed,
    sha256_file,
)
from run_vidal_experiments import run_one as run_vidal


def load_schedule(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 30:
        raise ValueError(f"Expected 30 scheduled instances, found {len(rows)}")
    return rows


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algorithm", choices=("proposed", "vidal"), required=True)
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument(
        "--schedule", type=Path,
        default=project_dir / "paper_reference_values.csv")
    parser.add_argument("--hgs-exe", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    schedule = load_schedule(args.schedule.resolve())
    dataset_by_label: dict[str, Path] = {}
    for candidate in (project_dir / "Dataset-VRP").glob("*.vrp"):
        label = parse_vrp_file(str(candidate))[0]["label"]
        if label in dataset_by_label:
            raise ValueError(f"Duplicate dataset label: {label}")
        dataset_by_label[label] = candidate
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.algorithm == "vidal":
        (args.output_dir / "solutions").mkdir(parents=True, exist_ok=True)
        (args.output_dir / "logs").mkdir(parents=True, exist_ok=True)
    runs_path = args.output_dir / "runs.csv"
    summary_path = args.output_dir / "summary.csv"
    rows = load_existing_runs(runs_path) if args.resume else []
    completed = {run_key(row) for row in rows if row.get("status") == "ok"}

    solver_path = project_dir / "CVRP_TS_ALNS_v2.py"
    if args.algorithm == "proposed":
        commit, dirty = git_metadata(project_dir)
        solver_hash = sha256_file(solver_path)
        algorithm_name = "Proposed-Python-v2"
    else:
        if args.hgs_exe is None:
            parser.error("--hgs-exe is required for --algorithm vidal")
        args.hgs_exe = args.hgs_exe.resolve()
        if not args.hgs_exe.is_file():
            parser.error(f"HGS executable not found: {args.hgs_exe}")
        commit, dirty = git_metadata(args.hgs_exe.parent)
        solver_hash = sha256_file(args.hgs_exe)
        algorithm_name = "Vidal-HGS-CVRP"

    print(
        f"Running {algorithm_name}: {len(schedule)} instances, seed={args.seed}, "
        "exact paper time limits",
        flush=True,
    )
    for scheduled in schedule:
        instance = scheduled["instance"]
        budget = float(scheduled["time_limit_s"])
        vrp_path = dataset_by_label.get(instance)
        if vrp_path is None:
            raise FileNotFoundError(
                f"No VRP file declares instance label {instance!r}")

        if args.algorithm == "proposed":
            key = (
                algorithm_name, instance, str(args.seed), f"{budget:.6g}",
                "True", "True", "True", "full", "False",
            )
        else:
            key = (
                algorithm_name, instance, str(args.seed), f"{budget:.6g}",
                "HGS-default", "HGS-default", "HGS-default", "HGS", "False",
            )
        if key in completed:
            print(f"SKIP {instance} (already complete)", flush=True)
            continue

        print(f"RUN  {instance} seed={args.seed} T={budget:.0f}s", flush=True)
        if args.algorithm == "proposed":
            row = run_proposed(
                vrp_path=vrp_path,
                seed=args.seed,
                time_limit=budget,
                adaptive_penalty=True,
                adaptive_removal=True,
                adaptive_operator_weights=True,
                search_mode="full",
                hgs_warmstart=False,
                verbose=False,
                commit=commit,
                dirty=dirty,
                solver_sha256=solver_hash,
            )
        else:
            row = run_vidal(
                hgs_exe=args.hgs_exe,
                hgs_dir=args.hgs_exe.parent,
                vrp_path=vrp_path,
                solution_dir=args.output_dir / "solutions",
                log_dir=args.output_dir / "logs",
                seed=args.seed,
                time_limit=budget,
                commit=commit,
                dirty=dirty,
                executable_sha256=solver_hash,
            )

        rows.append(row)
        atomic_write_csv(runs_path, RUN_FIELDS, rows)
        atomic_write_csv(summary_path, SUMMARY_FIELDS, build_summary(rows, [args.seed]))
        if row["status"] == "ok":
            print(
                f" OK  {instance}: cost={row['cost']} "
                f"elapsed={row['elapsed_s']}s",
                flush=True,
            )
        else:
            print(f"ERR  {instance}: {row['error']}", flush=True)

    failures = sum(row.get("status") != "ok" for row in rows)
    print(f"Runs: {runs_path}", flush=True)
    print(f"Summary: {summary_path}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
