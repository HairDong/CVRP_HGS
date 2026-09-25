"""Build a paper-style comparison table from matched CVRP run files.

The reported difference follows the convention used in the manuscript table:

    Difference = Proposed v2 - Vidal HGS

Therefore, a negative value means that Proposed v2 obtained a lower (better)
objective value.  Only successful, feasible runs with the same instance, seed,
and time limit are compared.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


CSV_FIELDS = [
    "problem_no",
    "instance",
    "vidal_hgs",
    "proposed_v2",
    "difference",
    "difference_pct",
    "time_limit_s",
    "seed",
    "vidal_elapsed_s",
    "proposed_elapsed_s",
]


def read_successful_runs(path: Path) -> dict[tuple[str, str, str], dict]:
    """Index successful feasible runs by instance, seed, and time limit."""
    indexed: dict[tuple[str, str, str], dict] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "ok" or row.get("feasible") != "True":
                continue
            key = (
                row["instance"],
                str(row["seed"]),
                f"{float(row['time_limit_s']):.9g}",
            )
            indexed[key] = row
    return indexed


def matched_rows(proposed_path: Path, vidal_path: Path) -> list[dict]:
    proposed = read_successful_runs(proposed_path)
    vidal = read_successful_runs(vidal_path)
    # Lexicographic order matches the ordering used by the manuscript table
    # (for example, A-n63-k10 appears before A-n63-k9).
    common = sorted(proposed.keys() & vidal.keys(), key=lambda key: key[0].lower())
    if not common:
        raise ValueError("No matched successful runs were found")

    rows: list[dict] = []
    for number, key in enumerate(common, start=1):
        p_row = proposed[key]
        h_row = vidal[key]
        p_cost = float(p_row["cost"])
        h_cost = float(h_row["cost"])
        difference = p_cost - h_cost
        percentage = difference / h_cost * 100.0
        rows.append({
            "problem_no": number,
            "instance": key[0],
            "vidal_hgs": format_number(h_cost),
            "proposed_v2": format_number(p_cost),
            "difference": format_number(difference),
            "difference_pct": f"{percentage:.3f}",
            "time_limit_s": f"{float(key[2]):.2f}",
            "seed": key[1],
            "vidal_elapsed_s": f"{float(h_row['elapsed_s']):.3f}",
            "proposed_elapsed_s": f"{float(p_row['elapsed_s']):.3f}",
        })
    return rows


def format_number(value: float) -> str:
    return str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value:.3f}"


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_latex(path: Path, rows: list[dict], caption: str) -> None:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        rf"\caption{{{caption}}}",
        r"\begin{tabular}{rrrrrrr}",
        r"\hline",
        r"Prob. \# & Prob. code & Vidal HGS & Proposed v2 & Difference & \% Difference & $T$(s) \\",
        r"\hline",
    ]
    for row in rows:
        instance = row["instance"].replace("_", r"\_")
        lines.append(
            f"{row['problem_no']} & {instance} & {row['vidal_hgs']} & "
            f"{row['proposed_v2']} & {row['difference']} & "
            f"{row['difference_pct']} & {row['time_limit_s']} \\\\"
        )
    lines.extend([r"\hline", r"\end{tabular}", r"\end{table}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_png(path: Path, rows: list[dict], title: str) -> None:
    import matplotlib.pyplot as plt

    headers = [
        "Prob. #", "Prob. code", "Vidal HGS", "Proposed v2",
        "Difference", "% Difference", "Time Limit T(s)",
    ]
    cells = [[
        row["problem_no"], row["instance"], row["vidal_hgs"],
        row["proposed_v2"], row["difference"], row["difference_pct"],
        row["time_limit_s"],
    ] for row in rows]

    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    height = 1.3 + 0.34 * len(rows)
    fig, axis = plt.subplots(figsize=(10.4, height))
    axis.axis("off")
    axis.set_title(title, fontsize=12, fontweight="bold", pad=12)
    table = axis.table(
        cellText=cells,
        colLabels=headers,
        cellLoc="center",
        colLoc="center",
        loc="upper center",
        colWidths=[0.08, 0.19, 0.13, 0.14, 0.13, 0.16, 0.17],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.6)
    table.scale(1.0, 1.18)

    for (row_index, col_index), cell in table.get_celld().items():
        cell.set_facecolor("white")
        cell.set_edgecolor("black")
        if row_index == 0:
            cell.set_text_props(fontweight="bold")
            cell.visible_edges = "BT"
            cell.set_linewidth(0.8)
            if col_index == 6:
                cell.get_text().set_color("red")
        else:
            cell.visible_edges = ""

    # Bold the better value in each data row; ties are bold in both columns.
    for index, row in enumerate(rows, start=1):
        vidal = float(row["vidal_hgs"])
        proposed = float(row["proposed_v2"])
        if vidal <= proposed:
            table[index, 2].get_text().set_fontweight("bold")
        if proposed <= vidal:
            table[index, 3].get_text().set_fontweight("bold")

    # Bottom rule, matching the compact manuscript-table style.
    last_row = len(rows)
    for col_index in range(len(headers)):
        table[last_row, col_index].visible_edges = "B"
        table[last_row, col_index].set_linewidth(0.8)

    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposed-runs", type=Path, required=True)
    parser.add_argument("--vidal-runs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--title", default="Quick comparison of Proposed v2 and Vidal HGS-CVRP")
    args = parser.parse_args()

    rows = matched_rows(args.proposed_runs, args.vidal_runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "comparison_table.csv"
    png_path = args.output_dir / "comparison_table.png"
    tex_path = args.output_dir / "comparison_table.tex"
    write_csv(csv_path, rows)
    write_png(png_path, rows, args.title)
    write_latex(tex_path, rows, args.title)

    wins = sum(float(row["difference"]) < 0 for row in rows)
    ties = sum(float(row["difference"]) == 0 for row in rows)
    losses = len(rows) - wins - ties
    mean_pct = sum(float(row["difference_pct"]) for row in rows) / len(rows)
    print(f"Matched rows: {len(rows)}")
    print(f"Proposed v2 wins/ties/losses: {wins}/{ties}/{losses}")
    print(f"Mean percentage difference (v2 - HGS): {mean_pct:.3f}%")
    print(f"CSV: {csv_path}")
    print(f"PNG: {png_path}")
    print(f"LaTeX: {tex_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
