"""
itis_fallback.py
----------------
Purpose: use ITIS (Integrated Taxonomic Information System) to fill in
         taxonomy fields not resolved by prior fallbacks. Particularly
         effective for vertebrates, including Squamata and Mammalia.

Input:  ./data/BodyMass_Wikidata_pass.csv
Output: ./data/BodyMass_ITIS_pass.csv
"""

import time

import pandas as pd
import requests

INPUT_CSV = "./data/BodyMass_Wikidata_pass.csv"
OUTPUT_CSV = "./data/BodyMass_ITIS_pass.csv"
MISSED_SPECIES_PATH = "./data/missed_species_itis.txt"

ITIS_BASE = "https://www.itis.gov/ITISWebService/jsonservice"

TAXONOMY_FIELDS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

_RETRY_DELAYS = (2.0, 5.0, 15.0)
_TRANSIENT = {429, 500, 502, 503, 504}


def _itis_get(endpoint, params):
    url = f"{ITIS_BASE}/{endpoint}"
    for delay in (*_RETRY_DELAYS, None):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code not in _TRANSIENT:
                return r
        except (requests.ConnectionError, requests.Timeout):
            if delay is None:
                raise
        if delay is not None:
            time.sleep(delay)
    return r


def itis_lookup(name):
    """Return {rank: taxon_name} for a species name, or {} if not found."""
    try:
        r = _itis_get("searchByScientificName", {"srchKey": name})
        if r.status_code != 200:
            return {}
    except requests.RequestException:
        return {}

    tsn = None
    for entry in r.json().get("scientificNames") or []:
        if entry and entry.get("tsn"):
            tsn = entry["tsn"]
            break

    if not tsn:
        return {}

    try:
        r = _itis_get("getFullHierarchyFromTSN", {"tsn": tsn})
        if r.status_code != 200:
            return {}
    except requests.RequestException:
        return {}

    rank_map = {}
    for entry in r.json().get("hierarchyList") or []:
        if not entry:
            continue
        rank = (entry.get("rankName") or "").lower()
        taxon_name = entry.get("taxonName") or ""
        if rank in TAXONOMY_FIELDS and taxon_name:
            rank_map[rank] = taxon_name

    return rank_map


df = pd.read_csv(INPUT_CSV)

needs_idx = df[df[TAXONOMY_FIELDS].isna().any(axis=1)].index
unique_names = (
    df.loc[needs_idx, "taxon"].str.strip().str.replace("_", " ", regex=False).unique().tolist()
)
print(f"Unique taxa needing ITIS lookup: {len(unique_names)}")

missed = []

for i, name in enumerate(unique_names):
    rank_map = itis_lookup(name)

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

    if (i + 1) % 100 == 0:
        print(f"Checkpoint: {i + 1}/{len(unique_names)}")
        df.to_csv(OUTPUT_CSV, index=False)

    time.sleep(0.5)

df.to_csv(OUTPUT_CSV, index=False)
print(f"Saved: {OUTPUT_CSV}")

with open(MISSED_SPECIES_PATH, "w", encoding="utf-8") as f:
    for n in missed:
        f.write(n + "\n")
print(f"ITIS missed: {len(missed)}")
