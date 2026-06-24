from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import json

URL = "http://127.0.0.1:5000/multi_species"
payload = {
    "species_name": "Pseudotsuga menziesii, panthera_tigris, canis_lupus, felis_catus"
}
response = requests.get(URL, params=payload)

# Check response
if response.status_code == 200:
    data = response.json()
    print("Taxonomy Query Result:")
    print(json.dumps(data, indent=4))
else:
    print(f"Error: {response.status_code}")
    print(response.text)
