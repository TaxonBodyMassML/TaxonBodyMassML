"""
worms_fallback.py
-----------------
Purpose: use WoRMS AphiaRecordsByMatchNames to fill in taxonomy fields
         not resolved by GBIF or NCBI. Particularly effective for
         marine invertebrates, fish, and other aquatic taxa.

Accepted match types: exact, phonetic, near_1.

Input:  ./data/BodyMass_NCBI_pass.csv
Output: ./data/BodyMass_WoRMS_pass.csv
"""

import time

import pandas as pd
import requests

INPUT_CSV = "./data/BodyMass_NCBI_pass.csv"
OUTPUT_CSV = "./data/BodyMass_WoRMS_pass.csv"
MISSED_SPECIES_PATH = "./data/missed_species_worms.txt"

WORMS_URL = "https://www.marinespecies.org/rest/AphiaRecordsByMatchNames"

ACCEPTED_MATCH_TYPES = {"exact", "phonetic", "near_1"}
BATCH_SIZE = 50
TAXONOMY_FIELDS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
WORMS_RANK_FIELDS = ["kingdom", "phylum", "class", "order", "family", "genus"]


def worms_match_batch(names):
    """Return {name: rank_map} for names with accepted match types."""
    params = [("scientificnames[]", n) for n in names]
    params.append(("marine_only", "false"))
    try:
        r = requests.get(WORMS_URL, params=params, timeout=30)
        if r.status_code != 200:
            return {}
    except requests.RequestException as e:
        print(f"WoRMS batch request failed: {e}")
        return {}
    out = {}
    for name, records in zip(names, r.json()):
        if not records:
            continue
        # Prefer accepted status; fall back to first record
        best = next(
            (rec for rec in records if (rec or {}).get("status") == "accepted"),
            records[0],
        )
        if not best or best.get("match_type") not in ACCEPTED_MATCH_TYPES:
            continue
        rank_map = {f: best[f] for f in WORMS_RANK_FIELDS if best.get(f)}
        if (best.get("rank") or "").lower() == "species":
            rank_map["species"] = best.get("scientificname", "")
        if rank_map:
            out[name] = rank_map
    return out


df = pd.read_csv(INPUT_CSV)

needs_idx = df[df[TAXONOMY_FIELDS].isna().any(axis=1)].index
unique_names = (
    df.loc[needs_idx, "taxon"].str.strip().str.replace("_", " ", regex=False).unique().tolist()
)
print(f"Unique taxa needing WoRMS lookup: {len(unique_names)}")

missed = []

for batch_start in range(0, len(unique_names), BATCH_SIZE):
    batch = unique_names[batch_start : batch_start + BATCH_SIZE]
    worms_map = worms_match_batch(batch)

    for name in batch:
        if name not in worms_map:
            missed.append(name)
            continue

        rank_map = worms_map[name]
        mask = (df["taxon"].str.strip().str.replace("_", " ", regex=False) == name) & df[
            TAXONOMY_FIELDS
        ].isna().any(axis=1)
        for idx in df[mask].index:
            for field in TAXONOMY_FIELDS:
                if pd.isna(df.at[idx, field]) and field in rank_map:
                    df.at[idx, field] = rank_map[field]

    print(f"Checkpoint: {min(batch_start + BATCH_SIZE, len(unique_names))}/{len(unique_names)}")
    df.to_csv(OUTPUT_CSV, index=False)
    time.sleep(0.5)

df.to_csv(OUTPUT_CSV, index=False)
print(f"Saved: {OUTPUT_CSV}")

with open(MISSED_SPECIES_PATH, "w", encoding="utf-8") as f:
    for name in missed:
        f.write(name + "\n")
print(f"WoRMS missed: {len(missed)}")
