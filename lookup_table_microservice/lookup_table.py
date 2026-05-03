"""
lookup_table.py
-------------------
Provides API endpoints for prototype lookup
operations in the web development module.
"""

import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app)

GBIF_MATCH_URL = "https://api.gbif.org/v2/species/match"

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

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

    params = {"db": "taxonomy", "term": input_name, "retmode": "json"}

    r = requests.get(NCBI_ESEARCH, params=params, timeout=10)

    if r.status_code != 200:
        return {}

    data = r.json()

    id_list = data.get("esearchresult", {}).get("idlist", [])

    if not id_list:
        return {}

    tax_id = id_list[0]

    params = {"db": "taxonomy", "id": tax_id, "retmode": "xml"}

    r = requests.get(NCBI_EFETCH, params=params, timeout=10)

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

    return taxons


def gbif_match(input_name):
    """
    gbif_match()
    inputs: input_name is a string which represents
            the scientific name of target species
    output: returns JSON response from fuzzy match API
    """
    params = {
        "scientificName": input_name,
    }
    r = requests.get(GBIF_MATCH_URL, params=params, timeout=10)
    if r.status_code != 200:
        return None
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
    NAME = str(species_name).strip().replace("_", " ")

    try:
        gbif_result = gbif_match(NAME)
        print(NAME)
        
        taxonomy = {
            field: gbif_result.get(field)
            for field in taxonomy_fields
        }

        if any(taxon_field is None for taxon_field in taxonomy.values()):
            xml_result = ncbi_match(NAME)
            if xml_result:
                ncbi_taxonomy = parse_ncbi_xml(xml_result)
                taxonomy.update(ncbi_taxonomy)
                
        taxonomy = {field: taxonomy.get(field) or "UNK" for field in taxonomy_fields}

        return jsonify({
            "taxonomy": taxonomy
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
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
        s.strip().lower().replace("_", " ")
        for s in species_names.split(",")
        if s.strip()
    ]

    results = {}

    try:
        for NAME in species_list:
            gbif_result = gbif_match(NAME)

            taxonomy = {
                field: gbif_result.get(field)
                for field in taxonomy_fields
            }

            if any(v is None for v in taxonomy.values()):
                xml_result = ncbi_match(NAME)
                if xml_result:
                    ncbi_taxonomy = parse_ncbi_xml(xml_result)
                    taxonomy.update(ncbi_taxonomy)

            taxonomy = {f: taxonomy.get(f) or "UNK" for f in taxonomy_fields}

            results[NAME] = taxonomy

        return jsonify({"taxonomy": results}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # use Render's assigned port
    app.run(host="0.0.0.0", port=port)
