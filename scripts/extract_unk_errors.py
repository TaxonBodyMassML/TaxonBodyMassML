"""
Quantify the prediction-error penalty from partial taxonomy resolution (S3).

For each masking level, all test-set species are re-predicted with finer ranks
set to "UNK". The resulting MAE is compared to the full-taxonomy baseline.

Run from repo root:
  predictive_models/.venv/bin/python scripts/extract_unk_errors.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
ARTIFACTS = REPO / "artifacts"
RESULTS = REPO / "predictive_models" / "results"
RESULTS.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Load model and categories
# ---------------------------------------------------------------------------
print("Loading model ...")
model = xgb.Booster()
model.load_model(str(ARTIFACTS / "model.ubj"))

with open(ARTIFACTS / "categories.json") as f:
    categories = json.load(f)

RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

# ---------------------------------------------------------------------------
# Load test set
# ---------------------------------------------------------------------------
test = pd.read_csv(DATA / "test.csv")
y_true_log10 = np.log10(test["mass_g"].values)
x_test = test.drop(columns=["mass_g"]).copy()


# ---------------------------------------------------------------------------
# Align categories exactly as done in decision_tree.py
# ---------------------------------------------------------------------------
def align_to_training(df, categories):
    """Set category dtype for each column using training-time category lists."""
    df = df.copy()
    for col in RANKS:
        if col not in df.columns:
            df[col] = "UNK"
        df[col] = df[col].astype("category")
        cats = list(categories[col]) + (["UNK"] if "UNK" not in categories[col] else [])
        df[col] = df[col].cat.set_categories(cats)
    return df


def predict_mae(df):
    aligned = align_to_training(df, categories)
    dmat = xgb.DMatrix(aligned, enable_categorical=True)
    preds = model.predict(dmat)
    return float(np.mean(np.abs(y_true_log10 - preds)))


# ---------------------------------------------------------------------------
# Baseline: full taxonomy
# ---------------------------------------------------------------------------
print("Computing baseline (full taxonomy) ...")
mae_full = predict_mae(x_test)
print(f"  Baseline MAE: {mae_full:.4f} log10 units")

# ---------------------------------------------------------------------------
# Masking levels: progressively replace finer ranks with UNK
# ---------------------------------------------------------------------------
masking_levels = [
    (
        r"\texttt{species}~$=$~\texttt{``UNK''}",
        ["species"],
    ),
    (
        r"\texttt{genus}$+$\texttt{species}~$=$~\texttt{``UNK''}",
        ["genus", "species"],
    ),
    (
        r"\texttt{family}$+$\texttt{genus}$+$\texttt{species}~$=$~\texttt{``UNK''}",
        ["family", "genus", "species"],
    ),
    (
        r"\texttt{order}$+\ldots+$\texttt{species}~$=$~\texttt{``UNK''}",
        ["order", "family", "genus", "species"],
    ),
    (
        r"\texttt{class}$+\ldots+$\texttt{species}~$=$~\texttt{``UNK''}",
        ["class", "order", "family", "genus", "species"],
    ),
]

results = [("Full taxonomy", mae_full, 0.0)]

for label, mask_cols in masking_levels:
    print(f"  Masking {label} ...")
    df_masked = x_test.copy()
    for col in mask_cols:
        df_masked[col] = "UNK"
    mae = predict_mae(df_masked)
    delta = mae - mae_full
    results.append((label, mae, delta))

# ---------------------------------------------------------------------------
# Print results
# ---------------------------------------------------------------------------
print("\n=== UNK-rank prediction error (log10 MAE) ===")
print(f"{'Masking level':<35s} {'MAE':>8s} {'ΔMAE':>8s}")
print("-" * 55)
for label, mae, delta in results:
    sign = "+" if delta > 0 else ""
    print(f"{label:<35s} {mae:8.4f} {sign}{delta:8.4f}")

# Write LaTeX tabular to ms/results/tab_unk_errors.tex
lines = [
    r"\begin{tabular}{lrr}",
    r"\toprule",
    r"Taxonomy resolution & MAE ($\log_{10}$ g) & $\Delta$MAE \\",
    r"\midrule",
]
for label, mae, delta in results:
    delta_str = "---" if delta == 0 else f"${delta:+.3f}$"
    lines.append(f"{label} & {mae:.4f} & {delta_str} \\\\")
lines += [r"\bottomrule", r"\end{tabular}", ""]
out_tex = RESULTS / "tab_unk_errors.tex"
out_tex.write_text("\n".join(lines))
print(f"\nWrote {out_tex}")
