"""Summarize matched multi-seed CVRP experiments without using BKS values.

Expected input is one or more ``runs.csv`` files produced by
``run_experiments.py`` and ``run_vidal_experiments.py``.  For each instance,
the script validates that both algorithms contain the same expected seeds and
time limit, then reports Best, Average, sample Std, Median, Worst, and the seed
or seeds attaining Best.

Because CVRP is a minimization problem, negative v2-minus-HGS differences mean
that Proposed v2 is better; positive differences mean that Vidal HGS is better.
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import statistics
from pathlib import Path


OUTPUT_FIELDS = [
    "problem_no",
    "instance",
    "kir_2017",
    "time_limit_s",
    "vidal_runs",
    "vidal_best",
    "vidal_average",
    "vidal_std",
    "vidal_median",
    "vidal_worst",
    "vidal_best_seeds",
    "v2_runs",
    "v2_best",
    "v2_average",
    "v2_std",
    "v2_median",
    "v2_worst",
    "v2_best_seeds",
    "diff_best_v2_hgs",
    "diff_best_v2_hgs_pct",
    "diff_average_v2_hgs",
    "diff_average_v2_hgs_pct",
]


def parse_seed_spec(spec: str) -> list[int]:
    seeds: list[int] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            start, stop = int(left), int(right)
            if stop < start:
                raise ValueError(f"Descending seed range is invalid: {token}")
            seeds.extend(range(start, stop + 1))
        else:
            seeds.append(int(token))
    seeds = list(dict.fromkeys(seeds))
    if not seeds:
        raise ValueError("At least one expected seed is required")
    return seeds


def expand_input_paths(specs: list[str]) -> list[Path]:
    """Expand files, directories, and quoted glob patterns deterministically."""
    resolved: list[Path] = []
    for spec in specs:
        candidate = Path(spec)
        if candidate.is_dir():
            run_file = candidate / "runs.csv"
            if not run_file.is_file():
                raise FileNotFoundError(f"Directory has no runs.csv: {candidate}")
            resolved.append(run_file.resolve())
            continue
        if candidate.is_file():
            resolved.append(candidate.resolve())
            continue
        matches = [Path(value).resolve() for value in glob.glob(spec, recursive=True)]
        matches = [value for value in matches if value.is_file()]
        if not matches:
            raise FileNotFoundError(f"No input files matched: {spec}")
        resolved.extend(sorted(matches, key=lambda value: str(value).lower()))

    unique = list(dict.fromkeys(resolved))
    if not unique:
        raise ValueError("No runs.csv input files were supplied")
    return unique


def read_reference_rows(path: Path) -> list[dict]:
    """Read instance order, Kir 2017 result, and time limit; ignore BKS."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {"problem_no", "instance", "kir_2017", "time_limit_s"}
    missing = required - set(rows[0] if rows else {})
    if missing:
        raise ValueError(f"Reference CSV is missing columns: {sorted(missing)}")
    if not rows:
        raise ValueError("Reference CSV contains no instances")
    return rows


def read_run_group(paths: list[Path], group_name: str) -> dict[str, dict[int, dict]]:
    """Read and validate successful feasible rows, rejecting duplicate seeds."""
    by_instance: dict[str, dict[int, dict]] = {}
    required = {
        "instance", "seed", "time_limit_s", "cost", "status", "feasible",
    }
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{path} is missing columns: {sorted(missing)}")
            for line_number, row in enumerate(reader, start=2):
                if row["status"].strip().lower() != "ok":
                    raise ValueError(
                        f"{group_name}: unsuccessful run in {path}:{line_number}: "
                        f"{row.get('error', '')}")
                if row["feasible"].strip().lower() != "true":
                    raise ValueError(
                        f"{group_name}: infeasible run in {path}:{line_number}")
                instance = row["instance"].strip()
                seed = int(row["seed"])
                budget = float(row["time_limit_s"])
                cost = float(row["cost"])
                if not instance or not math.isfinite(budget) or budget <= 0:
                    raise ValueError(f"Invalid instance/time in {path}:{line_number}")
                if not math.isfinite(cost):
                    raise ValueError(f"Invalid cost in {path}:{line_number}")
                normalized = {
                    "instance": instance,
                    "seed": seed,
                    "time_limit_s": budget,
                    "cost": cost,
                    "source": f"{path}:{line_number}",
                }
                existing = by_instance.setdefault(instance, {}).get(seed)
                if existing is not None:
                    same = (
                        math.isclose(existing["time_limit_s"], budget, abs_tol=1e-9)
                        and math.isclose(existing["cost"], cost, abs_tol=1e-9)
                    )
                    if not same:
                        raise ValueError(
                            f"{group_name}: conflicting duplicate for {instance}, "
                            f"seed {seed}: {existing['source']} and "
                            f"{path}:{line_number}")
                    continue
                by_instance[instance][seed] = normalized
    return by_instance


