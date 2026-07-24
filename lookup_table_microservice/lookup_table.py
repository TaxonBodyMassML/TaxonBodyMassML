"""
lookup_table.py
-------------------
Provides API endpoints for prototype lookup
operations in the web development module.
"""

import os
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

GBIF_MATCH_URL = "https://api.gbif.org/v2/species/match"

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# ---------------------------------------------------------------------------
# Session (connection reuse across all GBIF + NCBI calls)
# ---------------------------------------------------------------------------
APP_VERSION = "1.0.0"
_EMAIL = os.environ.get("TAXONBODYMASSML_EMAIL", "")
_USER_AGENT = (
    f"TaxonBodyMassML/{APP_VERSION} (contact: {_EMAIL})"
    if _EMAIL
    else f"TaxonBodyMassML/{APP_VERSION}"
)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": _USER_AGENT})

# ---------------------------------------------------------------------------
# NCBI rate limiter (slot-reservation)
# ---------------------------------------------------------------------------
_NCBI_LOCK = threading.Lock()
_NCBI_NEXT_SLOT: float = 0.0


def _ncbi_rate() -> float:
    return 10.0 if os.environ.get("NCBI_API_KEY") else 3.0


def _ncbi_wait() -> None:
    global _NCBI_NEXT_SLOT  # pylint: disable=global-statement
    with _NCBI_LOCK:
        now = time.monotonic()
        rate = _ncbi_rate()
        _NCBI_NEXT_SLOT = max(_NCBI_NEXT_SLOT, now)
        wait_until = _NCBI_NEXT_SLOT
        _NCBI_NEXT_SLOT += 1.0 / rate
    sleep_for = wait_until - time.monotonic()
    if sleep_for > 0:
        time.sleep(sleep_for)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
_RETRY_DELAYS = (1.0, 2.0, 4.0)
_TRANSIENT = {429, 500, 502, 503, 504}


def _http_get(url, params, *, ncbi=False, timeout=10):
    for delay in (*_RETRY_DELAYS, None):
        if ncbi:
            _ncbi_wait()
            api_key = os.environ.get("NCBI_API_KEY")
            if api_key:
                params = {**params, "api_key": api_key}
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


taxonomy_fields = [
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
]


def ncbi_match(input_name):
    """
    Get taxonomy lineage from NCBI
    """

    r = _http_get(
        NCBI_ESEARCH,
        {"db": "taxonomy", "term": input_name, "retmode": "json"},
        ncbi=True,
    )

    if r.status_code != 200:
        return {}

    data = r.json()

    id_list = data.get("esearchresult", {}).get("idlist", [])

    if not id_list:
        return {}

    tax_id = id_list[0]

    r = _http_get(
        NCBI_EFETCH,
        {"db": "taxonomy", "id": tax_id, "retmode": "xml"},
        ncbi=True,
    )

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

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return taxons

    lineage = root.find(".//LineageEx")

    if lineage is not None:
        for taxon in lineage.findall("Taxon"):

            rank = taxon.find("Rank").text.lower()
            name = taxon.find("ScientificName").text

            taxons[rank] = name

    species_ = root.find(".//ScientificName")
    if species_ is not None:
        taxons["species"] = species_.text

    return taxons


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


@app.route("/single_species", methods=["GET"])
def single_species():
    """
    single_species()
    -------------------
    receive a request for the taxonomy of a single species
    """
    species_name = request.args.get("species_name")

    # if there is no input species name, then return an error
    if not species_name:
        return jsonify({"error": "Missing 'species_name' parameter"}), 400

    species_name = species_name.lower()

    # clean existing taxonomy data for request
    name = str(species_name).strip().replace("_", " ")

    try:
        gbif_result = gbif_match(name)
        print(name)

        taxonomy = {field: gbif_result.get(field) for field in taxonomy_fields}

        if any(taxon_field is None for taxon_field in taxonomy.values()):
            xml_result = ncbi_match(name)
            if xml_result:
                ncbi_taxonomy = parse_ncbi_xml(xml_result)
                taxonomy.update(ncbi_taxonomy)

        taxonomy = {field: taxonomy.get(field) or "UNK" for field in taxonomy_fields}

        all_unk = all(value == "UNK" for value in taxonomy.values())
        if all_unk:
            return (
                jsonify({"error": "Could not find a valid taxonomy for this species."}),
                422,
            )
        return jsonify({"taxonomy": taxonomy}), 200

    except (requests.RequestException, ET.ParseError, AttributeError, KeyError) as e:
        return jsonify({"error": str(e)}), 500


