"""
wikidata_fallback.py
--------------------
Purpose: use Wikidata SPARQL to fill in taxonomy fields not resolved
         by GBIF, NCBI, WoRMS, or COL. Traverses the P171 (parent taxon)
         chain to extract all seven Linnaean ranks.

Wikidata properties used:
  P225 - taxon name
  P105 - taxon rank
  P171 - parent taxon (transitive closure via P171*)

Input:  ./data/BodyMass_COL_pass.csv
Output: ./data/BodyMass_Wikidata_pass.csv
"""

import time

import pandas as pd
import requests

INPUT_CSV = "./data/passes/TaxonBodyMass_COL_pass.csv"
OUTPUT_CSV = "./data/passes/TaxonBodyMass_Wikidata_pass.csv"
MISSED_SPECIES_PATH = "./data/passes/missed_species_wikidata.txt"

SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "TaxonBodyMassML/0.4.0 (https://github.com/TaxonBodyMassML/TaxonBodyMassML)",
    "Accept": "application/sparql-results+json",
}

BATCH_SIZE = 10
TAXONOMY_FIELDS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
TARGET_RANKS = set(TAXONOMY_FIELDS)

_RETRY_DELAYS = (5.0, 15.0, 30.0)
_TRANSIENT = {429, 500, 502, 503, 504}


def _sparql_get(query):
    for delay in (*_RETRY_DELAYS, None):
        try:
            r = requests.get(
                SPARQL_URL,
                params={"query": query, "format": "json"},
                headers=HEADERS,
                timeout=60,
            )
            if r.status_code not in _TRANSIENT:
                return r
        except (requests.ConnectionError, requests.Timeout):
            if delay is None:
                raise
        if delay is not None:
            time.sleep(delay)
    return r


def wikidata_batch(names):
    """Return {name: {rank: taxon_name}} for names resolved by Wikidata."""
    # Escape double quotes in names (rare in scientific names but defensive)
    escaped = [n.replace("\\", "\\\\").replace('"', '\\"') for n in names]
    values = " ".join(f'"{n}"' for n in escaped)
    query = f"""
SELECT ?searchName ?rankLabel ?taxonName WHERE {{
  VALUES ?searchName {{ {values} }}
  ?taxon wdt:P225 ?searchName .
  ?taxon wdt:P171* ?ancestor .
  ?ancestor wdt:P225 ?taxonName .
  ?ancestor wdt:P105 ?rank .
  ?rank rdfs:label ?rankLabel .
  FILTER(LANG(?rankLabel) = "en")
}}
"""
    try:
        r = _sparql_get(query)
        if r.status_code != 200:
            print(f"  Wikidata SPARQL error {r.status_code}")
            return {}
    except requests.RequestException as e:
        print(f"  Wikidata request failed: {e}")
        return {}

    out = {}
    for row in r.json().get("results", {}).get("bindings", []):
        name = row["searchName"]["value"]
        rank = row["rankLabel"]["value"]
        taxon_name = row["taxonName"]["value"]
        if rank not in TARGET_RANKS:
            continue
        if name not in out:
            out[name] = {}
        if rank not in out[name]:  # first match per rank wins
            out[name][rank] = taxon_name
    return out


df = pd.read_csv(INPUT_CSV)

needs_idx = df[df[TAXONOMY_FIELDS].isna().any(axis=1)].index
unique_names = (
    df.loc[needs_idx, "taxon"].str.strip().str.replace("_", " ", regex=False).unique().tolist()
)
print(f"Unique taxa needing Wikidata lookup: {len(unique_names)}")

missed = []

for batch_start in range(0, len(unique_names), BATCH_SIZE):
    batch = unique_names[batch_start : batch_start + BATCH_SIZE]
    wiki_map = wikidata_batch(batch)

    for name in batch:
        if name not in wiki_map:
            missed.append(name)
            continue

        rank_map = wiki_map[name]
        mask = (df["taxon"].str.strip().str.replace("_", " ", regex=False) == name) & df[
            TAXONOMY_FIELDS
        ].isna().any(axis=1)
        for idx in df[mask].index:
            for field in TAXONOMY_FIELDS:
                if pd.isna(df.at[idx, field]) and field in rank_map:
                    df.at[idx, field] = rank_map[field]

    print(f"Checkpoint: {min(batch_start + BATCH_SIZE, len(unique_names))}/{len(unique_names)}")
    df.to_csv(OUTPUT_CSV, index=False)
    time.sleep(1.0)  # Wikidata requests: max 1/s

df.to_csv(OUTPUT_CSV, index=False)
print(f"Saved: {OUTPUT_CSV}")

with open(MISSED_SPECIES_PATH, "w", encoding="utf-8") as f:
    for name in missed:
        f.write(name + "\n")
print(f"Wikidata missed: {len(missed)}")