def describe(seed_rows: dict[int, dict]) -> dict:
    ordered = sorted(seed_rows.items())
    costs = [row["cost"] for _, row in ordered]
    best = min(costs)
    best_seeds = [str(seed) for seed, row in ordered
                  if math.isclose(row["cost"], best, abs_tol=1e-9)]
    return {
        "runs": len(costs),
        "best": best,
        "average": statistics.fmean(costs),
        # Sample standard deviation (n-1), appropriate for repeated runs.
        "std": statistics.stdev(costs) if len(costs) >= 2 else 0.0,
        "median": statistics.median(costs),
        "worst": max(costs),
        "best_seeds": "|".join(best_seeds),
    }


def number(value: float, decimals: int = 6) -> str:
    if math.isclose(value, round(value), abs_tol=1e-9):
        return str(int(round(value)))
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def validate_seed_set(
    group_name: str,
    instance: str,
    seed_rows: dict[int, dict],
    expected_seeds: set[int],
) -> None:
    actual = set(seed_rows)
    missing = sorted(expected_seeds - actual)
    extra = sorted(actual - expected_seeds)
    if missing or extra:
        raise ValueError(
            f"{group_name} {instance}: expected seeds "
            f"{sorted(expected_seeds)}, missing={missing}, extra={extra}")


def build_rows(
    references: list[dict],
    proposed: dict[str, dict[int, dict]],
    vidal: dict[str, dict[int, dict]],
    expected_seeds: list[int],
) -> list[dict]:
    output: list[dict] = []
    expected = set(expected_seeds)
    reference_instances = {row["instance"] for row in references}
    extras = (set(proposed) | set(vidal)) - reference_instances
    if extras:
        raise ValueError(f"Runs contain instances absent from references: {sorted(extras)}")

    for ref in references:
        instance = ref["instance"]
        if instance not in proposed or instance not in vidal:
            raise ValueError(f"Missing one or both algorithms for {instance}")
        p_seed_rows = proposed[instance]
        h_seed_rows = vidal[instance]
        validate_seed_set("Proposed v2", instance, p_seed_rows, expected)
        validate_seed_set("Vidal HGS", instance, h_seed_rows, expected)

        expected_budget = float(ref["time_limit_s"])
        for seed in expected_seeds:
            p_budget = p_seed_rows[seed]["time_limit_s"]
            h_budget = h_seed_rows[seed]["time_limit_s"]
            if not math.isclose(p_budget, h_budget, abs_tol=1e-9):
                raise ValueError(
                    f"{instance} seed {seed}: time limits differ "
                    f"(v2={p_budget}, HGS={h_budget})")
            if not math.isclose(p_budget, expected_budget, abs_tol=1e-9):
                raise ValueError(
                    f"{instance} seed {seed}: time limit {p_budget} does not "
                    f"match reference {expected_budget}")

        p_stats = describe(p_seed_rows)
        h_stats = describe(h_seed_rows)
        diff_best = p_stats["best"] - h_stats["best"]
        diff_average = p_stats["average"] - h_stats["average"]
        output.append({
            "problem_no": ref["problem_no"],
            "instance": instance,
            "kir_2017": number(float(ref["kir_2017"])),
            "time_limit_s": number(expected_budget, 2),
            "vidal_runs": h_stats["runs"],
            "vidal_best": number(h_stats["best"]),
            "vidal_average": number(h_stats["average"]),
            "vidal_std": number(h_stats["std"]),
            "vidal_median": number(h_stats["median"]),
            "vidal_worst": number(h_stats["worst"]),
            "vidal_best_seeds": h_stats["best_seeds"],
            "v2_runs": p_stats["runs"],
            "v2_best": number(p_stats["best"]),
            "v2_average": number(p_stats["average"]),
            "v2_std": number(p_stats["std"]),
            "v2_median": number(p_stats["median"]),
            "v2_worst": number(p_stats["worst"]),
            "v2_best_seeds": p_stats["best_seeds"],
            "diff_best_v2_hgs": number(diff_best),
            "diff_best_v2_hgs_pct": f"{diff_best / h_stats['best'] * 100.0:.3f}",
            "diff_average_v2_hgs": number(diff_average),
            "diff_average_v2_hgs_pct": (
                f"{diff_average / h_stats['average'] * 100.0:.3f}"),
        })
    return output


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def latex_escape(value: str) -> str:
    return value.replace("_", r"\_").replace("%", r"\%")


