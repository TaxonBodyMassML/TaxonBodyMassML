"""
Extract XGBoost gain-based feature importances for Supplementary S2.

Outputs:
  - Console: normalized % importance per taxonomy rank
  - predictive_models/results/feature_importance.png

Run from repo root:
  predictive_models/.venv/bin/python scripts/extract_feature_importance.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xgboost as xgb

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = REPO / "artifacts" / "model.ubj"
OUT_DIR = REPO / "predictive_models" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Loading model from {ARTIFACT} ...")
model = xgb.Booster()
model.load_model(str(ARTIFACT))
print("Model loaded.")

scores = model.get_score(importance_type="gain")

# Taxonomy columns in hierarchical order
RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
missing = [r for r in RANKS if r not in scores]
if missing:
    print(f"Warning: ranks not in scores (zero gain): {missing}")

total = sum(scores.values())
pct = {r: 100.0 * scores.get(r, 0.0) / total for r in RANKS}

print("\n=== Feature importances (gain, normalised to 100%) ===")
for rank in RANKS:
    bar = "#" * int(pct[rank] / 2)
    print(f"  {rank:<10s} {pct[rank]:6.2f}%  {bar}")

# Print LaTeX tabular
print("\n=== LaTeX: feature importance table ===")
print(r"\begin{table}[ht]")
print(r"\centering")
print(r"\caption{XGBoost gain-based feature importances for \texttt{TaxonBodyMassML},")
print(r"normalised to 100\%. Gain measures the average improvement in loss reduction")
print(r"per split using each feature across all trees.}")
print(r"\label{tab:feature_importance}")
print(r"\begin{tabular}{lr}")
print(r"\toprule")
print(r"Taxonomy rank & Relative importance (\%) \\")
print(r"\midrule")
for rank in RANKS:
    print(f"\\texttt{{{rank}}} & {pct[rank]:.1f} \\\\")
print(r"\bottomrule")
print(r"\end{tabular}")
print(r"\end{table}")

# Figure
fig, ax = plt.subplots(figsize=(5, 3.5))
vals = [pct[r] for r in RANKS]
colors = ["#4a90d9" if r in ("species", "genus") else "#aacde8" for r in RANKS]
bars = ax.barh(RANKS, vals, color=colors, edgecolor="white", height=0.65)
ax.set_xlabel("Relative importance (%, gain)")
ax.set_xlim(0, max(vals) * 1.15)
for bar, v in zip(bars, vals):
    ax.text(
        v + max(vals) * 0.01,
        bar.get_y() + bar.get_height() / 2,
        f"{v:.1f}%",
        va="center",
        fontsize=8,
    )
ax.invert_yaxis()
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
out_path = OUT_DIR / "feature_importance.png"
plt.savefig(out_path, dpi=180)
print(f"\nFigure saved to {out_path}")