def _resolve_species(name):
    gbif_result = gbif_match(name)

    taxonomy = {field: gbif_result.get(field) for field in taxonomy_fields}

    if any(v is None for v in taxonomy.values()):
        xml_result = ncbi_match(name)
        if xml_result:
            ncbi_taxonomy = parse_ncbi_xml(xml_result)
            taxonomy.update(ncbi_taxonomy)

    taxonomy = {f: taxonomy.get(f) or "UNK" for f in taxonomy_fields}

    if all(value == "UNK" for value in taxonomy.values()):
        return name, None
    return name, taxonomy


@app.route("/multi_species", methods=["GET"])
def multi_species():
    """
    multi_species()
    -------------------
    receive a request for the taxonomy of a list of species
    """
    species_names = request.args.get("species_name")

    if not species_names:
        return jsonify({"error": "Missing 'species_name' parameter"}), 400

    species_list = [
        s.strip().lower().replace("_", " ") for s in species_names.split(",") if s.strip()
    ]

    results = {}

    try:
        workers = min(max(len(species_list), 1), 8)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for name, taxonomy in pool.map(_resolve_species, species_list):
                results[name] = taxonomy  # null included so callers can detect misses

        return jsonify({"taxonomy": results}), 200

    except (requests.RequestException, ET.ParseError, AttributeError, KeyError) as e:
        return jsonify({"error": str(e)}), 500


def _gbif_fuzzy_name(name):
    """Return (input_name, matched_name_or_None) via GBIF fuzzy match."""
    try:
        r = _http_get(GBIF_MATCH_URL, {"scientificName": name})
        if r.status_code != 200:
            return name, None
        data = r.json()
        if data.get("matchType") not in ("EXACT", "FUZZY"):
            return name, None
        matched = data.get("species")
        return name, matched if matched else None
    except requests.RequestException:
        return name, None


@app.route("/fuzzy_lookup", methods=["GET"])
def fuzzy_lookup():
    """
    fuzzy_lookup()
    -------------------
    Like /multi_species but runs GBIF fuzzy name correction first.
    Returns taxonomy keyed by original input name, plus a matched_name field
    per species showing the canonical name GBIF resolved to.
    """
    species_names = request.args.get("species_name")

    if not species_names:
        return jsonify({"error": "Missing 'species_name' parameter"}), 400

    species_list = [
        s.strip().lower().replace("_", " ") for s in species_names.split(",") if s.strip()
    ]

    try:
        workers = min(max(len(species_list), 1), 8)

        # Step 1: fuzzy-correct each name via GBIF
        corrections = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for original, matched in pool.map(_gbif_fuzzy_name, species_list):
                corrections[original] = matched

        # Step 2: resolve taxonomy for corrected (or original) names
        lookup_names = [corrections[n] or n for n in species_list]
        resolved = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for name, taxonomy in pool.map(_resolve_species, lookup_names):
                resolved[name] = taxonomy

        # Step 3: build response keyed by original input name
        results = {}
        for original, lookup_name in zip(species_list, lookup_names):
            results[original] = {
                "matched_name": corrections[original],
                "taxonomy": resolved.get(lookup_name),
            }

        return jsonify({"taxonomy": results}), 200

    except (requests.RequestException, AttributeError, KeyError) as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # use Render's assigned port
    app.run(host="0.0.0.0", port=port)
