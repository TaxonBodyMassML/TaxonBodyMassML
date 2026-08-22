"""
Extract training-data statistics for the manuscript.

Outputs:
  - Smallest and largest species (Methods §2.1)
  - Per-kingdom and per-class breakdown table (Results §3.2, Supplementary S1)
  - LaTeX tabular source for both tables

Run from repo root:
  predictive_models/.venv/bin/python scripts/extract_training_stats.py
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
RESULTS = REPO / "predictive_models" / "results"
RESULTS.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Load and filter to the 37,839 rows used in training
# ---------------------------------------------------------------------------
df = pd.read_csv(DATA / "passes" / "TaxonBodyMass_curated.csv")

FEATURES = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
df = df.dropna(subset=FEATURES + ["mass_g"])
df = df[df["mass_g"] > 0]  # guard against non-positive masses before log

print(f"Rows after filtering: {len(df):,}")

# ---------------------------------------------------------------------------
# Smallest and largest species
# ---------------------------------------------------------------------------
idx_min = df["mass_g"].idxmin()
idx_max = df["mass_g"].idxmax()
smallest = df.loc[idx_min, ["taxon", "mass_g", "kingdom", "class"]]
largest = df.loc[idx_max, ["taxon", "mass_g", "kingdom", "class"]]

print("\n--- Smallest species ---")
print(f"  Taxon  : {smallest['taxon']}")
print(f"  mass_g : {smallest['mass_g']:.4g} g  (log10 = {math.log10(smallest['mass_g']):.3f})")
print(f"  Kingdom: {smallest['kingdom']}   Class: {smallest['class']}")

print("\n--- Largest species ---")
print(f"  Taxon  : {largest['taxon']}")
print(f"  mass_g : {largest['mass_g']:.4g} g  (log10 = {math.log10(largest['mass_g']):.3f})")
print(f"  Kingdom: {largest['kingdom']}   Class: {largest['class']}")


# ---------------------------------------------------------------------------
# Per-kingdom summary
# ---------------------------------------------------------------------------
def summarise(grpby_col):
    g = df.groupby(grpby_col)
    out = pd.DataFrame(
        {
            "n_records": g["mass_g"].count(),
            "n_species": g["taxon"].nunique(),
            "log10_min": g["mass_g"].apply(lambda x: math.log10(x.min())),
            "log10_med": g["mass_g"].apply(lambda x: math.log10(x.median())),
            "log10_max": g["mass_g"].apply(lambda x: math.log10(x.max())),
        }
    ).sort_values("n_records", ascending=False)
    return out


by_kingdom = summarise("kingdom")
by_class = summarise("class")

print("\n\n=== Per-kingdom summary ===")
print(by_kingdom.to_string(float_format="{:.2f}".format))

print("\n\n=== Per-class summary (top 25 by record count) ===")
print(by_class.head(25).to_string(float_format="{:.2f}".format))


# ---------------------------------------------------------------------------
# LaTeX tabular for per-kingdom — written to ms/results/tab_kingdom.tex
# ---------------------------------------------------------------------------
def _tabular_kingdom(df_k):
    lines = [
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r" & & \multicolumn{2}{c}{Mass range} \\",
        r"\cmidrule(l){3-4}",
        r"Kingdom & $n_{\text{rec}}$ & min & max \\",
        r"\midrule",
    ]
    for kingdom, row in df_k.iterrows():
        lines.append(
            f"{kingdom} & {int(row['n_records']):,} & ${row['log10_min']:.1f}$ & ${row['log10_max']:.1f}$ \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    return "\n".join(lines)


out_kingdom = RESULTS / "tab_kingdom.tex"
out_kingdom.write_text(_tabular_kingdom(by_kingdom))
print(f"\nWrote {out_kingdom}")


# ---------------------------------------------------------------------------
# LaTeX tabular for per-class (top 20) — written to ms/results/tab_class.tex
# ---------------------------------------------------------------------------
def _tabular_class(df_c, n=20):
    lines = [
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r" & & \multicolumn{2}{c}{Mass range} \\",
        r"\cmidrule(l){3-4}",
        r"Class & $n_{\text{rec}}$ & min & max \\",
        r"\midrule",
    ]
    for cls, row in df_c.head(n).iterrows():
        lines.append(
            f"{cls} & {int(row['n_records']):,} & ${row['log10_min']:.1f}$ & ${row['log10_max']:.1f}$ \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    return "\n".join(lines)


out_class = RESULTS / "tab_class.tex"
out_class.write_text(_tabular_class(by_class))
print(f"Wrote {out_class}")
