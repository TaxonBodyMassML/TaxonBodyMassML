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
    ("species=UNK", ["species"]),
    ("genus+species=UNK", ["genus", "species"]),
    ("family+genus+species=UNK", ["family", "genus", "species"]),
    ("order+…+species=UNK", ["order", "family", "genus", "species"]),
    ("class+…+species=UNK", ["class", "order", "family", "genus", "species"]),
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

# LaTeX table
print("\n=== LaTeX: UNK-rank error table ===")
print(r"\begin{table}[ht]")
print(r"\centering")
print(r"\caption{Mean absolute error (MAE, $\log_{10}$ g) on the 3{,}784-row test set")
print(r"under progressive masking of finer taxonomy ranks to \texttt{UNK}.")
print(r"$\Delta$MAE is the penalty relative to full-taxonomy prediction.}")
print(r"\label{tab:unk_errors}")
print(r"\begin{tabular}{lrr}")
print(r"\toprule")
print(r"Taxonomy resolution & MAE ($\log_{10}$ g) & $\Delta$MAE \\")
print(r"\midrule")
for label, mae, delta in results:
    label_tex = label.replace("+", r"+").replace("…", r"\ldots{}")
    sign = "+" if delta > 0 else ("" if delta == 0 else "")
    delta_str = f"---" if delta == 0 else f"{delta:+.4f}"
    print(f"{label_tex} & {mae:.4f} & {delta_str} \\\\")
print(r"\bottomrule")
print(r"\end{tabular}")
print(r"\end{table}")
