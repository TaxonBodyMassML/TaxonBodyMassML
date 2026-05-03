import numpy as np
import pandas as pd
import requests
import json

test = pd.read_csv("./data/test.csv")
x_test = test.drop(["mass_g"], axis=1)

URL = "https://marxism-smolder-crispy.ngrok-free.dev/xgb_pred_multi"
payload = []
for INDEX in range(0, 5):
    print("Expected mass:", test["mass_g"].iloc[INDEX])

    payload.append({
        "kingdom": x_test["kingdom"].iloc[INDEX],
        "phylum": x_test["phylum"].iloc[INDEX],
        "class": x_test["class"].iloc[INDEX],
        "order": x_test["order"].iloc[INDEX],
        "family": x_test["family"].iloc[INDEX],
        "genus": x_test["genus"].iloc[INDEX],
        "species": x_test["species"].iloc[INDEX]
    })

response = requests.post(URL, json=payload)

# Check response
if response.status_code == 200:
    data = response.json()
    print("\nBatch Prediction Result:")
    print(json.dumps(data, indent=4))
else:
    print(f"Error: {response.status_code}")
    print(response.text)