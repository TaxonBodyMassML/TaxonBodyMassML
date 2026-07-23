"""
Docstring for data-combination.combination_api
contributors: Grant Pasquantonio
pasquang@oregonstate.edu
1-16-2026
purpose: use gbif taxonomy API to fuzzy match species taxonomy
         to each species in Mark Novak's BodyMass dataset.
"""

# pylint: disable=duplicate-code

import os
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

INPUT_CSV = "./data/BodyMass.csv"
OUTPUT_CSV = "./data/BodyMass_with_full_taxonomy.csv"

GBIF_MATCH_URL = "https://api.gbif.org/v2/species/match"

# use starting index to start from the last saved
# index in case of interruption/failure
STARTING_INDEX = 0
MISSED_SPECIES_PATH = "./data/missed_species.txt"

# ---------------------------------------------------------------------------
# Session (connection reuse)
# ---------------------------------------------------------------------------
_APP_VERSION = "1.0.0"
_EMAIL = os.environ.get("TAXONBODYMASSML_EMAIL", "")
_USER_AGENT = (
    f"TaxonBodyMassML/{_APP_VERSION} (contact: {_EMAIL})"
    if _EMAIL
    else f"TaxonBodyMassML/{_APP_VERSION}"
)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": _USER_AGENT})

# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
_RETRY_DELAYS = (1.0, 2.0, 4.0)
_TRANSIENT = {429, 500, 502, 503, 504}


def _http_get(url, params, *, timeout=10):
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            resp = _SESSION.get(url, params=params, timeout=timeout)
            if resp.status_code not in _TRANSIENT:
                return resp
        except (requests.ConnectionError, requests.Timeout):
            if delay is None:
                raise
        if delay is not None:
            time.sleep(delay)
    return resp


def gbif_match(input_name):
    """
    gbif_match()
    inputs: input_name is a string which represents
            the scientific name of target species
    output: returns JSON response from fuzzy match API
    """
    r = _http_get(GBIF_MATCH_URL, {"scientificName": input_name})
    if r.status_code != 200:
        return {}
    return r.json()


df = pd.read_csv(INPUT_CSV)

# these are the new columns that will be added to our dataset
taxonomy_fields = [
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
    "confidence",
]

# initialize new columns
for field in taxonomy_fields:
    if field not in df.columns:
        df[field] = None

# temporary storage for any species which could not be found or
# resulted in error upon request to the API
missed_species = []


def _fetch_row(args):
    idx, name = args
    try:
        result = gbif_match(name)
        classification = result.get("classification") or []
        rank_map = {r["rank"].lower(): r["name"] for r in classification}
        confidence_score = (result.get("diagnostics") or {}).get("confidence")
        return idx, rank_map, confidence_score, None
    except (requests.RequestException, KeyError, AttributeError) as e:
        print(f"Failed on {name}: {e}")
        return idx, {}, None, name


# build the work list, skipping already-processed rows
work = [
    (i, str(row["taxon"]).strip().replace("_", " "))
    for i, row in df.iterrows()
    if i >= STARTING_INDEX and str(row["taxon"]).strip() not in ("", "nan")
]

# process in chunks of 100 (preserves checkpoint saves); parallelize within each chunk
CHUNK_SIZE = 100
with ThreadPoolExecutor(max_workers=8) as pool:
    for chunk_start in range(0, len(work), CHUNK_SIZE):
        chunk = work[chunk_start : chunk_start + CHUNK_SIZE]
        for idx, rank_map, confidence_score, missed in pool.map(_fetch_row, chunk):
            if missed:
                missed_species.append(missed)
            else:
                for rank, rank_name in rank_map.items():
                    df.at[idx, rank] = rank_name
                df.at[idx, "confidence"] = confidence_score
                print(df.at[idx, "taxon"] if "taxon" in df.columns else idx)
        print(f"Saving checkpoint at index {chunk[-1][0]}")
        df.to_csv(OUTPUT_CSV, index=False)

# final save of results to the output csv
df.to_csv(OUTPUT_CSV, index=False)
print(f"Saved: {OUTPUT_CSV}")

# write all missed species to the output txt
with open(MISSED_SPECIES_PATH, "w", encoding="utf-8") as missed_species_list:
    for species in missed_species:
        missed_species_list.write(species + "\n")
    print("Total missed species:", len(missed_species))
    print("List of missed species has been saved to:", MISSED_SPECIES_PATH)