def write_latex(path: Path, rows: list[dict], caption: str) -> None:
    lines = [
        r"\begin{table*}[htbp]",
        r"\centering",
        rf"\caption{{{latex_escape(caption)}}}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{rrrrrrrrrr}",
        r"\hline",
        (r"Prob. \# & Prob. code & Kır 2017 & Vidal Best & "
         r"Vidal Avg $\pm$ Std & v2 Best & v2 Avg $\pm$ Std & "
         r"$\%\Delta_{Best}$ & $\%\Delta_{Avg}$ & $T$(s) \\"),
        r"\hline",
    ]
    for row in rows:
        values = [
            row["problem_no"],
            latex_escape(row["instance"]),
            row["kir_2017"],
            row["vidal_best"],
            f"{row['vidal_average']} $\\pm$ {row['vidal_std']}",
            row["v2_best"],
            f"{row['v2_average']} $\\pm$ {row['v2_std']}",
            row["diff_best_v2_hgs_pct"],
            row["diff_average_v2_hgs_pct"],
            row["time_limit_s"],
        ]
        lines.append(" & ".join(values) + r" \\")
    lines.extend([
        r"\hline",
        r"\end{tabular}%",
        r"}",
        r"\end{table*}",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_count(rows: list[dict], field: str) -> tuple[int, int, int]:
    values = [float(row[field]) for row in rows]
    wins = sum(value < -1e-9 for value in values)
    ties = sum(abs(value) <= 1e-9 for value in values)
    return wins, ties, len(values) - wins - ties


def write_overall_summary(path: Path, rows: list[dict], seeds: list[int]) -> None:
    best = compare_count(rows, "diff_best_v2_hgs")
    average = compare_count(rows, "diff_average_v2_hgs")
    avg_gap = statistics.fmean(
        float(row["diff_average_v2_hgs_pct"]) for row in rows)
    lines = [
        f"Expected seeds: {','.join(map(str, seeds))}",
        f"Instances: {len(rows)}",
        ("Proposed v2 vs Vidal HGS by Best (wins/ties/losses): "
         f"{best[0]}/{best[1]}/{best[2]}"),
        ("Proposed v2 vs Vidal HGS by Average (wins/ties/losses): "
         f"{average[0]}/{average[1]}/{average[2]}"),
        f"Mean per-instance percentage difference by Average: {avg_gap:.3f}%",
        "Difference convention: Proposed v2 minus Vidal HGS; lower is better.",
        "Std convention: sample standard deviation with denominator n-1.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--proposed-runs", nargs="+", required=True,
        help="v2 runs.csv files, directories, or quoted glob patterns")
    parser.add_argument(
        "--vidal-runs", nargs="+", required=True,
        help="Vidal runs.csv files, directories, or quoted glob patterns")
    parser.add_argument(
        "--references", type=Path,
        default=project_dir / "paper_reference_values.csv",
        help="CSV providing instance order, Kir 2017 value, and time limit")
    parser.add_argument(
        "--expected-seeds", default="1-10",
        help="Required seeds, for example 1-10 or 1,3,5")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--caption",
        default="Multi-seed comparison with Kir et al. (2017) and Vidal HGS-CVRP")
    args = parser.parse_args()

    seeds = parse_seed_spec(args.expected_seeds)
    references = read_reference_rows(args.references.resolve())
    proposed_paths = expand_input_paths(args.proposed_runs)
    vidal_paths = expand_input_paths(args.vidal_runs)
    proposed = read_run_group(proposed_paths, "Proposed v2")
    vidal = read_run_group(vidal_paths, "Vidal HGS")
    rows = build_rows(references, proposed, vidal, seeds)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "multiseed_comparison.csv"
    latex_path = args.output_dir / "multiseed_comparison.tex"
    summary_path = args.output_dir / "overall_summary.txt"
    write_csv(csv_path, rows)
    write_latex(latex_path, rows, args.caption)
    write_overall_summary(summary_path, rows, seeds)
    print(f"Validated {len(rows)} instances x {len(seeds)} seeds x 2 algorithms")
    print(f"CSV: {csv_path}")
    print(f"LaTeX: {latex_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
