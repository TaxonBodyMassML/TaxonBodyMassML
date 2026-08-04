"""
filter_kingdoms.py
------------------
Purpose: Remove non-animal eukaryotic kingdoms from the taxonomy dataset.
         Reads BodyMass_ITIS_pass.csv and writes BodyMass_curated.csv,
         preserving the original file as an unfiltered reference.

Kingdoms removed: Plantae, Chromista, Fungi, Viridiplantae
Kingdoms retained: Animalia, Metazoa, Protozoa, Bacteria, Bacillati (+ any UNK)
"""

import pandas as pd

INPUT_FILE_PATH = "./data/BodyMass_ITIS_pass.csv"
OUTPUT_FILE_PATH = "./data/BodyMass_curated.csv"

KINGDOMS_TO_REMOVE = {"Plantae", "Chromista", "Fungi", "Viridiplantae"}

df = pd.read_csv(INPUT_FILE_PATH)

print(f"Rows before filtering: {len(df)}")
print("\nKingdom counts before filtering:")
print(df["kingdom"].value_counts(dropna=False))

removed = df[df["kingdom"].isin(KINGDOMS_TO_REMOVE)]
print(f"\nRows to remove by kingdom:")
print(removed["kingdom"].value_counts())

df = df[~df["kingdom"].isin(KINGDOMS_TO_REMOVE)]

print(f"\nRows after filtering: {len(df)}")
print("\nKingdom counts after filtering:")
print(df["kingdom"].value_counts(dropna=False))

df.to_csv(OUTPUT_FILE_PATH, index=False)
print(f"\nSaved curated dataset to: {OUTPUT_FILE_PATH}")
