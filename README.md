# Adaptive Hybrid ALNS-HGS for the CVRP

This repository contains the Python implementation and experiment utilities for
an adaptive hybrid metaheuristic for the Capacitated Vehicle Routing Problem
(CVRP). The method combines two offspring-generation paths inside a small
population:

- order crossover (OX) followed by Split decoding;
- adaptive ALNS perturbation with six operators;
- granular local search, including SWAP* and 2-opt* neighborhoods;
- HGS-style biased-fitness population management and broken-pairs diversity;
- adaptive penalties for capacity and fleet-size violations;
- tabu and movement memories used as an admission filter;
- stagnation-dependent destruction sizes and double-bridge diversification.

The solver reads TSPLIB `EUC_2D` CVRP instances, enforces the vehicle limit
`K`, and validates customer coverage, route capacity, and fleet size before a
solution is returned or written to an experiment file.

## Repository layout

| Path | Purpose |
| --- | --- |
| `CVRP_TS_ALNS_v2.py` | Main Python solver and single-instance CLI |
| `Dataset-VRP/` | The 30 benchmark instances used in the paper |
| `run_experiments.py` | Reproducible multi-instance, multi-seed runner |
| `run_ablations.ps1` | ALNS-only, recombination-only, and fixed-adaptation ablations |
| `run_vidal_experiments.py` | Matched-budget runner for an external Vidal HGS executable |
| `run_exact_limits.py` | Helper for matched paper time limits |
| `summarize_multiseed_results.py` | Validates and summarizes matched multi-seed runs |
| `make_comparison_table.py` | Generates comparison tables from run CSV files |
| `make_merged_paper_table.py` | Merges proposed and HGS results for paper tables |
| `paper_reference_values.csv` | Instance order, reference values, and paper budgets |
| `results/paper_multiseed_10seed/` | Final aggregate 10-seed comparison artifacts |
| `tests/` | Infrastructure and feasibility regression tests |

Generated raw runs are written under `benchmark_results/` and are ignored by
Git. This keeps the repository small while preserving the final aggregate
tables under `results/`.

## Requirements

- Python 3.10 or newer
- `matplotlib` 3.5 or newer
- PowerShell 5.1 or newer only for the supplied `.ps1` orchestration scripts

Create an isolated environment and install the Python dependency:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux or macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Quick start

Run the solver on one included instance:

```bash
python CVRP_TS_ALNS_v2.py Dataset-VRP/A-n32-k5.vrp --verbose
```

The command prints the best feasible solution and saves a convergence/route
plot as `cvrp_ts_alns_result.png`.

For a short reproducibility smoke test with two seeds and a five-second budget:

```bash
python run_experiments.py A-n32-k5.vrp --seeds 1-2 --time-limit 5 \
  --output-dir benchmark_results/smoke --verbose
```

On PowerShell, the same command can be written on one line:

```powershell
python run_experiments.py A-n32-k5.vrp --seeds 1-2 --time-limit 5 --output-dir benchmark_results\smoke --verbose
```

Each run is checked for exact customer coverage, capacity feasibility, and the
vehicle limit before it is recorded. The runner also records the Git commit,
working-tree state, Python version, platform, and solver SHA-256 hash.

## Paper experiment

Run all 30 instances with seeds 1 through 10 and the piecewise time budget
implemented by `default_time_limit`:

```bash
python run_experiments.py --seeds 1-10 \
  --output-dir benchmark_results/proposed --resume
```

This is a long experiment. Use `--time-limit` for short checks. The main
options are:

```text
--fixed-penalty
--fixed-removal
--fixed-operator-weights
--search-mode {full,alns_only,recombination_only}
--resume
--verbose
```

## Ablation study

The PowerShell script runs the five component/path variants used by the
ablation infrastructure over the 30 paper instances and ten seeds:

```powershell
.\run_ablations.ps1 -PythonExe (Get-Command python).Source
```

The full method should be run separately with `run_experiments.py` under the
same seeds and time budgets before comparing variants.

## Comparison with Vidal HGS-CVRP

`run_vidal_experiments.py` expects an independently built HGS-CVRP executable;
the executable is not bundled in this repository. A short matched-budget run
looks like this:

```bash
python run_vidal_experiments.py A-n32-k5.vrp \
  --hgs-exe /path/to/hgs-executable --seeds 1-2 --time-limit 5 \
  --output-dir benchmark_results/vidal-smoke
```

After both methods have completed matching seeds and budgets, generate the
aggregate table with:

```bash
python summarize_multiseed_results.py \
  --proposed-runs benchmark_results/proposed/runs.csv \
  --vidal-runs benchmark_results/vidal/runs.csv \
  --references paper_reference_values.csv \
  --expected-seeds 1-10 \
  --output-dir benchmark_results/multiseed-summary
```

## Tests

Run the regression tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

## Reproducibility notes

- Distances use the TSPLIB `EUC_2D` rule: `int(distance + 0.5)`.
- The vehicle limit is read from the instance comment or the `-kK` suffix.
- The proposed solver is independent by default. External HGS warm-starting is
  disabled unless `--allow-hgs-warmstart` is explicitly supplied.
- The default paper time budget depends on the number of customers; see
  `default_time_limit` in `run_experiments.py`.
- Random seeds are explicit and recorded in every run CSV.
- Aggregate results report best, average, sample standard deviation, median,
  worst, and the seeds attaining the best result.

## Citation

If this code supports academic work, please cite the accompanying paper:

```bibtex
@inproceedings{dong2026adaptive,
  author    = {Nguyen D. H. Dong and Hoang T. Doan and Uyen T. Nguyen},
  title     = {An Adaptive Hybrid ALNS-HGS Metaheuristic for the
               Capacitated Vehicle Routing Problem},
  booktitle = {International Conference on Computational Social Networks},
  year      = {2026},
  note      = {Accepted for publication}
}
```
