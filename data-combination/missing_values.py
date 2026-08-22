"""
Docstring for missing_values
contributors: Grant Pasquantonio
pasquang@oregonstate.edu
3-4-2026
purpose: analyze missing values in first pass of taxonomy dataset
"""

import pandas as pd

# import matplotlib.pyplot as plt

INPUT_FILE_PATH = "./data/passes/TaxonBodyMass_GBIF_pass.csv"
OUTPUT_FILE_PATH = "./data/species_missing_order_class.csv"

df = pd.read_csv(INPUT_FILE_PATH)

df = df.drop(["subspecies", "form"], axis=1)

print("Number of missing values in each column:")
print(df.isna().sum())

df = df[df["confidence"].notna()]

df_missing = pd.DataFrame()
df_missing = pd.concat([df_missing, df[df["class"].isna()]], ignore_index=True)
df_missing = pd.concat([df_missing, df[df["order"].isna()]], ignore_index=True)

print(df_missing)
df_missing.to_csv(OUTPUT_FILE_PATH, index=False)

df = df[df["class"].notna()]
df = df[df["order"].notna()]

print("Number of missing values in each column:")
print(df.isna().sum())
print(df)
