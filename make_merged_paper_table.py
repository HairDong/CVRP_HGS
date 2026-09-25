"""Merge paper references, Vidal HGS results, and Proposed v2 results."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from make_comparison_table import read_successful_runs


def fmt_number(value: float) -> str:
    return str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value:.3f}"


def load_references(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 30:
        raise ValueError(f"Expected 30 reference rows, found {len(rows)}")
    return rows


def merge(reference_path: Path, proposed_path: Path, vidal_path: Path, seed: int) -> list[dict]:
    references = load_references(reference_path)
    proposed = read_successful_runs(proposed_path)
    vidal = read_successful_runs(vidal_path)
    rows: list[dict] = []
    for ref in references:
        instance = ref["instance"]
        budget = float(ref["time_limit_s"])
        key = (instance, str(seed), f"{budget:.9g}")
        if key not in proposed:
            raise ValueError(f"Missing Proposed v2 result for {key}")
        if key not in vidal:
            raise ValueError(f"Missing Vidal HGS result for {key}")

        p_row = proposed[key]
        h_row = vidal[key]
        p_cost = float(p_row["cost"])
        h_cost = float(h_row["cost"])
        kir = float(ref["kir_2017"])
        diff_kir = p_cost - kir
        diff_hgs = p_cost - h_cost
        rows.append({
            "problem_no": ref["problem_no"],
            "instance": instance,
            "kir_2017": fmt_number(kir),
            "vidal_hgs": fmt_number(h_cost),
            "proposed_v2": fmt_number(p_cost),
            "diff_v2_kir": fmt_number(diff_kir),
            "diff_v2_kir_pct": f"{diff_kir / kir * 100.0:.3f}",
            "diff_v2_hgs": fmt_number(diff_hgs),
            "diff_v2_hgs_pct": f"{diff_hgs / h_cost * 100.0:.3f}",
            "time_limit_s": f"{budget:.2f}",
            "seed": str(seed),
            "vidal_elapsed_s": f"{float(h_row['elapsed_s']):.3f}",
            "proposed_elapsed_s": f"{float(p_row['elapsed_s']):.3f}",
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_latex(path: Path, rows: list[dict], caption: str) -> None:
    headers = [
        r"Prob. \#", "Prob. code", "Kır 2017", "Vidal HGS", "Proposed v2",
        r"$\Delta_{Kir}$", r"$\%\Delta_{Kir}$", r"$\Delta_{HGS}$",
        r"$\%\Delta_{HGS}$", "$T$(s)",
    ]
    lines = [
        r"\begin{table*}[htbp]", r"\centering", rf"\caption{{{caption}}}",
        r"\resizebox{\textwidth}{!}{%", r"\begin{tabular}{rrrrrrrrrr}",
        r"\hline", " & ".join(headers) + r" \\", r"\hline",
    ]
    for row in rows:
        values = [
            row["problem_no"], row["instance"], row["kir_2017"], row["vidal_hgs"],
            row["proposed_v2"], row["diff_v2_kir"],
            row["diff_v2_kir_pct"], row["diff_v2_hgs"], row["diff_v2_hgs_pct"],
            row["time_limit_s"],
        ]
        lines.append(" & ".join(values) + r" \\")
    lines.extend([
        r"\hline", r"\end{tabular}%", r"}", r"\end{table*}",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_png(path: Path, rows: list[dict], title: str) -> None:
    import matplotlib.pyplot as plt

    headers = [
        "Prob. #", "Prob. code", "Kır et al. 2017", "Vidal HGS",
        "Proposed v2", "Δ v2-Kır", "% Δ v2-Kır",
        "Δ v2-HGS", "% Δ v2-HGS", "T(s)",
    ]
    keys = [
        "problem_no", "instance", "kir_2017", "vidal_hgs", "proposed_v2",
        "diff_v2_kir", "diff_v2_kir_pct", "diff_v2_hgs",
        "diff_v2_hgs_pct", "time_limit_s",
    ]
    cells = [[row[key] for key in keys] for row in rows]
    plt.rcParams.update({"font.family": "serif", "font.size": 8})
    fig, axis = plt.subplots(figsize=(15.5, 9.3))
    axis.axis("off")
    axis.set_title(title, fontsize=13, fontweight="bold", pad=12)
    widths = [0.06, 0.13, 0.11, 0.10, 0.11, 0.09, 0.10, 0.09, 0.10, 0.08]
    table = axis.table(
        cellText=cells, colLabels=headers, cellLoc="center", colLoc="center",
        loc="upper center", colWidths=widths,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.7)
    table.scale(1.0, 1.24)
    for (row_index, col_index), cell in table.get_celld().items():
        cell.set_facecolor("white")
        cell.set_edgecolor("black")
        if row_index == 0:
            cell.set_text_props(fontweight="bold")
            cell.visible_edges = "BT"
            cell.set_linewidth(0.8)
            if col_index == len(headers) - 1:
                cell.get_text().set_color("red")
        else:
            cell.visible_edges = ""

    # Bold the best solver result among Kır 2017, Vidal HGS, and Proposed v2.
    for index, row in enumerate(rows, start=1):
        results = [float(row["kir_2017"]), float(row["vidal_hgs"]),
                   float(row["proposed_v2"])]
        best = min(results)
        for result, column in zip(results, (2, 3, 4)):
            if result == best:
                table[index, column].get_text().set_fontweight("bold")
    for col_index in range(len(headers)):
        table[len(rows), col_index].visible_edges = "B"
        table[len(rows), col_index].set_linewidth(0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--proposed-runs", type=Path, required=True)
    parser.add_argument("--vidal-runs", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--title", default="Merged comparison under the paper time limits")
    args = parser.parse_args()
    rows = merge(
        args.references.resolve(), args.proposed_runs.resolve(),
        args.vidal_runs.resolve(), args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "merged_comparison.csv", rows)
    write_png(args.output_dir / "merged_comparison.png", rows, args.title)
    write_latex(args.output_dir / "merged_comparison.tex", rows, args.title)

    wins_hgs = sum(float(row["diff_v2_hgs"]) < 0 for row in rows)
    ties_hgs = sum(float(row["diff_v2_hgs"]) == 0 for row in rows)
    wins_kir = sum(float(row["diff_v2_kir"]) < 0 for row in rows)
    ties_kir = sum(float(row["diff_v2_kir"]) == 0 for row in rows)
    print(f"Rows: {len(rows)}")
    print(f"v2 vs HGS wins/ties/losses: {wins_hgs}/{ties_hgs}/{len(rows)-wins_hgs-ties_hgs}")
    print(f"v2 vs Kir wins/ties/losses: {wins_kir}/{ties_kir}/{len(rows)-wins_kir-ties_kir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
