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

# ---------------------------------------------------------------------------
# Load and filter to the 37,839 rows used in training
# ---------------------------------------------------------------------------
df = pd.read_csv(DATA / "BodyMass_second_pass.csv")

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
# LaTeX tabular for per-kingdom (S1 table)
# ---------------------------------------------------------------------------
print("\n\n=== LaTeX: per-kingdom table ===")
print(r"\begin{table}[ht]")
print(r"\centering")
print(r"\caption{Training data coverage by kingdom. $n_{\text{rec}}$ = number of records;")
print(r"$n_{\text{spp}}$ = unique species; mass range in $\log_{10}$ g (min / median / max).}")
print(r"\label{tab:coverage_kingdom}")
print(r"\begin{tabular}{lrrrl}")
print(r"\toprule")
print(r"Kingdom & $n_{\text{rec}}$ & $n_{\text{spp}}$ & & Mass range ($\log_{10}$ g) \\")
print(r"\midrule")
for kingdom, row in by_kingdom.iterrows():
    mass_range = f"{row['log10_min']:.1f} / {row['log10_med']:.1f} / {row['log10_max']:.1f}"
    print(
        f"{kingdom} & {int(row['n_records']):,} & {int(row['n_species']):,} & & {mass_range} \\\\"
    )
print(r"\bottomrule")
print(r"\end{tabular}")
print(r"\end{table}")

# ---------------------------------------------------------------------------
# LaTeX tabular for per-class (top 20, S1 table)
# ---------------------------------------------------------------------------
print("\n\n=== LaTeX: per-class table (top 20) ===")
print(r"\begin{table}[ht]")
print(r"\centering")
print(r"\caption{Training data coverage by class (top 20 by record count).}")
print(r"\label{tab:coverage_class}")
print(r"\begin{tabular}{lrrl}")
print(r"\toprule")
print(r"Class & $n_{\text{rec}}$ & $n_{\text{spp}}$ & Mass range ($\log_{10}$ g) \\")
print(r"\midrule")
for cls, row in by_class.head(20).iterrows():
    mass_range = f"{row['log10_min']:.1f}–{row['log10_max']:.1f}"
    print(f"{cls} & {int(row['n_records']):,} & {int(row['n_species']):,} & {mass_range} \\\\")
print(r"\bottomrule")
print(r"\end{tabular}")
print(r"\end{table}")
