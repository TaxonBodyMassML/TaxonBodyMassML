"""
Export model performance metrics table for the manuscript (Table 3 / tab:metrics).

Reads predictive_models/results/metrics.json, which is written by
predictive_models/decision_tree.py.  The "filtered_gt0p1g" key is only
present after decision_tree.py has been re-run; if missing, this script
exits with an informative error.

Outputs:
  ms/results/tab_metrics.tex

Run from repo root:
  predictive_models/.venv/bin/python scripts/extract_test_metrics.py
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
METRICS_PATH = REPO / "predictive_models" / "results" / "metrics.json"
RESULTS = REPO / "predictive_models" / "results"
RESULTS.mkdir(exist_ok=True)

with open(METRICS_PATH) as f:
    m = json.load(f)

if "filtered_gt0p1g" not in m:
    sys.exit(
        "ERROR: 'filtered_gt0p1g' key missing from metrics.json.\n"
        "Re-run predictive_models/decision_tree.py to regenerate it."
    )

full = m
filt = m["filtered_gt0p1g"]

lines = [
    r"\begin{tabular}{lrrrr}",
    r"\toprule",
    r"Test set & $R^2$ & RMSE & MAE & $n$ \\",
    r"\midrule",
    (
        f"Full test set"
        f" & {full['r2']:.2f}"
        f" & {full['rmse']:.2f}"
        f" & {full['mae']:.2f}"
        f" & {full['n_test']:,} \\\\"
    ),
    (
        r"Reduced (mass $>0.1$\,g)"
        f" & {filt['r2']:.2f}"
        f" & {filt['rmse']:.2f}"
        f" & {filt['mae']:.2f}"
        f" & {filt['n']:,} \\\\"
    ),
    r"\bottomrule",
    r"\end{tabular}",
    "",
]

out = RESULTS / "tab_metrics.tex"
out.write_text("\n".join(lines))
print(f"Wrote {out}")
