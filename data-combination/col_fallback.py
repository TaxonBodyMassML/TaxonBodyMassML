"""
col_fallback.py
---------------
Purpose: use Catalogue of Life ChecklistBank to fill in taxonomy fields
         not resolved by GBIF, NCBI, or WoRMS. COL directly sources from
         the Reptile Database, making it particularly effective for Squamata.

Input:  ./data/BodyMass_WoRMS_pass.csv
Output: ./data/BodyMass_COL_pass.csv
"""

import time

import pandas as pd
import requests

INPUT_CSV = "./data/passes/TaxonBodyMass_WoRMS_pass.csv"
OUTPUT_CSV = "./data/passes/TaxonBodyMass_COL_pass.csv"
MISSED_SPECIES_PATH = "./data/passes/missed_species_col.txt"

COL_URL = "https://api.checklistbank.org/dataset/3/nameusage/search"

TAXONOMY_FIELDS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
COL_RANK_FIELDS = {"kingdom", "phylum", "class", "order", "family", "genus"}

_RETRY_DELAYS = (2.0, 5.0, 15.0)
_TRANSIENT = {429, 500, 502, 503, 504}


def _col_get(params):
    for delay in (*_RETRY_DELAYS, None):
        try:
            r = requests.get(COL_URL, params=params, timeout=30)
            if r.status_code not in _TRANSIENT:
                return r
        except (requests.ConnectionError, requests.Timeout):
            if delay is None:
                raise
        if delay is not None:
            time.sleep(delay)
    return r


def col_lookup(name):
    """Return {rank: taxon_name} for a species name, or {} if not found."""
    params = {"q": name, "rank": "species", "limit": 5}
    try:
        r = _col_get(params)
        if r.status_code != 200:
            return {}
    except requests.RequestException:
        return {}

    data = r.json()
    entries = data.get("result") or data.get("results") or []

    for entry in entries:
        # classification[] is at the top level of each result entry
        classification = entry.get("classification", [])
        rank_map = {}
        for c in classification:
            rank = (c.get("rank") or "").lower()
            val = c.get("name") or ""
            if rank in COL_RANK_FIELDS and val:
                rank_map[rank] = val

        if rank_map:
            rank_map["species"] = name
            return rank_map

    return {}


df = pd.read_csv(INPUT_CSV)

needs_idx = df[df[TAXONOMY_FIELDS].isna().any(axis=1)].index
unique_names = (
    df.loc[needs_idx, "taxon"].str.strip().str.replace("_", " ", regex=False).unique().tolist()
)
print(f"Unique taxa needing COL lookup: {len(unique_names)}")

missed = []

for i, name in enumerate(unique_names):
    rank_map = col_lookup(name)

    if not rank_map:
        missed.append(name)
    else:
        mask = (df["taxon"].str.strip().str.replace("_", " ", regex=False) == name) & df[
            TAXONOMY_FIELDS
        ].isna().any(axis=1)
        for idx in df[mask].index:
            for field in TAXONOMY_FIELDS:
                if pd.isna(df.at[idx, field]) and field in rank_map:
                    df.at[idx, field] = rank_map[field]

    if (i + 1) % 10 == 0:
        print(f"Checkpoint: {i + 1}/{len(unique_names)}")
        df.to_csv(OUTPUT_CSV, index=False)

    time.sleep(0.5)

df.to_csv(OUTPUT_CSV, index=False)
print(f"Saved: {OUTPUT_CSV}")

with open(MISSED_SPECIES_PATH, "w", encoding="utf-8") as f:
    for n in missed:
        f.write(n + "\n")
print(f"COL missed: {len(missed)}")
