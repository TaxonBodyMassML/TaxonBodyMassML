"""
ncbi_fallback.py
----------------
contributors: Grant Pasquantonio
pasquang@oregonstate.edu
3-4-2026
purpose: use NCBI Taxonomy API to fill in missing taxonomy fields
         not resolved by GBIF. Uses exact name matching via esearch
         + efetch.

Input:  ./data/BodyMass_GBIF_pass.csv
Output: ./data/BodyMass_NCBI_pass.csv
"""

# pylint: disable=duplicate-code

import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests

INPUT_CSV = "./data/passes/TaxonBodyMass_GBIF_pass.csv"
OUTPUT_CSV = "./data/passes/TaxonBodyMass_NCBI_pass.csv"

STARTING_INDEX = 0
MISSED_SPECIES_PATH = "./data/passes/missed_species_ncbi.txt"

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


_RETRY_DELAYS = (2.0, 5.0, 10.0)
_TRANSIENT = {429, 500, 502, 503, 504}


def _ncbi_get(url, params):
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
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


def ncbi_match(input_name):
    """
    Get taxonomy lineage from NCBI
    """

    params = {"db": "taxonomy", "term": input_name, "retmode": "json"}

    r = _ncbi_get(NCBI_ESEARCH, params)

    if r.status_code != 200:
        return {}

    data = r.json()

    id_list = data.get("esearchresult", {}).get("idlist", [])

    if not id_list:
        return {}

    tax_id = id_list[0]

    params = {"db": "taxonomy", "id": tax_id, "retmode": "xml"}

    r = _ncbi_get(NCBI_EFETCH, params)

    if r.status_code != 200:
        return {}

    return r.text


def parse_ncbi_xml(xml_text):
    """
    parse_ncbi_xml()
    inputs: xml_text is an xml object that must be parsed for taxonomy data
    output: returns taxonomy
    """

    taxons = {}

    root = ET.fromstring(xml_text)

    lineage = root.find(".//LineageEx")

    if lineage is not None:
        for taxon in lineage.findall("Taxon"):

            rank = taxon.find("Rank").text.lower()
            name = taxon.find("ScientificName").text

            taxons[rank] = name

    species_ = root.find(".//ScientificName")
    if species_ is not None:
        taxons["species"] = species_.text

    # NCBI uses "Metazoa" where other databases use the formal kingdom "Animalia"
    if taxons.get("kingdom") == "Metazoa":
        taxons["kingdom"] = "Animalia"

    return taxons


df = pd.read_csv(INPUT_CSV)

taxonomy_fields = [
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
]

missed_species = []


for i, row in df.iterrows():

    if i < STARTING_INDEX:
        continue

    missing_fields = [field for field in taxonomy_fields if pd.isna(row[field])]  # noqa

    if not missing_fields:
        continue

    if i % 25 == 0:
        print("Saving taxonomy data from index:", i)
        df.to_csv(OUTPUT_CSV, index=False)

    NAME = str(row["taxon"]).strip().replace("_", " ")

    if not NAME or NAME == "nan":
        continue

    try:

        print("Query:", NAME)

        xml_result = ncbi_match(NAME)

        if not xml_result:
            missed_species.append(NAME)
            continue

        taxonomy = parse_ncbi_xml(xml_result)

        for field in missing_fields:
            if field in taxonomy:
                df.at[i, field] = taxonomy[field]

        time.sleep(0.34)

    except (FileNotFoundError, ValueError, requests.RequestException) as e:
        print(f"Failed to process {NAME}: {e}")
        missed_species.append(NAME)


df.to_csv(OUTPUT_CSV, index=False)

print("Saved:", OUTPUT_CSV)


with open(MISSED_SPECIES_PATH, "w", encoding="utf-8") as f:

    for species in missed_species:
        f.write(species + "\n")

print("Missed:", len(missed_species))
